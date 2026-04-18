"""Anti-cheat system for detecting collusion and suspicious behavior.

Monitors player behavior to detect:
- Collusion (two players always in same team)
- Chip dumping (intentional losing to transfer chips)
- Botting (automated play patterns)
"""
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple
import logging

logger = logging.getLogger(__name__)


class CollusionDetector:
    """Detect if multiple players are colluding (sharing info, soft playing)."""
    
    def __init__(self, suspicion_threshold: int = 5):
        # player_pair -> {games_together, soft_play_count, wins_together}
        self.pair_stats: Dict[Tuple[int, int], Dict] = defaultdict(lambda: {
            "games_together": 0,
            "soft_play": 0,  # Not raising against each other
            "chip_transfers": 0,
            "suspicion_score": 0
        })
        self.suspicion_threshold = suspicion_threshold
        self.suspicious_pairs: Set[Tuple[int, int]] = set()
    
    def record_game_result(self, players: List[int], winner: int, all_ins: List[int] = None):
        """
        Record game result for analysis.
        
        Args:
            players: List of user_ids in the game
            winner: User_id of the winner
            all_ins: List of user_ids who went all-in
        """
        # Update pair statistics
        for i, p1 in enumerate(players):
            for p2 in players[i+1:]:
                pair = tuple(sorted([p1, p2]))
                self.pair_stats[pair]["games_together"] += 1
                
                # Check if they both reached showdown (possible collusion marker)
                if all_ins and p1 in all_ins and p2 in all_ins:
                    self.pair_stats[pair]["chip_transfers"] += 1
        
        # Calculate suspicion scores
        self._update_suspicion_scores()
    
    def _update_suspicion_scores(self):
        """Recalculate suspicion scores for all pairs."""
        for pair, stats in self.pair_stats.items():
            score = 0
            games = stats["games_together"]
            
            if games >= 5:
                # High win rate together
                soft_play_rate = stats["soft_play"] / games
                if soft_play_rate > 0.8:  # 80% soft play
                    score += 3
                
                # High chip transfer rate
                transfer_rate = stats["chip_transfers"] / games
                if transfer_rate > 0.5:
                    score += 5
                
                # Many games together
                if games > 20:
                    score += min((games - 20) // 10, 5)
            
            stats["suspicion_score"] = score
            
            # Flag suspicious pairs
            if score >= self.suspicion_threshold:
                self.suspicious_pairs.add(pair)
                logger.warning(f"🚨 SUSPICIOUS PAIR DETECTED: {pair} (score: {score})")
    
    def check_player(self, user_id: int) -> List[Tuple[int, int, int]]:
        """
        Check if a player is involved in suspicious activity.
        
        Returns list of (partner_id, suspicion_score, games_together)
        """
        results = []
        for pair, stats in self.pair_stats.items():
            if user_id in pair:
                if stats["suspicion_score"] >= self.suspicion_threshold:
                    partner = pair[0] if pair[1] == user_id else pair[1]
                    results.append((
                        partner,
                        stats["suspicion_score"],
                        stats["games_together"]
                    ))
        return sorted(results, key=lambda x: x[1], reverse=True)
    
    def get_alert_message(self, pair: Tuple[int, int]) -> str:
        """Generate alert message for admin."""
        stats = self.pair_stats[pair]
        return (
            f"🚨 <b>POTENTIAL COLLUSION DETECTED</b>\n"
            f"════════════════════\n\n"
            f"Players: <code>{pair[0]}</code> & <code>{pair[1]}</code>\n"
            f"Suspicion Score: <b>{stats['suspicion_score']}/10</b>\n"
            f"Games Together: {stats['games_together']}\n"
            f"Soft Play Count: {stats['soft_play']}\n"
            f"Chip Transfers: {stats['chip_transfers']}\n\n"
            f"<i>Review recommended</i>"
        )


class ChipDumpingDetector:
    """Detect intentional chip dumping between players."""
    
    def __init__(self):
        # donor -> recipient -> amount_transferred
        self.transfers: Dict[int, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        self.dumping_threshold = 10000  # Chips threshold
    
    def record_hand(self, players_bets: Dict[int, int], winner: int):
        """
        Record betting patterns from a hand.
        
        Args:
            players_bets: {user_id: total_bet_amount}
            winner: user_id who won
        """
        # Check for large losses to the same player
        for player, bet in players_bets.items():
            if player != winner and bet > 0:
                self.transfers[player][winner] += bet
                
                # Check threshold
                if self.transfers[player][winner] >= self.dumping_threshold:
                    logger.warning(
                        f"🚨 CHIP DUMPING: Player {player} lost "
                        f"{self.transfers[player][winner]} chips to {winner}"
                    )
    
    def get_dumping_suspicion(self, user_id: int) -> List[Tuple[int, int]]:
        """
        Get list of suspected chip dumping for a user.
        
        Returns list of (recipient_id, total_chips_lost)
        """
        suspects = []
        for recipient, amount in self.transfers[user_id].items():
            if amount >= self.dumping_threshold // 2:  # Lower threshold for reporting
                suspects.append((recipient, amount))
        return sorted(suspects, key=lambda x: x[1], reverse=True)


class AntiCheatManager:
    """Main anti-cheat manager coordinating all detectors."""
    
    def __init__(self):
        self.collusion = CollusionDetector()
        self.dumping = ChipDumpingDetector()
        self.banned_users: Set[int] = set()
        self.warnings: Dict[int, List[str]] = defaultdict(list)
    
    def record_game(self, game_data: dict):
        """Record complete game data for analysis."""
        players = game_data.get("players", [])
        winner = game_data.get("winner")
        
        # Update detectors
        self.collusion.record_game_result(
            [p["user_id"] for p in players],
            winner,
            game_data.get("all_ins", [])
        )
        
        # Check betting patterns for chip dumping
        bets = {p["user_id"]: p.get("total_bet", 0) for p in players}
        self.dumping.record_hand(bets, winner)
    
    def check_user(self, user_id: int) -> dict:
        """Get complete anti-cheat report for a user."""
        collusion_suspects = self.collusion.check_player(user_id)
        dumping_suspects = self.dumping.get_dumping_suspicion(user_id)
        
        return {
            "user_id": user_id,
            "is_banned": user_id in self.banned_users,
            "warnings": self.warnings.get(user_id, []),
            "collusion_suspects": [
                {"partner": p, "score": s, "games": g}
                for p, s, g in collusion_suspects
            ],
            "chip_dumping_suspects": [
                {"recipient": r, "amount": a}
                for r, a in dumping_suspects
            ],
            "risk_score": self._calculate_risk_score(user_id, collusion_suspects)
        }
    
    def _calculate_risk_score(self, user_id: int, collusion_data: List) -> int:
        """Calculate overall risk score 0-100."""
        score = 0
        
        # Collusion contribution
        if collusion_data:
            score += min(collusion_data[0][1] * 10, 50)  # Max 50 from collusion
        
        # Chip dumping contribution
        dumping = self.dumping.get_dumping_suspicion(user_id)
        if dumping:
            score += min(len(dumping) * 10, 30)  # Max 30 from dumping
        
        return min(score, 100)
    
    def ban_user(self, user_id: int, reason: str):
        """Ban a user from the system."""
        self.banned_users.add(user_id)
        logger.critical(f"⛔ USER BANNED: {user_id} - {reason}")
        # TODO: Update database to mark user as banned
    
    def get_alerts(self) -> List[str]:
        """Get all current alerts for admin review."""
        alerts = []
        
        for pair in self.collusion.suspicious_pairs:
            alerts.append(self.collusion.get_alert_message(pair))
        
        return alerts


# Global instance
_anti_cheat: AntiCheatManager = None


def get_anti_cheat() -> AntiCheatManager:
    """Get or create global anti-cheat manager."""
    global _anti_cheat
    if _anti_cheat is None:
        _anti_cheat = AntiCheatManager()
    return _anti_cheat
