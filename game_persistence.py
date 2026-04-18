"""Game state persistence - save active games to database.

This module ensures games survive bot restarts by persisting
game state to SQLite and restoring on startup.
"""
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict
from dataclasses import asdict

from database import aiosqlite, DB_NAME
from game_state import Game, GamePhase, Player, active_games

logger = logging.getLogger(__name__)


class GamePersistence:
    """Manage saving and loading game state."""
    
    @staticmethod
    async def init_tables():
        """Create tables for game persistence."""
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS saved_games (
                    chat_id INTEGER PRIMARY KEY,
                    game_data TEXT NOT NULL,
                    saved_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS game_players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    username TEXT,
                    first_name TEXT,
                    balance INTEGER,
                    current_bet INTEGER,
                    total_bet INTEGER,
                    folded INTEGER,
                    all_in INTEGER,
                    FOREIGN KEY (chat_id) REFERENCES saved_games(chat_id)
                )
            ''')
            
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_game_players_chat_id 
                ON game_players(chat_id)
            ''')
            
            await db.commit()
            logger.info("🗄️ Game persistence tables initialized")
    
    @staticmethod
    def _serialize_game(game: Game) -> dict:
        """Convert Game object to serializable dict."""
        return {
            "chat_id": game.chat_id,
            "creator_id": game.creator_id,
            "phase": game.phase.value if isinstance(game.phase, GamePhase) else game.phase,
            "small_blind": game.small_blind,
            "big_blind": game.big_blind,
            "current_bet": game.current_bet,
            "min_raise": game.min_raise,
            "pot": game.pot,
            "side_pots": game.side_pots,
            "community_cards": game.community_cards,
            "deck": game.deck.cards if hasattr(game.deck, 'cards') else [],
            "button_index": game.button_index,
            "current_player_idx": game.current_player_idx,
            "registration_open": game.registration_open,
            "turn_end_time": game.turn_end_time,
            "max_players": game.max_players,
            "settings": game.settings if hasattr(game, 'settings') else {},
        }
    
    @staticmethod
    def _serialize_players(players: List[Player]) -> List[dict]:
        """Convert Player objects to serializable dicts."""
        return [
            {
                "user_id": p.user_id,
                "username": p.username,
                "first_name": p.first_name,
                "balance": p.balance,
                "hand": p.hand if hasattr(p, 'hand') else [],
                "current_bet": p.current_bet if hasattr(p, 'current_bet') else 0,
                "total_bet": p.total_bet if hasattr(p, 'total_bet') else 0,
                "folded": p.folded if hasattr(p, 'folded') else False,
                "all_in": p.all_in if hasattr(p, 'all_in') else False,
                "is_active": p.is_active if hasattr(p, 'is_active') else True,
            }
            for p in players
        ]
    
    @staticmethod
    async def save_game(chat_id: int, game: Game):
        """Save a game to the database."""
        try:
            game_data = {
                "game": GamePersistence._serialize_game(game),
                "players": GamePersistence._serialize_players(game.players),
            }
            
            saved_at = datetime.now().isoformat()
            # Games expire after 24 hours (in case bot is down for long)
            from datetime import timedelta
            expires_at = (datetime.now() + timedelta(hours=24)).isoformat()
            
            async with aiosqlite.connect(DB_NAME) as db:
                # Save game data
                await db.execute('''
                    INSERT OR REPLACE INTO saved_games 
                    (chat_id, game_data, saved_at, expires_at)
                    VALUES (?, ?, ?, ?)
                ''', (chat_id, json.dumps(game_data), saved_at, expires_at))
                
                # Delete old player records
                await db.execute(
                    "DELETE FROM game_players WHERE chat_id = ?",
                    (chat_id,)
                )
                
                # Insert player records
                for player in game.players:
                    await db.execute('''
                        INSERT INTO game_players 
                        (chat_id, user_id, username, first_name, balance, 
                         current_bet, total_bet, folded, all_in)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        chat_id,
                        player.user_id,
                        getattr(player, 'username', ''),
                        getattr(player, 'first_name', ''),
                        player.balance,
                        getattr(player, 'current_bet', 0),
                        getattr(player, 'total_bet', 0),
                        int(getattr(player, 'folded', False)),
                        int(getattr(player, 'all_in', False))
                    ))
                
                await db.commit()
                logger.info(f"💾 Game {chat_id} saved ({len(game.players)} players)")
                
        except Exception as e:
            logger.error(f"❌ Failed to save game {chat_id}: {e}")
    
    @staticmethod
    async def load_game(chat_id: int) -> Optional[Game]:
        """Load a game from the database."""
        try:
            async with aiosqlite.connect(DB_NAME) as db:
                db.row_factory = aiosqlite.Row
                
                # Get game data
                async with db.execute(
                    "SELECT * FROM saved_games WHERE chat_id = ? AND expires_at > datetime('now')",
                    (chat_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return None
                    
                    game_data = json.loads(row['game_data'])
                
                # Get players
                async with db.execute(
                    "SELECT * FROM game_players WHERE chat_id = ?",
                    (chat_id,)
                ) as cursor:
                    player_rows = await cursor.fetchall()
                    players_data = [dict(r) for r in player_rows]
                
                # Reconstruct game
                from game_state import Game, Player, Deck
                
                game_info = game_data['game']
                players_info = game_data['players']
                
                # Create game object
                game = Game(
                    chat_id=chat_id,
                    creator_id=game_info['creator_id'],
                    small_blind=game_info.get('small_blind', 10),
                    big_blind=game_info.get('big_blind', 20)
                )
                
                # Restore game state
                game.phase = GamePhase(game_info['phase'])
                game.current_bet = game_info.get('current_bet', 0)
                game.min_raise = game_info.get('min_raise', game.big_blind)
                game.pot = game_info.get('pot', 0)
                game.side_pots = game_info.get('side_pots', [])
                game.community_cards = game_info.get('community_cards', [])
                game.button_index = game_info.get('button_index', 0)
                game.current_player_idx = game_info.get('current_player_idx', 0)
                game.registration_open = game_info.get('registration_open', False)
                game.turn_end_time = game_info.get('turn_end_time')
                game.max_players = game_info.get('max_players', 9)
                
                # Restore deck if possible
                deck_cards = game_info.get('deck', [])
                if deck_cards:
                    from cards import Card
                    game.deck.cards = [Card(c['rank'], c['suit']) for c in deck_cards]
                
                # Restore players
                for p_data in players_info:
                    player = Player(
                        user_id=p_data['user_id'],
                        username=p_data.get('username', ''),
                        first_name=p_data.get('first_name', ''),
                        balance=p_data['balance']
                    )
                    player.hand = p_data.get('hand', [])
                    player.current_bet = p_data.get('current_bet', 0)
                    player.total_bet = p_data.get('total_bet', 0)
                    player.folded = bool(p_data.get('folded', 0))
                    player.all_in = bool(p_data.get('all_in', 0))
                    player.is_active = p_data.get('is_active', True)
                    game.players.append(player)
                
                logger.info(f"📂 Game {chat_id} loaded ({len(game.players)} players)")
                return game
                
        except Exception as e:
            logger.error(f"❌ Failed to load game {chat_id}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    async def delete_game(chat_id: int):
        """Delete a saved game."""
        try:
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute(
                    "DELETE FROM saved_games WHERE chat_id = ?",
                    (chat_id,)
                )
                await db.execute(
                    "DELETE FROM game_players WHERE chat_id = ?",
                    (chat_id,)
                )
                await db.commit()
                logger.info(f"🗑️ Saved game {chat_id} deleted")
        except Exception as e:
            logger.error(f"❌ Failed to delete game {chat_id}: {e}")
    
    @staticmethod
    async def list_saved_games() -> List[Dict]:
        """List all saved games."""
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM saved_games WHERE expires_at > datetime('now') ORDER BY saved_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "chat_id": r['chat_id'],
                        "saved_at": r['saved_at'],
                        "expires_at": r['expires_at'],
                        "player_count": await GamePersistence._get_player_count(db, r['chat_id'])
                    }
                    for r in rows
                ]
    
    @staticmethod
    async def _get_player_count(db, chat_id: int) -> int:
        """Get player count for a game."""
        async with db.execute(
            "SELECT COUNT(*) FROM game_players WHERE chat_id = ?",
            (chat_id,)
        ) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0
    
    @staticmethod
    async def cleanup_expired():
        """Delete expired game saves."""
        try:
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute(
                    "DELETE FROM saved_games WHERE expires_at < datetime('now')"
                )
                await db.commit()
                logger.info("🧹 Expired games cleaned up")
        except Exception as e:
            logger.error(f"❌ Failed to cleanup games: {e}")


async def save_all_active_games():
    """Save all currently active games (call before shutdown)."""
    if not active_games:
        logger.info("ℹ️ No active games to save")
        return
    
    logger.info(f"💾 Saving {len(active_games)} active games...")
    for chat_id, game in active_games.items():
        await GamePersistence.save_game(chat_id, game)
    logger.info("✅ All games saved")


async def restore_saved_games():
    """Restore games from database (call on startup)."""
    from game_state import active_games
    
    saved_games = await GamePersistence.list_saved_games()
    if not saved_games:
        logger.info("ℹ️ No saved games to restore")
        return
    
    logger.info(f"📂 Restoring {len(saved_games)} saved games...")
    
    for saved in saved_games:
        chat_id = saved['chat_id']
        game = await GamePersistence.load_game(chat_id)
        if game:
            active_games[chat_id] = game
            logger.info(f"  ✓ Restored game {chat_id} ({saved['player_count']} players)")
        else:
            logger.warning(f"  ✗ Failed to restore game {chat_id}")
    
    logger.info(f"✅ Restored {len(active_games)} games")
