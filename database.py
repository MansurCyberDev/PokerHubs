import json
import aiosqlite
import asyncio
from datetime import datetime
from typing import Optional, Dict, List

from config import ADMIN_IDS
from skins import SKINS, TABLE_SKINS, CHIP_SKINS

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
            ("chip_skin", "TEXT DEFAULT 'classic'"),
            ("owned_chip_skins", "TEXT DEFAULT '[\"classic\"]'"),
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
                all_chip_skins = list(CHIP_SKINS.keys())
                owned_skins_json = json.dumps(all_card_skins)
                owned_table_skins_json = json.dumps(all_table_skins)
                owned_chip_skins_json = json.dumps(all_chip_skins)
                card_skin = "classic"  # Default active
                table_skin = "classic"  # Default active
                chip_skin = "classic"  # Default active
            else:
                owned_skins_json = '["classic"]'
                owned_table_skins_json = '["classic"]'
                owned_chip_skins_json = '["classic"]'
                card_skin = "classic"
                table_skin = "classic"
                chip_skin = "classic"
            
            await db.execute(
                "INSERT INTO players (user_id, username, first_name, card_skin, table_skin, chip_skin, owned_skins, owned_table_skins, owned_chip_skins) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, username, first_name, card_skin, table_skin, chip_skin, owned_skins_json, owned_table_skins_json, owned_chip_skins_json)
            )
            await db.commit()
            
            result = {
                "user_id": user_id, "username": username, "first_name": first_name,
                "games_played": 0, "games_won": 0, "total_winnings": 0,
                "biggest_win": 0, "current_balance": 1000,
                "gold": 0, "card_skin": card_skin, "table_skin": table_skin, "chip_skin": chip_skin,
                "owned_skins": owned_skins_json, "owned_table_skins": owned_table_skins_json, "owned_chip_skins": owned_chip_skins_json,
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
            all_chip_skins = list(CHIP_SKINS.keys())
            owned_skins_json = json.dumps(all_card_skins)
            owned_table_skins_json = json.dumps(all_table_skins)
            owned_chip_skins_json = json.dumps(all_chip_skins)
            
            current_owned = json.loads(row['owned_skins'] or '["classic"]')
            current_table_owned = json.loads(row['owned_table_skins'] or '["classic"]')
            # Convert row to dict to use .get() method for potentially missing column
            row_dict = dict(row)
            current_chip_owned = json.loads(row_dict.get('owned_chip_skins', None) or '["classic"]')
            
            # If admin doesn't have all skins, grant them
            if (set(current_owned) != set(all_card_skins) or 
                set(current_table_owned) != set(all_table_skins) or
                set(current_chip_owned) != set(all_chip_skins)):
                await db.execute(
                    "UPDATE players SET owned_skins = ?, owned_table_skins = ?, owned_chip_skins = ? WHERE user_id = ?",
                    (owned_skins_json, owned_table_skins_json, owned_chip_skins_json, user_id)
                )
                await db.commit()
                # Update row data
                row = dict(row)
                row['owned_skins'] = owned_skins_json
                row['owned_table_skins'] = owned_table_skins_json
                row['owned_chip_skins'] = owned_chip_skins_json
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


async def buy_chip_skin(user_id: int, skin_id: str, price: int) -> bool:
    """Купить скин фишек за золото. Возвращает True если успешно."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT gold, owned_chip_skins FROM players WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        if not row or row["gold"] < price:
            return False
        owned = json.loads(row["owned_chip_skins"] or '["classic"]')
        if skin_id in owned:
            return False
        owned.append(skin_id)
        await db.execute(
            "UPDATE players SET gold = gold - ?, owned_chip_skins = ?, chip_skin = ? WHERE user_id = ?",
            (price, json.dumps(owned), skin_id, user_id)
        )
        await db.commit()
        return True


async def set_chip_skin(user_id: int, skin_id: str):
    """Установить активный скин фишек"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE players SET chip_skin = ? WHERE user_id = ?", (skin_id, user_id))
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