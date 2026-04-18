"""Analytics tracking system for game metrics and user behavior.

Tracks:
- DAU/MAU (Daily/Monthly Active Users)
- Retention rates
- Revenue from Kaspi payments
- Popular features usage
- Game statistics
"""
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from database import aiosqlite, DB_NAME

logger = logging.getLogger(__name__)


class AnalyticsTracker:
    """Track and store analytics events."""
    
    def __init__(self):
        self._initialized = False
    
    async def init_tables(self):
        """Create analytics tables."""
        if self._initialized:
            return
        
        async with aiosqlite.connect(DB_NAME) as db:
            # Events table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS analytics_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    user_id INTEGER,
                    chat_id INTEGER,
                    data TEXT,
                    timestamp TEXT NOT NULL
                )
            ''')
            
            # Daily metrics table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS analytics_daily (
                    date TEXT PRIMARY KEY,
                    dau INTEGER DEFAULT 0,
                    games_started INTEGER DEFAULT 0,
                    games_completed INTEGER DEFAULT 0,
                    new_users INTEGER DEFAULT 0,
                    revenue_kzt INTEGER DEFAULT 0,
                    skins_purchased INTEGER DEFAULT 0
                )
            ''')
            
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_events_type_time 
                ON analytics_events(event_type, timestamp)
            ''')
            
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_events_user 
                ON analytics_events(user_id, timestamp)
            ''')
            
            await db.commit()
        
        self._initialized = True
        logger.info("📊 Analytics tables initialized")
    
    async def track_event(self, event_type: str, user_id: int = None, 
                         chat_id: int = None, data: dict = None):
        """
        Track an analytics event.
        
        Args:
            event_type: Type of event (e.g., 'game_start', 'skin_purchase')
            user_id: Telegram user ID
            chat_id: Chat/group ID
            data: Additional JSON-serializable data
        """
        await self.init_tables()
        
        timestamp = datetime.now().isoformat()
        data_json = json.dumps(data) if data else None
        
        try:
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute('''
                    INSERT INTO analytics_events 
                    (event_type, user_id, chat_id, data, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                ''', (event_type, user_id, chat_id, data_json, timestamp))
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to track event: {e}")
    
    async def track_game_start(self, chat_id: int, creator_id: int, player_count: int):
        """Track when a game starts."""
        await self.track_event(
            'game_start',
            user_id=creator_id,
            chat_id=chat_id,
            data={'player_count': player_count}
        )
    
    async def track_game_end(self, chat_id: int, winner_id: int, pot_size: int, 
                            hand_count: int):
        """Track when a game ends."""
        await self.track_event(
            'game_end',
            user_id=winner_id,
            chat_id=chat_id,
            data={'pot_size': pot_size, 'hand_count': hand_count}
        )
    
    async def track_skin_purchase(self, user_id: int, skin_type: str, 
                                 skin_id: str, price: int):
        """Track skin purchase."""
        await self.track_event(
            'skin_purchase',
            user_id=user_id,
            data={'skin_type': skin_type, 'skin_id': skin_id, 'price': price}
        )
    
    async def track_kaspi_payment(self, user_id: int, amount_kzt: int, 
                                  item_type: str, item_amount: int):
        """Track Kaspi payment."""
        await self.track_event(
            'kaspi_payment',
            user_id=user_id,
            data={
                'amount_kzt': amount_kzt,
                'item_type': item_type,
                'item_amount': item_amount
            }
        )
    
    async def update_daily_metrics(self, date: str = None):
        """Update daily metrics aggregate."""
        date = date or datetime.now().strftime('%Y-%m-%d')
        
        async with aiosqlite.connect(DB_NAME) as db:
            # Calculate DAU
            async with db.execute('''
                SELECT COUNT(DISTINCT user_id) FROM analytics_events
                WHERE date(timestamp) = ? AND user_id IS NOT NULL
            ''', (date,)) as cursor:
                dau = (await cursor.fetchone())[0] or 0
            
            # Calculate games
            async with db.execute('''
                SELECT 
                    SUM(CASE WHEN event_type = 'game_start' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN event_type = 'game_end' THEN 1 ELSE 0 END)
                FROM analytics_events
                WHERE date(timestamp) = ?
            ''', (date,)) as cursor:
                row = await cursor.fetchone()
                games_started = row[0] or 0
                games_completed = row[1] or 0
            
            # Calculate revenue
            async with db.execute('''
                SELECT SUM(amount_kzt) FROM analytics_events
                WHERE date(timestamp) = ? AND event_type = 'kaspi_payment'
            ''', (date,)) as cursor:
                revenue = (await cursor.fetchone())[0] or 0
            
            # Insert or update
            await db.execute('''
                INSERT OR REPLACE INTO analytics_daily
                (date, dau, games_started, games_completed, revenue_kzt)
                VALUES (?, ?, ?, ?, ?)
            ''', (date, dau, games_started, games_completed, revenue))
            await db.commit()
    
    async def get_dashboard_stats(self, days: int = 30) -> dict:
        """Get analytics dashboard statistics."""
        await self.init_tables()
        
        since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            
            # Daily stats
            async with db.execute('''
                SELECT * FROM analytics_daily
                WHERE date >= ?
                ORDER BY date DESC
            ''', (since_date,)) as cursor:
                daily_rows = await cursor.fetchall()
            
            # Top events
            async with db.execute('''
                SELECT event_type, COUNT(*) as count
                FROM analytics_events
                WHERE date(timestamp) >= ?
                GROUP BY event_type
                ORDER BY count DESC
            ''', (since_date,)) as cursor:
                event_rows = await cursor.fetchall()
            
            # Top users
            async with db.execute('''
                SELECT user_id, COUNT(*) as events
                FROM analytics_events
                WHERE date(timestamp) >= ? AND user_id IS NOT NULL
                GROUP BY user_id
                ORDER BY events DESC
                LIMIT 10
            ''', (since_date,)) as cursor:
                top_users = await cursor.fetchall()
        
        # Calculate aggregates
        total_revenue = sum(r['revenue_kzt'] for r in daily_rows)
        avg_dau = sum(r['dau'] for r in daily_rows) / len(daily_rows) if daily_rows else 0
        total_games = sum(r['games_completed'] for r in daily_rows)
        
        return {
            "period_days": days,
            "summary": {
                "total_revenue_kzt": total_revenue,
                "avg_dau": round(avg_dau, 1),
                "total_games": total_games,
                "active_days": len(daily_rows)
            },
            "daily": [
                {
                    "date": r['date'],
                    "dau": r['dau'],
                    "games": r['games_completed'],
                    "revenue": r['revenue_kzt']
                }
                for r in daily_rows
            ],
            "top_events": [
                {"event": r['event_type'], "count": r['count']}
                for r in event_rows[:10]
            ],
            "top_users": [
                {"user_id": r['user_id'], "events": r['events']}
                for r in top_users
            ]
        }
    
    async def format_dashboard(self, stats: dict) -> str:
        """Format stats for Telegram display."""
        summary = stats['summary']
        
        return (
            f"📊 <b>ANALYTICS DASHBOARD</b>\n"
            f"════════════════════\n\n"
            f"<b>Last {stats['period_days']} Days:</b>\n"
            f"💰 Revenue: <b>{summary['total_revenue_kzt']:,} ₸</b>\n"
            f"👥 Avg DAU: <b>{summary['avg_dau']}</b>\n"
            f"🎮 Games: <b>{summary['total_games']}</b>\n"
            f"📅 Active Days: <b>{summary['active_days']}</b>\n\n"
            f"<i>Top Events:</i>\n" +
            "\n".join([
                f"  • {e['event']}: {e['count']}"
                for e in stats['top_events'][:5]
            ])
        )


# Global instance
_analytics: AnalyticsTracker = None


def get_analytics() -> AnalyticsTracker:
    """Get or create global analytics tracker."""
    global _analytics
    if _analytics is None:
        _analytics = AnalyticsTracker()
    return _analytics
