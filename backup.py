"""Database backup system with automatic rotation."""
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class DatabaseBackup:
    """Manage database backups with rotation and cleanup."""
    
    def __init__(
        self,
        db_path: str = "poker_stats.db",
        backup_dir: str = "backups",
        max_backups: int = 7,  # Keep 7 days of daily backups
        max_daily_backups: int = 24  # Keep hourly backups for today
    ):
        self.db_path = db_path
        self.backup_dir = Path(backup_dir)
        self.max_backups = max_backups
        self.max_daily_backups = max_daily_backups
        
        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        self.daily_dir = self.backup_dir / "daily"
        self.hourly_dir = self.backup_dir / "hourly"
        self.daily_dir.mkdir(exist_ok=True)
        self.hourly_dir.mkdir(exist_ok=True)
    
    def create_backup(self, backup_type: str = "manual") -> str:
        """Create a new database backup."""
        if not os.path.exists(self.db_path):
            logger.error(f"Database file not found: {self.db_path}")
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"poker_stats_{backup_type}_{timestamp}.db"
        
        # Choose directory based on type
        if backup_type == "hourly":
            backup_path = self.hourly_dir / backup_filename
        else:
            backup_path = self.daily_dir / backup_filename
        
        try:
            shutil.copy2(self.db_path, backup_path)
            size_mb = os.path.getsize(backup_path) / (1024 * 1024)
            logger.info(f"✅ Backup created: {backup_path} ({size_mb:.2f} MB)")
            return str(backup_path)
        except Exception as e:
            logger.error(f"❌ Backup failed: {e}")
            return None
    
    def cleanup_old_backups(self):
        """Remove old backups according to retention policy."""
        try:
            # Clean old daily backups (keep only max_backups)
            daily_backups = sorted(self.daily_dir.glob("*.db"), key=os.path.getctime)
            if len(daily_backups) > self.max_backups:
                for old_backup in daily_backups[:-self.max_backups]:
                    old_backup.unlink()
                    logger.info(f"🗑️ Deleted old daily backup: {old_backup.name}")
            
            # Clean old hourly backups (keep only last 24 hours)
            cutoff = datetime.now() - timedelta(hours=self.max_daily_backups)
            hourly_backups = self.hourly_dir.glob("*.db")
            for backup in hourly_backups:
                if datetime.fromtimestamp(os.path.getctime(backup)) < cutoff:
                    backup.unlink()
                    logger.info(f"🗑️ Deleted old hourly backup: {backup.name}")
                    
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
    
    def get_latest_backup(self) -> str:
        """Get path to the most recent backup."""
        all_backups = list(self.daily_dir.glob("*.db")) + list(self.hourly_dir.glob("*.db"))
        if not all_backups:
            return None
        return str(max(all_backups, key=os.path.getctime))
    
    def list_backups(self) -> list:
        """List all available backups with info."""
        backups = []
        for backup_file in sorted(self.backup_dir.rglob("*.db"), key=os.path.getctime, reverse=True):
            stat = backup_file.stat()
            backups.append({
                "path": str(backup_file),
                "name": backup_file.name,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
                "type": backup_file.parent.name
            })
        return backups
    
    def restore_backup(self, backup_path: str = None) -> bool:
        """Restore database from backup."""
        if backup_path is None:
            backup_path = self.get_latest_backup()
        
        if not backup_path or not os.path.exists(backup_path):
            logger.error(f"Backup not found: {backup_path}")
            return False
        
        try:
            # Create emergency backup of current state
            if os.path.exists(self.db_path):
                emergency_path = f"{self.db_path}.emergency_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.copy2(self.db_path, emergency_path)
                logger.warning(f"⚠️ Emergency backup created: {emergency_path}")
            
            # Restore
            shutil.copy2(backup_path, self.db_path)
            logger.info(f"✅ Database restored from: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Restore failed: {e}")
            return False


def auto_backup_task(backup_manager: DatabaseBackup, interval_hours: int = 1):
    """Async task for automatic backups."""
    import asyncio
    
    async def backup_loop():
        while True:
            try:
                # Create hourly backup
                backup_manager.create_backup("hourly")
                
                # Also create daily backup at midnight
                now = datetime.now()
                if now.hour == 0:
                    backup_manager.create_backup("daily")
                
                # Cleanup old backups
                backup_manager.cleanup_old_backups()
                
                # Wait for next interval
                await asyncio.sleep(interval_hours * 3600)
            except Exception as e:
                logger.error(f"Auto-backup error: {e}")
                await asyncio.sleep(60)  # Retry in 1 minute on error
    
    return backup_loop()
