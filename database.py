import json
import aiosqlite
import asyncio
from datetime import datetime
from typing import Optional, Dict, List

from config import ADMIN_IDS
from skins import SKINS, TABLE_SKINS

DB_NAME = "poker_stats.db"


async def init_db():
    """Инициализация базы данных"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                games_played INTEGER DEFAULT 0,
                games_won INTEGER DEFAULT 0,
                total_winnings INTEGER DEFAULT 0,
                biggest_win INTEGER DEFAULT 0,
                current_balance INTEGER DEFAULT 1000,
                gold INTEGER DEFAULT 0,
                card_skin TEXT DEFAULT 'classic',
                owned_skins TEXT DEFAULT '["classic"]', table_skin TEXT DEFAULT 'classic', owned_table_skins TEXT DEFAULT '["classic"]',
                language TEXT DEFAULT 'ru',
                last_bonus TEXT
            )
        ''')
        # Миграция: добавляем новые поля если они не существуют
        for col, definition in [
            ("gold", "INTEGER DEFAULT 0"),
            ("card_skin", "TEXT DEFAULT 'classic'"),
            ("owned_skins", "TEXT DEFAULT '[\"classic\"]'"),
            ("language", "TEXT DEFAULT 'ru'"),
            ("luck_multiplier", "INTEGER DEFAULT 0"), 
            ("table_skin", "TEXT DEFAULT 'classic'"), 
            ("owned_table_skins", "TEXT DEFAULT '[\"classic\"]'"),
        ]:
            try:
                await db.execute(f"ALTER TABLE players ADD COLUMN {col} {definition}")
            except Exception:
                pass  # Колонка уже существует

        await db.execute('''
            CREATE TABLE IF NOT EXISTS hand_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                hand_data TEXT,
                result TEXT,
                amount INTEGER,
                timestamp TEXT
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS kaspi_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                first_name TEXT,
                item_type TEXT,
                item_id TEXT,
                amount_kzt INTEGER,
                amount_item INTEGER,
                status TEXT DEFAULT 'pending',
                receipt_photo_id TEXT,
                admin_comment TEXT,
                created_at TEXT,
                processed_at TEXT,
                processed_by INTEGER
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS issue_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                first_name TEXT,
                message TEXT,
                status TEXT DEFAULT 'pending',
                admin_reply TEXT,
                created_at TEXT,
                replied_at TEXT,
                replied_by INTEGER
            )
        ''')

        await db.commit()
        
        # Enable WAL mode for better concurrency (high load optimization)
        # WAL allows multiple readers while one writer is active
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("PRAGMA cache_size=-64000")  # 64MB cache
        await db.execute("PRAGMA temp_store=MEMORY")
        await db.commit()


async def get_player(user_id: int, username: str = "", first_name: str = "") -> Dict:
    """Получить или создать игрока"""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
                "SELECT * FROM players WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            # Check if user is admin
            is_admin = user_id in ADMIN_IDS
            
            # For admins, give all skins; for others, only classic
            if is_admin:
                all_card_skins = list(SKINS.keys())
                all_table_skins = list(TABLE_SKINS.keys())
                owned_skins_json = json.dumps(all_card_skins)
                owned_table_skins_json = json.dumps(all_table_skins)
                card_skin = "classic"  # Default active
                table_skin = "classic"  # Default active
            else:
                owned_skins_json = '["classic"]'
                owned_table_skins_json = '["classic"]'
                card_skin = "classic"
                table_skin = "classic"
            
            await db.execute(
                "INSERT INTO players (user_id, username, first_name, card_skin, table_skin, owned_skins, owned_table_skins) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, username, first_name, card_skin, table_skin, owned_skins_json, owned_table_skins_json)
            )
            await db.commit()
            
            result = {
                "user_id": user_id, "username": username, "first_name": first_name,
                "games_played": 0, "games_won": 0, "total_winnings": 0,
                "biggest_win": 0, "current_balance": 1000,
                "gold": 0, "card_skin": card_skin, "table_skin": table_skin,
                "owned_skins": owned_skins_json, "owned_table_skins": owned_table_skins_json,
                "language": "ru", "luck_multiplier": 0
            }
            
            if is_admin:
                # Add extra gold for admins
                await db.execute(
                    "UPDATE players SET gold = gold + 10000 WHERE user_id = ?",
                    (user_id,)
                )
                await db.commit()
                result["gold"] = 10000
            
            return result
        
        # Check if existing player is admin and needs all skins
        is_admin = user_id in ADMIN_IDS
        if is_admin:
            # Ensure admin has all skins
            all_card_skins = list(SKINS.keys())
            all_table_skins = list(TABLE_SKINS.keys())
            owned_skins_json = json.dumps(all_card_skins)
            owned_table_skins_json = json.dumps(all_table_skins)
            
            current_owned = json.loads(row['owned_skins'] or '["classic"]')
            current_table_owned = json.loads(row['owned_table_skins'] or '["classic"]')
            
            # If admin doesn't have all skins, grant them
            if (set(current_owned) != set(all_card_skins) or 
                set(current_table_owned) != set(all_table_skins)):
                await db.execute(
                    "UPDATE players SET owned_skins = ?, owned_table_skins = ? WHERE user_id = ?",
                    (owned_skins_json, owned_table_skins_json, user_id)
                )
                await db.commit()
                # Update row data
                row = dict(row)
                row['owned_skins'] = owned_skins_json
                row['owned_table_skins'] = owned_table_skins_json
                return row
        
        # Обновляем имя, если оно изменилось
        if (username and row['username'] != username) or (first_name and row['first_name'] != first_name):
            await db.execute(
                "UPDATE players SET username = ?, first_name = ? WHERE user_id = ?",
                (username, first_name, user_id)
            )
            await db.commit()
            d_row = dict(row)
            d_row['username'] = username
            d_row['first_name'] = first_name
            return d_row

        return dict(row)


async def update_stats(user_id: int, won: bool = False, amount: int = 0):
    """Обновить статистику после игры"""
    async with aiosqlite.connect(DB_NAME) as db:
        if won:
            await db.execute('''
                UPDATE players 
                SET games_played = games_played + 1,
                    games_won = games_won + 1,
                    total_winnings = total_winnings + ?,
                    biggest_win = MAX(biggest_win, ?),
                    current_balance = current_balance + ?
                WHERE user_id = ?
            ''', (amount, amount, amount, user_id))
        else:
            await db.execute('''
                UPDATE players 
                SET games_played = games_played + 1,
                    current_balance = current_balance - ?
                WHERE user_id = ?
            ''', (amount, user_id))
        await db.commit()


async def add_gold(user_id: int, amount: int):
    """Добавить золото игроку (за покупку через Telegram Stars)"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE players SET gold = gold + ? WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()


async def add_coins(user_id: int, amount: int):
    """Добавить/убавить фишки игроку. amount может быть отрицательным."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE players SET current_balance = MAX(0, current_balance + ?) WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()


async def set_luck_multiplier(user_id: int, percent: int):
    """Установить шанс-буст комбинаций в процентах [0..100]."""
    value = max(0, min(100, int(percent)))
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE players SET luck_multiplier = ? WHERE user_id = ?",
            (value, user_id)
        )
        await db.commit()


async def player_exists(user_id: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT 1 FROM players WHERE user_id = ? LIMIT 1", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row is not None


async def buy_skin(user_id: int, skin_id: str, price: int) -> bool:
    """Купить скин за золото. Возвращает True если успешно."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT gold, owned_skins FROM players WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        if not row or row["gold"] < price:
            return False
        owned = json.loads(row["owned_skins"] or '["classic"]')
        if skin_id in owned:
            return False  # Уже есть
        owned.append(skin_id)
        await db.execute(
            "UPDATE players SET gold = gold - ?, owned_skins = ?, card_skin = ? WHERE user_id = ?",
            (price, json.dumps(owned), skin_id, user_id)
        )
        await db.commit()
        return True


async def buy_table_skin(user_id: int, skin_id: str, price: int) -> bool:
    """Купить скин стола за золото. Возвращает True если успешно."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT gold, owned_table_skins FROM players WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        if not row or row["gold"] < price:
            return False
        owned = json.loads(row["owned_table_skins"] or '["classic"]')
        if skin_id in owned:
            return False
        owned.append(skin_id)
        await db.execute(
            "UPDATE players SET gold = gold - ?, owned_table_skins = ?, table_skin = ? WHERE user_id = ?",
            (price, json.dumps(owned), skin_id, user_id)
        )
        await db.commit()
        return True


async def set_table_skin(user_id: int, skin_id: str):
    """Установить активный скин стола"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE players SET table_skin = ? WHERE user_id = ?", (skin_id, user_id))
        await db.commit()


async def set_skin(user_id: int, skin_id: str):
    """Установить активный скин"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE players SET card_skin = ? WHERE user_id = ?", (skin_id, user_id))
        await db.commit()


async def set_language(user_id: int, lang: str):
    """Установить язык игрока"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE players SET language = ? WHERE user_id = ?", (lang, user_id))
        await db.commit()


async def get_leaderboard(limit: int = 10) -> List[Dict]:
    """Топ игроков по победам"""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT username, first_name, games_won, total_winnings 
            FROM players 
            ORDER BY games_won DESC 
            LIMIT ?
        ''', (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


# ==================== KASPI PAYMENTS ====================

KASPI_PRICES = {
    # Gold packages - основная валюта для покупки через Kaspi
    "gold_100": {"amount": 100, "price_kzt": 100, "name": "100 Gold"},
    "gold_200": {"amount": 200, "price_kzt": 150, "name": "200 Gold"},
    "gold_300": {"amount": 300, "price_kzt": 200, "name": "300 Gold"},
    "gold_500": {"amount": 500, "price_kzt": 300, "name": "500 Gold (экономия 100₸)"},
    "gold_1000": {"amount": 1000, "price_kzt": 550, "name": "1000 Gold (экономия 450₸)"},
    "gold_2000": {"amount": 2000, "price_kzt": 1000, "name": "2000 Gold (экономия 1000₸)"},
    # Фишки через Kaspi (альтернативный способ)
    "chips_10k": {"amount": 10000, "price_kzt": 100, "name": "10 000 фишек"},
    "chips_25k": {"amount": 25000, "price_kzt": 150, "name": "25 000 фишек"},
    "chips_50k": {"amount": 50000, "price_kzt": 250, "name": "50 000 фишек"},
}

async def create_kaspi_payment(user_id: int, username: str, first_name: str, 
                                item_type: str, item_id: str, 
                                amount_kzt: int, amount_item: int) -> int:
    """Создать новый платёж. Возвращает ID платежа."""
    from datetime import datetime
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('''
            INSERT INTO kaspi_payments (user_id, username, first_name, item_type, item_id,
                                       amount_kzt, amount_item, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        ''', (user_id, username, first_name, item_type, item_id, 
              amount_kzt, amount_item, datetime.now().isoformat()))
        await db.commit()
        return cursor.lastrowid


async def get_kaspi_payment(payment_id: int) -> Optional[Dict]:
    """Получить информацию о платеже по ID"""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM kaspi_payments WHERE id = ?", (payment_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_pending_payments() -> List[Dict]:
    """Получить все ожидающие платежи для админ-панели"""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT * FROM kaspi_payments 
            WHERE status = 'pending' 
            ORDER BY created_at DESC
        ''') as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_user_payments(user_id: int, limit: int = 10) -> List[Dict]:
    """Получить историю платежей пользователя"""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT * FROM kaspi_payments 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (user_id, limit)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def add_receipt_to_payment(payment_id: int, photo_file_id: str) -> bool:
    """Добавить чек к существующему платежу"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE kaspi_payments SET receipt_photo_id = ? WHERE id = ?",
            (photo_file_id, payment_id)
        )
        await db.commit()
        return True


async def approve_kaspi_payment(payment_id: int, admin_id: int, 
                                admin_comment: str = "") -> Optional[Dict]:
    """Одобрить платёж и начислить товар. Возвращает информацию о платеже."""
    from datetime import datetime
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        
        # Получаем платёж
        async with db.execute(
            "SELECT * FROM kaspi_payments WHERE id = ? AND status = 'pending'",
            (payment_id,)
        ) as cursor:
            payment = await cursor.fetchone()
        
        if not payment:
            return None
        
        payment = dict(payment)
        
        # Начисляем товар
        if payment['item_type'] == 'chips':
            await db.execute(
                "UPDATE players SET current_balance = current_balance + ? WHERE user_id = ?",
                (payment['amount_item'], payment['user_id'])
            )
        elif payment['item_type'] == 'gold':
            await db.execute(
                "UPDATE players SET gold = gold + ? WHERE user_id = ?",
                (payment['amount_item'], payment['user_id'])
            )
        elif payment['item_type'] == 'card_skin':
            # Добавляем скин в owned_skins и устанавливаем активным
            await db.execute('''
                UPDATE players 
                SET owned_skins = json_insert(owned_skins, '$[#]', ?),
                    card_skin = ?
                WHERE user_id = ?
            ''', (payment['item_id'], payment['item_id'], payment['user_id']))
        elif payment['item_type'] == 'table_skin':
            await db.execute('''
                UPDATE players 
                SET owned_table_skins = json_insert(owned_table_skins, '$[#]', ?),
                    table_skin = ?
                WHERE user_id = ?
            ''', (payment['item_id'], payment['item_id'], payment['user_id']))
        
        # Обновляем статус платежа
        await db.execute('''
            UPDATE kaspi_payments 
            SET status = 'approved', 
                processed_at = ?, 
                processed_by = ?,
                admin_comment = ?
            WHERE id = ?
        ''', (datetime.now().isoformat(), admin_id, admin_comment, payment_id))
        
        await db.commit()
        
        # Возвращаем обновлённый платёж
        async with db.execute("SELECT * FROM kaspi_payments WHERE id = ?", (payment_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def reject_kaspi_payment(payment_id: int, admin_id: int, 
                               reason: str) -> bool:
    """Отклонить платёж с причиной"""
    from datetime import datetime
    async with aiosqlite.connect(DB_NAME) as db:
        result = await db.execute('''
            UPDATE kaspi_payments 
            SET status = 'rejected', 
                processed_at = ?, 
                processed_by = ?,
                admin_comment = ?
            WHERE id = ? AND status = 'pending'
        ''', (datetime.now().isoformat(), admin_id, reason, payment_id))
        await db.commit()
        return result.rowcount > 0


async def get_payment_stats() -> Dict:
    """Статистика платежей для админ-панели"""
    async with aiosqlite.connect(DB_NAME) as db:
        # Всего заявок
        async with db.execute("SELECT COUNT(*) FROM kaspi_payments") as cursor:
            total = (await cursor.fetchone())[0]
        
        # Ожидают
        async with db.execute("SELECT COUNT(*) FROM kaspi_payments WHERE status = 'pending'") as cursor:
            pending = (await cursor.fetchone())[0]
        
        # Одобрено
        async with db.execute("SELECT COUNT(*) FROM kaspi_payments WHERE status = 'approved'") as cursor:
            approved = (await cursor.fetchone())[0]
        
        # Отклонено
        async with db.execute("SELECT COUNT(*) FROM kaspi_payments WHERE status = 'rejected'") as cursor:
            rejected = (await cursor.fetchone())[0]
        
        # Сумма одобренных платежей
        async with db.execute("SELECT SUM(amount_kzt) FROM kaspi_payments WHERE status = 'approved'") as cursor:
            total_revenue = (await cursor.fetchone())[0] or 0
        
        return {
            "total": total,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "total_revenue_kzt": total_revenue
        }


# ==================== ISSUE MESSAGES ====================

async def save_issue_message(user_id: int, username: str, first_name: str, message: str) -> int:
    """Save issue message to database and return issue ID"""
    from datetime import datetime
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('''
            INSERT INTO issue_messages (user_id, username, first_name, message, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
        ''', (user_id, username, first_name, message, datetime.now().isoformat()))
        await db.commit()
        return cursor.lastrowid


async def get_pending_issues() -> List[Dict]:
    """Get all pending issue messages for admin panel"""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT * FROM issue_messages 
            WHERE status = 'pending' 
            ORDER BY created_at DESC
        ''') as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_issue(issue_id: int) -> Optional[Dict]:
    """Get issue message by ID"""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM issue_messages WHERE id = ?", (issue_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def reply_to_issue(issue_id: int, admin_id: int, reply_text: str) -> bool:
    """Mark issue as replied with admin response"""
    from datetime import datetime
    async with aiosqlite.connect(DB_NAME) as db:
        result = await db.execute('''
            UPDATE issue_messages 
            SET status = 'replied', 
                replied_at = ?, 
                replied_by = ?,
                admin_reply = ?
            WHERE id = ? AND status = 'pending'
        ''', (datetime.now().isoformat(), admin_id, reply_text, issue_id))
        await db.commit()
        return result.rowcount > 0


async def get_issue_stats() -> Dict:
    """Get statistics about issue messages"""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM issue_messages") as cursor:
            total = (await cursor.fetchone())[0]
        
        async with db.execute("SELECT COUNT(*) FROM issue_messages WHERE status = 'pending'") as cursor:
            pending = (await cursor.fetchone())[0]
        
        async with db.execute("SELECT COUNT(*) FROM issue_messages WHERE status = 'replied'") as cursor:
            replied = (await cursor.fetchone())[0]
        
        return {
            "total": total,
            "pending": pending,
            "replied": replied
        }