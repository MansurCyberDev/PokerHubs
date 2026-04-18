"""Web-based admin dashboard for managing the poker bot.

Provides browser interface for:
- Viewing real-time statistics
- Managing users and bans
- Monitoring payments
- Viewing analytics charts
"""
import json
import logging
from datetime import datetime
from aiohttp import web
from aiohttp_basicauth import BasicAuthMiddleware

logger = logging.getLogger(__name__)


class WebDashboard:
    """Web admin dashboard server."""
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8081,
        username: str = "admin",
        password: str = "changeme"
    ):
        self.host = host
        self.port = port
        self.app = web.Application()
        self.runner = None
        
        # Add basic auth
        auth = BasicAuthMiddleware(username=username, password=password)
        self.app.middlewares.append(auth)
        
        # Setup routes
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup dashboard routes."""
        self.app.router.add_get('/', self.index)
        self.app.router.add_get('/api/stats', self.api_stats)
        self.app.router.add_get('/api/users', self.api_users)
        self.app.router.add_get('/api/games', self.api_games)
        self.app.router.add_get('/api/payments', self.api_payments)
        self.app.router.add_post('/api/ban_user', self.api_ban_user)
        self.app.router.add_static('/static', path='web_static', name='static')
    
    async def index(self, request: web.Request) -> web.Response:
        """Main dashboard page."""
        html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>PokerHubs Admin Dashboard</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #1a1a2e; color: #eee; }
                .header { background: #16213e; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
                .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }
                .stat-card { background: #0f3460; padding: 20px; border-radius: 10px; text-align: center; }
                .stat-value { font-size: 2em; font-weight: bold; color: #e94560; }
                .stat-label { color: #aaa; margin-top: 5px; }
                .section { background: #16213e; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
                table { width: 100%; border-collapse: collapse; }
                th, td { padding: 10px; text-align: left; border-bottom: 1px solid #0f3460; }
                th { background: #0f3460; }
                .btn { padding: 8px 16px; background: #e94560; color: white; border: none; border-radius: 5px; cursor: pointer; }
                .btn:hover { background: #ff6b6b; }
                .refresh { float: right; }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🎰 PokerHubs Admin Dashboard</h1>
                <button class="btn refresh" onclick="location.reload()">Refresh</button>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value" id="active-games">-</div>
                    <div class="stat-label">Active Games</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="total-users">-</div>
                    <div class="stat-label">Total Users</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="daily-revenue">-</div>
                    <div class="stat-label">Today's Revenue</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="pending-payments">-</div>
                    <div class="stat-label">Pending Payments</div>
                </div>
            </div>
            
            <div class="section">
                <h2>🚨 Anti-Cheat Alerts</h2>
                <div id="alerts-content">Loading...</div>
            </div>
            
            <div class="section">
                <h2>💳 Recent Payments</h2>
                <table id="payments-table">
                    <thead>
                        <tr><th>ID</th><th>User</th><th>Amount</th><th>Status</th><th>Time</th></tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>
            
            <div class="section">
                <h2>🎮 Active Games</h2>
                <table id="games-table">
                    <thead>
                        <tr><th>Chat ID</th><th>Players</th><th>Phase</th><th>Pot</th></tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>
            
            <script>
                async function loadStats() {
                    const res = await fetch('/api/stats');
                    const data = await res.json();
                    document.getElementById('active-games').textContent = data.active_games;
                    document.getElementById('total-users').textContent = data.total_users;
                    document.getElementById('daily-revenue').textContent = data.revenue + ' ₸';
                    document.getElementById('pending-payments').textContent = data.pending_payments;
                }
                
                async function loadPayments() {
                    const res = await fetch('/api/payments');
                    const data = await res.json();
                    const tbody = document.querySelector('#payments-table tbody');
                    tbody.innerHTML = data.map(p => `
                        <tr>
                            <td>#${p.id}</td>
                            <td>${p.user}</td>
                            <td>${p.amount} ₸</td>
                            <td>${p.status}</td>
                            <td>${p.time}</td>
                        </tr>
                    `).join('');
                }
                
                async function loadGames() {
                    const res = await fetch('/api/games');
                    const data = await res.json();
                    const tbody = document.querySelector('#games-table tbody');
                    tbody.innerHTML = data.map(g => `
                        <tr>
                            <td>${g.chat_id}</td>
                            <td>${g.players}</td>
                            <td>${g.phase}</td>
                            <td>${g.pot}</td>
                        </tr>
                    `).join('');
                }
                
                loadStats();
                loadPayments();
                loadGames();
                setInterval(loadStats, 30000); // Refresh every 30s
            </script>
        </body>
        </html>
        '''
        return web.Response(text=html, content_type='text/html')
    
    async def api_stats(self, request: web.Request) -> web.Response:
        """API endpoint for statistics."""
        from game_state import active_games
        from database import aiosqlite, DB_NAME
        
        async with aiosqlite.connect(DB_NAME) as db:
            # Total users
            async with db.execute("SELECT COUNT(*) FROM players") as c:
                total_users = (await c.fetchone())[0]
            
            # Today's revenue
            today = datetime.now().strftime('%Y-%m-%d')
            async with db.execute(
                "SELECT SUM(amount_kzt) FROM kaspi_payments WHERE date(created_at) = ? AND status = 'approved'",
                (today,)
            ) as c:
                revenue = (await c.fetchone())[0] or 0
            
            # Pending payments
            async with db.execute(
                "SELECT COUNT(*) FROM kaspi_payments WHERE status = 'pending'"
            ) as c:
                pending = (await c.fetchone())[0]
        
        return web.json_response({
            "active_games": len(active_games),
            "total_users": total_users,
            "revenue": revenue,
            "pending_payments": pending,
            "timestamp": datetime.now().isoformat()
        })
    
    async def api_users(self, request: web.Request) -> web.Response:
        """API endpoint for users list."""
        from database import aiosqlite, DB_NAME
        
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT user_id, username, first_name, games_played, gold FROM players ORDER BY games_played DESC LIMIT 50"
            ) as c:
                users = [dict(r) for r in await c.fetchall()]
        
        return web.json_response(users)
    
    async def api_games(self, request: web.Request) -> web.Response:
        """API endpoint for active games."""
        from game_state import active_games
        
        games = []
        for chat_id, game in active_games.items():
            games.append({
                "chat_id": chat_id,
                "players": len(game.players),
                "phase": str(game.phase),
                "pot": game.pot
            })
        
        return web.json_response(games)
    
    async def api_payments(self, request: web.Request) -> web.Response:
        """API endpoint for recent payments."""
        from database import aiosqlite, DB_NAME
        
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT id, user_id, username, amount_kzt, status, created_at 
                   FROM kaspi_payments 
                   ORDER BY created_at DESC LIMIT 20"""
            ) as c:
                payments = [{
                    "id": r['id'],
                    "user": r['username'] or f"User_{r['user_id']}",
                    "amount": r['amount_kzt'],
                    "status": r['status'],
                    "time": r['created_at'][:16] if r['created_at'] else '-'
                } for r in await c.fetchall()]
        
        return web.json_response(payments)
    
    async def api_ban_user(self, request: web.Request) -> web.Response:
        """API endpoint to ban a user."""
        try:
            data = await request.json()
            user_id = data.get('user_id')
            reason = data.get('reason', 'Admin action')
            
            if not user_id:
                return web.json_response({"error": "user_id required"}, status=400)
            
            from anti_cheat import get_anti_cheat
            anti_cheat = get_anti_cheat()
            anti_cheat.ban_user(user_id, reason)
            
            logger.warning(f"🚫 User {user_id} banned via web dashboard: {reason}")
            return web.json_response({"success": True, "user_id": user_id})
            
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)
    
    async def start(self):
        """Start the dashboard server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        
        logger.info(f"📊 Web Dashboard: http://{self.host}:{self.port}")
        logger.info(f"   Username: admin")
    
    async def stop(self):
        """Stop the dashboard server."""
        if self.runner:
            await self.runner.cleanup()
            logger.info("📊 Web Dashboard stopped")
