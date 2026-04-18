"""Webhook server for production deployment.

This provides an alternative to polling mode for better reliability
and lower latency in production environments.
"""
import asyncio
import logging
from aiohttp import web
from telegram import Update
from telegram.ext import Application

logger = logging.getLogger(__name__)


class WebhookServer:
    """AIOHTTP server to handle Telegram webhook requests."""
    
    def __init__(
        self,
        application: Application,
        host: str = "0.0.0.0",
        port: int = 8080,
        webhook_path: str = "/webhook",
        health_path: str = "/health"
    ):
        self.application = application
        self.host = host
        self.port = port
        self.webhook_path = webhook_path
        self.health_path = health_path
        self.app = web.Application()
        self.runner = None
        
        # Setup routes
        self.app.router.add_post(webhook_path, self.handle_webhook)
        self.app.router.add_get(health_path, self.handle_health)
        self.app.router.add_get("/", self.handle_root)
    
    async def handle_webhook(self, request: web.Request) -> web.Response:
        """Handle incoming webhook updates from Telegram."""
        try:
            data = await request.json()
            update = Update.de_json(data, self.application.bot)
            
            # Process update
            await self.application.process_update(update)
            
            return web.Response(status=200, text="OK")
        except Exception as e:
            logger.error(f"Error processing webhook: {e}")
            return web.Response(status=500, text="Error")
    
    async def handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint for monitoring."""
        try:
            from health_check import get_health_monitor
            health_monitor = get_health_monitor()
            status = await health_monitor.get_status()
            
            return web.json_response({
                "status": status.status,
                "uptime_seconds": status.uptime_seconds,
                "active_games": status.active_games,
                "total_users": status.total_users,
                "db_connected": status.db_connected,
                "timestamp": status.timestamp
            })
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return web.json_response(
                {"status": "error", "message": str(e)},
                status=500
            )
    
    async def handle_root(self, request: web.Request) -> web.Response:
        """Root endpoint with basic info."""
        return web.json_response({
            "name": "PokerHubs Bot",
            "status": "running",
            "webhook": self.webhook_path,
            "health": self.health_path
        })
    
    async def start(self):
        """Start the webhook server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        
        logger.info(f"🌐 Webhook server started on http://{self.host}:{self.port}")
        logger.info(f"   Webhook URL: {self.webhook_path}")
        logger.info(f"   Health check: {self.health_path}")
    
    async def stop(self):
        """Stop the webhook server."""
        if self.runner:
            await self.runner.cleanup()
            logger.info("🌐 Webhook server stopped")


async def setup_webhook(
    application: Application,
    webhook_url: str,
    host: str = "0.0.0.0",
    port: int = 8080
) -> WebhookServer:
    """
    Setup and start webhook server with Telegram.
    
    Args:
        application: The bot application
        webhook_url: Full URL where Telegram should send updates
        host: Host to bind the server to
        port: Port to listen on
    
    Returns:
        WebhookServer instance
    """
    # Create server
    server = WebhookServer(application, host=host, port=port)
    
    # Start server first
    await server.start()
    
    # Set webhook in Telegram
    await application.bot.set_webhook(
        url=webhook_url,
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )
    
    logger.info(f"🔗 Webhook set: {webhook_url}")
    
    return server


async def remove_webhook(application: Application):
    """Remove webhook and switch back to polling if needed."""
    try:
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("🔗 Webhook deleted")
    except Exception as e:
        logger.error(f"Failed to delete webhook: {e}")
