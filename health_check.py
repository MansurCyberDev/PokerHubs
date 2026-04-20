import psutil
import asyncio
from datetime import datetime
from typing import Dict, Any


class HealthMonitor:
    """Simple health monitoring for the bot."""
    
    def __init__(self):
        self.start_time = datetime.now()
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current health status."""
        try:
            # Get CPU and memory usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used = memory.used / (1024 ** 3)  # GB
            memory_total = memory.total / (1024 ** 3)  # GB
            
            # Get disk usage
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            disk_used = disk.used / (1024 ** 3)  # GB
            disk_total = disk.total / (1024 ** 3)  # GB
            
            # Calculate uptime
            uptime = datetime.now() - self.start_time
            uptime_seconds = int(uptime.total_seconds())
            uptime_hours = uptime_seconds // 3600
            uptime_minutes = (uptime_seconds % 3600) // 60
            uptime_str = f"{uptime_hours}h {uptime_minutes}m"
            
            return {
                'status': 'healthy',
                'uptime': uptime_str,
                'cpu_percent': cpu_percent,
                'memory_percent': memory_percent,
                'memory_used_gb': round(memory_used, 2),
                'memory_total_gb': round(memory_total, 2),
                'disk_percent': disk_percent,
                'disk_used_gb': round(disk_used, 2),
                'disk_total_gb': round(disk_total, 2),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
    
    def format_status_message(self, status: Dict[str, Any]) -> str:
        """Format status as a readable message."""
        if status['status'] == 'error':
            return (
                f"❌ <b>Health Check Error</b>\n\n"
                f"Error: {status.get('error', 'Unknown')}\n"
                f"Time: {status.get('timestamp', 'N/A')}"
            )
        
        return (
            f"✅ <b>Bot Health Status</b>\n"
            f"════════════════════\n\n"
            f"🟢 Status: <b>{status['status'].upper()}</b>\n"
            f"⏱ Uptime: <b>{status['uptime']}</b>\n\n"
            f"💻 CPU: <b>{status['cpu_percent']}%</b>\n"
            f"🧠 Memory: <b>{status['memory_percent']}%</b> "
            f"({status['memory_used_gb']} / {status['memory_total_gb']} GB)\n"
            f"💾 Disk: <b>{status['disk_percent']}%</b> "
            f"({status['disk_used_gb']} / {status['disk_total_gb']} GB)\n\n"
            f"🕐 Checked: {status['timestamp']}"
        )


def get_health_monitor() -> HealthMonitor:
    """Get or create health monitor instance."""
    if not hasattr(get_health_monitor, '_instance'):
        get_health_monitor._instance = HealthMonitor()
    return get_health_monitor._instance
