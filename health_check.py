"""Health check and monitoring system for production."""
import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    """Health check status data."""
    status: str  # "healthy", "degraded", "unhealthy"
    uptime_seconds: float
    active_games: int
    total_users: int
    db_connected: bool
    last_error: Optional[str]
    timestamp: str


class HealthMonitor:
    """Monitor bot health and expose status endpoint."""
    
    def __init__(self, start_time: float = None):
        self.start_time = start_time or time.time()
        self.errors = []
        self.max_errors = 10
        self._db_check_interval = 60  # Check DB every minute
        self._last_db_check = 0
        self._db_status = True
    
    def record_error(self, error: str):
        """Record an error for health tracking."""
        self.errors.append({
            "time": datetime.now().isoformat(),
            "error": error
        })
        # Keep only recent errors
        if len(self.errors) > self.max_errors:
            self.errors.pop(0)
        logger.warning(f"Health check recorded error: {error}")
    
    async def check_database(self) -> bool:
        """Check database connectivity."""
        try:
            from database import aiosqlite, DB_NAME
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute("SELECT 1")
                return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    async def get_status(self) -> HealthStatus:
        """Get current health status."""
        # Cache DB check for performance
        now = time.time()
        if now - self._last_db_check > self._db_check_interval:
            self._db_status = await self.check_database()
            self._last_db_check = now
        
        # Get active games count
        try:
            from game_state import active_games
            active_games_count = len(active_games)
        except:
            active_games_count = 0
        
        # Determine overall status
        if not self._db_status:
            status = "unhealthy"
        elif len(self.errors) > 5:
            status = "degraded"
        else:
            status = "healthy"
        
        return HealthStatus(
            status=status,
            uptime_seconds=round(time.time() - self.start_time, 2),
            active_games=active_games_count,
            total_users=await self._get_user_count(),
            db_connected=self._db_status,
            last_error=self.errors[-1]["error"] if self.errors else None,
            timestamp=datetime.now().isoformat()
        )
    
    async def _get_user_count(self) -> int:
        """Get total users from database."""
        try:
            from database import aiosqlite, DB_NAME
            async with aiosqlite.connect(DB_NAME) as db:
                async with db.execute("SELECT COUNT(*) FROM players") as cursor:
                    result = await cursor.fetchone()
                    return result[0] if result else 0
        except:
            return 0
    
    def format_status_message(self, status: HealthStatus) -> str:
        """Format health status for display."""
        emoji = "🟢" if status.status == "healthy" else "🟡" if status.status == "degraded" else "🔴"
        uptime_hours = status.uptime_seconds / 3600
        
        return (
            f"{emoji} <b>Health Status: {status.status.upper()}</b>\n"
            f"════════════════════\n\n"
            f"⏱️ Uptime: {uptime_hours:.1f} hours\n"
            f"🎮 Active Games: {status.active_games}\n"
            f"👥 Total Users: {status.total_users}\n"
            f"🗄️ Database: {'✅ Connected' if status.db_connected else '❌ Disconnected'}\n"
            f"🕐 Last Check: {status.timestamp[:19]}"
        )


class RateLimiter:
    """Rate limiting for commands to prevent spam."""
    
    def __init__(
        self,
        default_limit: int = 20,  # commands per minute
        burst_limit: int = 5,     # burst allowance
        window_seconds: int = 60
    ):
        self.limits: Dict[int, Dict] = {}  # user_id -> {count, reset_time, burst_count}
        self.default_limit = default_limit
        self.burst_limit = burst_limit
        self.window_seconds = window_seconds
        self.blocked_users: Dict[int, float] = {}  # user_id -> unblock_time
    
    def is_allowed(self, user_id: int, command: str = None) -> tuple[bool, Optional[str]]:
        """
        Check if user is allowed to execute command.
        Returns (allowed, message if blocked).
        """
        now = time.time()
        
        # Check if user is blocked
        if user_id in self.blocked_users:
            if now < self.blocked_users[user_id]:
                remaining = int(self.blocked_users[user_id] - now)
                return False, f"⏳ Rate limit exceeded. Try again in {remaining} seconds."
            else:
                del self.blocked_users[user_id]
        
        # Initialize or reset expired window
        if user_id not in self.limits or now > self.limits[user_id]["reset_time"]:
            self.limits[user_id] = {
                "count": 0,
                "reset_time": now + self.window_seconds,
                "burst_count": 0
            }
        
        user_data = self.limits[user_id]
        
        # Check burst limit (immediate blocking)
        if user_data["burst_count"] >= self.burst_limit:
            block_duration = 30  # 30 second block for burst
            self.blocked_users[user_id] = now + block_duration
            return False, f"🚫 Too many commands! Blocked for {block_duration} seconds."
        
        # Check rate limit
        if user_data["count"] >= self.default_limit:
            remaining = int(user_data["reset_time"] - now)
            return False, f"⏳ Rate limit: {self.default_limit} commands per minute. Reset in {remaining}s."
        
        # Increment counters
        user_data["count"] += 1
        user_data["burst_count"] += 1
        
        # Decay burst count over time
        if user_data["count"] <= self.burst_limit:
            user_data["burst_count"] = max(0, user_data["burst_count"] - 1)
        
        return True, None
    
    def get_status(self, user_id: int) -> str:
        """Get rate limit status for user."""
        if user_id not in self.limits:
            return "Rate limit: 0/{} commands used".format(self.default_limit)
        
        user_data = self.limits[user_id]
        remaining = int(user_data["reset_time"] - time.time())
        
        return (
            f"Commands: {user_data['count']}/{self.default_limit}\n"
            f"Reset in: {remaining}s"
        )
    
    def cleanup(self):
        """Clean up expired entries."""
        now = time.time()
        expired = [uid for uid, data in self.limits.items() if now > data["reset_time"]]
        for uid in expired:
            del self.limits[uid]
        
        unblocked = [uid for uid, time_unblock in self.blocked_users.items() if now > time_unblock]
        for uid in unblocked:
            del self.blocked_users[uid]


# Global instances
_health_monitor: Optional[HealthMonitor] = None
_rate_limiter: Optional[RateLimiter] = None


def get_health_monitor() -> HealthMonitor:
    """Get or create global health monitor."""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = HealthMonitor()
    return _health_monitor


def get_rate_limiter() -> RateLimiter:
    """Get or create global rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
