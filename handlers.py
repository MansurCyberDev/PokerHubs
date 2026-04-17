import asyncio
from asyncio import CancelledError
import json
import aiosqlite
from typing import Optional
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import RetryAfter, BadRequest

from game_state import Game, Player, GamePhase, active_games, TURN_TIME
from database import (
    get_player, update_stats, init_db, add_gold, buy_skin, set_skin, 
    buy_table_skin, set_table_skin, set_language, player_exists,
    add_coins, set_luck_multiplier, DB_NAME
)
from keyboards import (
    get_registration_keyboard, get_bet_amounts_keyboard,
    get_main_menu_keyboard, get_profile_keyboard, get_shop_keyboard, get_shop_categories_keyboard, get_table_skins_keyboard, get_gold_packages_keyboard, get_chips_packages_keyboard, get_language_keyboard, get_inventory_categories_keyboard,
    get_blinds_keyboard, get_seats_keyboard, get_play_again_keyboard,
    get_turn_reply_keyboard
)
from utils import (
    format_table, format_cards, get_mention,
    send_cards_photo,
    card_image_path, back_image_path,
    build_poker_table_image_bytes, send_buffered_photo,
    format_timer_bar, get_dealing_animation, get_all_in_effect,
    get_win_effect, get_bad_beat_effect, get_chip_sound_emoji,
    get_applause_animation, get_timer_tick_emoji, format_mini_table_map
)
from cards import HandEvaluator
from skins import SKINS, DEFAULT_SKIN, TABLE_SKINS, DEFAULT_TABLE_SKIN
from config import MIN_PLAYERS, REGISTRATION_TIME, SMALL_BLIND, BIG_BLIND, ADMIN_IDS, SUPPORT_USERNAME

# user_id -> active game chat_id (для работы кнопок из ЛС)
user_active_games = {}
# user_id -> last DM prompt message_id (чтобы удалять старые кнопки)
user_last_dm_prompt = {}
# user_id -> last bet selection message_id
user_last_bet_prompt = {}
# user_id -> last hand photo message_id
user_last_hand_message = {}
# user_id -> last board photo message_id
user_last_board_message = {}
# user_id -> last main menu message_id
user_last_menu_message = {}

# Global cache for video duration and ad rate limiting
_video_duration_cache = None
_video_duration_lock = asyncio.Lock()
_ad_rate_limits = {}
_daily_bonus_limits = {}  # user_id -> last_claim_timestamp
_daily_bonus_lock = asyncio.Lock()

# Rate limiting for ad watching: user_id -> last watch timestamp
_ad_rate_limit_lock = asyncio.Lock()

# Cooldown between ad watches (seconds)
AD_COOLDOWN_SECONDS = 60

CREATOR_ONLY_ALERT = "Только создатель может изменять параметры игры и запускать её."


async def _get_video_duration(video_path: str) -> float:
    """Get video duration using ffprobe with caching (async-safe)"""
    global _video_duration_cache
    if _video_duration_cache is not None:
        return _video_duration_cache
    
    import subprocess
    try:
        # Run ffprobe in thread pool to avoid blocking event loop
        def run_ffprobe():
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
                 '-of', 'default=noprint_wrappers=1:nokey=1', video_path],
                capture_output=True, text=True, timeout=5
            )
            return float(result.stdout.strip()) if result.returncode == 0 else 30.0
        
        _video_duration_cache = await asyncio.to_thread(run_ffprobe)
        return _video_duration_cache
    except Exception:
        return 30.0


async def _compress_video(video_path: str, output_path: str, target_size_mb: int = 15) -> bool:
    """Compress video using ffmpeg to target size. Returns True if successful."""
    import subprocess
    import os
    
    try:
        # Get original video info
        def get_video_info():
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'v:0', 
                 '-show_entries', 'stream=bit_rate,duration', 
                 '-of', 'default=noprint_wrappers=1:nokey=1', video_path],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip().split('\n')
        
        info = await asyncio.to_thread(get_video_info)
        
        # Calculate target bitrate for desired file size
        # Formula: (target_size_mb * 8 * 1024 * 1024) / duration_seconds = bitrate_bps
        duration = await _get_video_duration(video_path)
        if duration <= 0:
            duration = 30.0
        
        # Target: 15MB max, leave some headroom for audio
        target_video_bitrate = int((target_size_mb * 7 * 1024 * 1024) / duration)
        target_video_bitrate = max(target_video_bitrate, 500000)  # Min 500kbps
        target_video_bitrate = min(target_video_bitrate, 4000000)  # Max 4Mbps
        
        print(f"DEBUG: Compressing video to ~{target_size_mb}MB, target bitrate: {target_video_bitrate}bps")
        
        # Compress with ffmpeg
        def run_ffmpeg():
            result = subprocess.run([
                'ffmpeg', '-y', '-i', video_path,
                '-c:v', 'libx264', '-preset', 'fast',
                '-b:v', f'{target_video_bitrate}',
                '-maxrate', f'{target_video_bitrate * 1.5}',
                '-bufsize', f'{target_video_bitrate * 2}',
                '-c:a', 'aac', '-b:a', '128k',
                '-movflags', '+faststart',
                '-vf', 'scale=1080:1920:force_original_aspect_ratio=decrease',
                output_path
            ], capture_output=True, text=True, timeout=120)
            return result.returncode == 0
        
        success = await asyncio.to_thread(run_ffmpeg)
        
        if success and os.path.exists(output_path):
            original_size = os.path.getsize(video_path) / (1024 * 1024)
            compressed_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"DEBUG: Video compressed: {original_size:.1f}MB -> {compressed_size:.1f}MB")
            return True
        return False
        
    except Exception as e:
        print(f"DEBUG: Video compression failed: {e}")
        return False


async def _check_ad_rate_limit(user_id: int) -> tuple[bool, int]:
    """Check if user can watch ad again. Returns (allowed, seconds_remaining)."""
    global _ad_rate_limits
    from time import time
    
    last_watch = _ad_rate_limits.get(user_id, 0)
    current_time = int(time())
    cooldown = 86400  # 24 hours = 86400 seconds (once per day)
    
    if current_time - last_watch < cooldown:
        return False, cooldown - (current_time - last_watch)
    
    _ad_rate_limits[user_id] = current_time
    # Cleanup old entries (older than 48 hours to be safe)
    cutoff = current_time - 172800
    _ad_rate_limits = {uid: ts for uid, ts in _ad_rate_limits.items() if ts > cutoff}
    
    return True, 0


async def _check_daily_bonus_limit(user_id: int) -> tuple[bool, int]:
    """Check if user can claim daily bonus. Returns (allowed, seconds_remaining)."""
    global _daily_bonus_limits
    from time import time
    
    last_claim = _daily_bonus_limits.get(user_id, 0)
    current_time = int(time())
    cooldown = 86400  # 24 hours = 86400 seconds (once per day)
    
    if current_time - last_claim < cooldown:
        return False, cooldown - (current_time - last_claim)
    
    _daily_bonus_limits[user_id] = current_time
    # Cleanup old entries (older than 48 hours to be safe)
    cutoff = current_time - 172800
    _daily_bonus_limits = {uid: ts for uid, ts in _daily_bonus_limits.items() if ts > cutoff}
    
    return True, 0


async def _user_lang(user_id: int) -> str:
    data = await get_player(user_id)
    lang = (data.get("language") or "ru").lower()
    return "en" if lang == "en" else "ru"


async def delete_message_safe(bot, chat_id: int, message_id):
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def clear_dm_ui(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    remove_prompt: bool = True,
    remove_bet_prompt: bool = True,
    remove_hand: bool = False,
    remove_board: bool = False,
):
    if remove_prompt:
        await delete_message_safe(context.bot, user_id, user_last_dm_prompt.pop(user_id, None))
    if remove_bet_prompt:
        await delete_message_safe(context.bot, user_id, user_last_bet_prompt.pop(user_id, None))
    if remove_hand:
        await delete_message_safe(context.bot, user_id, user_last_hand_message.pop(user_id, None))
    if remove_board:
        await delete_message_safe(context.bot, user_id, user_last_board_message.pop(user_id, None))


def cleanup_user_data(user_id: int):
    """Clean up user data dictionaries to prevent memory leaks"""
    user_active_games.pop(user_id, None)
    user_last_dm_prompt.pop(user_id, None)
    user_last_bet_prompt.pop(user_id, None)
    user_last_hand_message.pop(user_id, None)
    user_last_board_message.pop(user_id, None)
    user_last_menu_message.pop(user_id, None)


# Navigation history management
NAV_STACK_KEY = "nav_stack"
MAX_NAV_HISTORY = 10


def get_nav_stack(context: ContextTypes.DEFAULT_TYPE) -> list:
    """Get user's navigation history stack"""
    return context.user_data.get(NAV_STACK_KEY, [])


def push_nav_stack(context: ContextTypes.DEFAULT_TYPE, page: str):
    """Push a page onto navigation stack"""
    stack = get_nav_stack(context)
    # Don't push if same as current top
    if stack and stack[-1] == page:
        return
    stack.append(page)
    # Limit stack size
    if len(stack) > MAX_NAV_HISTORY:
        stack.pop(0)
    context.user_data[NAV_STACK_KEY] = stack


def pop_nav_stack(context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
    """Pop current page and return previous page"""
    stack = get_nav_stack(context)
    if not stack:
        return None
    # Remove current page
    stack.pop()
    context.user_data[NAV_STACK_KEY] = stack
    # Return new current page (previous)
    return stack[-1] if stack else None


def get_current_page(context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
    """Get current page from navigation stack"""
    stack = get_nav_stack(context)
    return stack[-1] if stack else None


def clear_nav_stack(context: ContextTypes.DEFAULT_TYPE):
    """Clear navigation history"""
    context.user_data[NAV_STACK_KEY] = []


def has_nav_history(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if there's navigation history (more than just current page)"""
    stack = get_nav_stack(context)
    return len(stack) > 1


async def maybe_restore_private_menu(context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int):
    # Главное меню теперь вызывается через Telegram Menu (/команды), без reply-клавиатуры.
    return


def _ordered_players(game: Game, anchor_user_id: Optional[int] = None):
    players = list(game.players)
    if anchor_user_id is None or not players:
        return players
    start_idx = next((i for i, p in enumerate(players) if p.user_id == anchor_user_id), None)
    if start_idx is None:
        return players
    return players[start_idx:] + players[:start_idx]


def _hidden_card_paths():
    hidden = back_image_path("back03") or back_image_path("back04")
    return [hidden, hidden]


def _table_board_paths(game: Game, skin_id: str = DEFAULT_SKIN):
    hidden = back_image_path("back03") or back_image_path("back04")
    paths = []
    for idx in range(5):
        if idx < len(game.community_cards):
            path = card_image_path(game.community_cards[idx], skin_id) or hidden
        else:
            path = hidden
        paths.append(path)
    return paths


def _table_seat_items(game: Game, reveal_all: bool = False, viewer_user_id: Optional[int] = None):
    hidden = back_image_path("back03") or back_image_path("back04")
    items = []
    for player in _ordered_players(game, viewer_user_id):
        show_cards = reveal_all or (viewer_user_id is not None and player.user_id == viewer_user_id)
        card_paths = []
        if show_cards:
            for card in player.hand[:2]:
                card_paths.append(card_image_path(card, player.card_skin) or hidden)
        else:
            card_paths = [hidden, hidden]
        if len(card_paths) < 2:
            card_paths = [hidden, hidden]
        items.append({
            "name": player.first_name,
            "cards": card_paths[:2],
        })
    return items


async def send_group_table_snapshot(context: ContextTypes.DEFAULT_TYPE, game: Game, caption: str, reveal_all: bool = False):
    # Use the first active player's table skin, or default
    table_skin = "classic"
    for player in game.players:
        if player.is_active and not player.folded:
            table_skin = getattr(player, 'table_skin', 'classic') or 'classic'
            break
    
    img = build_poker_table_image_bytes(
        _table_seat_items(game, reveal_all=reveal_all),
        _table_board_paths(game, DEFAULT_SKIN),
        text="PokerHubs",
        table_skin=table_skin
    )
    if img is None:
        return None
    return await send_buffered_photo(context.bot, game.chat_id, img, caption=caption, parse_mode=ParseMode.HTML)


async def send_private_table_snapshot(context: ContextTypes.DEFAULT_TYPE, game: Game, player: Player, caption: str):
    table_skin = getattr(player, 'table_skin', 'classic') or 'classic'
    
    img = build_poker_table_image_bytes(
        _table_seat_items(game, viewer_user_id=player.user_id),
        _table_board_paths(game, player.card_skin),
        text="PokerHubs",
        table_skin=table_skin
    )
    if img is None:
        return None
    return await send_buffered_photo(context.bot, player.user_id, img, caption=caption, parse_mode=ParseMode.HTML)


async def refresh_registration_message(context: ContextTypes.DEFAULT_TYPE, game: Game):
    players_list = ", ".join([p.first_name for p in game.players])
    text = (
        f"🎰 <b>Новый стол PokerHubs</b>\n\n"
        f"💵 Блайнды: {game.small_blind}/{game.big_blind}\n"
        f"👥 Мест за столом: {game.max_players}\n"
        f"👤 Создатель: {game.players[0].first_name}\n\n"
        f"⏳ Регистрация открыта\n"
        f"Игроки ({len(game.players)}): {players_list}"
    )
    if game.registration_message_id:
        try:
            await context.bot.edit_message_text(
                text=text,
                chat_id=game.chat_id,
                message_id=game.registration_message_id,
                reply_markup=get_registration_keyboard(),
                parse_mode=ParseMode.HTML
            )
            return
        except Exception:
            pass
    msg = await context.bot.send_message(
        game.chat_id,
        text,
        reply_markup=get_registration_keyboard(),
        parse_mode=ParseMode.HTML
    )
    game.registration_message_id = msg.message_id


async def safe_send_message(bot, chat_id: int, *args, **kwargs):
    max_retries = 3
    retries = 0
    while retries < max_retries:
        try:
            return await bot.send_message(chat_id, *args, **kwargs)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
            retries += 1
        except Exception as e:
            print(f"Error in safe_send_message: {e}")
            retries += 1
            if retries >= max_retries:
                raise
    return None


async def safe_edit_message_text(query, text: str, reply_markup=None, parse_mode=None):
    try:
        return await query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return None
        # Handle video/photo messages that have caption instead of text
        if "no text in the message" in str(e).lower() or "no caption in the message" in str(e).lower():
            try:
                return await query.edit_message_caption(
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            except BadRequest as e2:
                if "Message is not modified" in str(e2):
                    return None
                raise
        raise


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    player_data = await get_player(user.id, user.username, user.first_name)
    lang = "en" if (player_data.get("language") or "ru") == "en" else "ru"
    
    # Clear navigation history when starting fresh
    clear_nav_stack(context)
    
    # Если команда в ЛС — показываем главное меню
    if update.effective_chat.type == "private":
        bot_username = context.bot.username or ""
        skin_name = SKINS.get(player_data.get('card_skin', 'classic'), SKINS['classic'])['name']
        if lang == "en":
            text = (
                f"👋 <b>Welcome to Poker Hub, {user.first_name}!</b>\n"
                f"✨ •═════════════════════• ✨\n\n"
                f"🎰 <b>Your Account</b>\n"
                f"💰 <b>Chips:</b> {player_data['current_balance']}\n"
                f"💎 <b>Gold:</b> {player_data.get('gold', 0)}\n"
                f"🃏 <b>Deck:</b> {skin_name}\n\n"
                f"🚀 <b>Quick Start</b>\n"
                f"▶️ Add bot to group and start playing!\n"
                f"ℹ️ Need help? Use /rules"
            )
        else:
            text = (
                f"👋 <b>Добро пожаловать в Poker Hub, {user.first_name}!</b>\n"
                f"✨ •═════════════════════• ✨\n\n"
                f"🎰 <b>Ваш аккаунт</b>\n"
                f"💰 <b>Фишки:</b> {player_data['current_balance']}\n"
                f"💎 <b>Золото:</b> {player_data.get('gold', 0)}\n"
                f"🃏 <b>Колода:</b> {skin_name}\n\n"
                f"🚀 <b>Быстрый старт</b>\n"
                f"▶️ Добавь бота в группу и начни играть!\n"
                f"ℹ️ Нужна помощь? Используй /rules"
            )
        await update.message.reply_text(
            text,
            reply_markup=get_main_menu_keyboard(bot_username, lang=lang),
            parse_mode=ParseMode.HTML
        )
    else:
        # в группе — простой ответ
        await update.message.reply_text(
            f"👋 {user.first_name}! Пиши мне в ЛС, чтобы управлять профилем! Для новой игры используй /game",
            parse_mode=ParseMode.HTML
        )


async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shop command handler - opens the shop menu with navigation tracking."""
    user = update.effective_user
    player_data = await get_player(user.id, user.username, user.first_name)
    lang = "en" if (player_data.get("language") or "ru") == "en" else "ru"
    
    # Track navigation to shop
    push_nav_stack(context, "menu_shop")
    
    text = (
        f"🛒 <b>SKIN SHOP</b>\n════════════════════\n\n"
        f"Welcome to the shop! Here you can buy skins for cards and tables.\n\n"
        f"🃏 Card Skins — customize your cards!\n"
        f"🎰 Table Skins — change the table look!\n"
        f"💰 Buy Chips — get more chips for the game!"
        if lang == "en" else
        f"🛒 <b>МАГАЗИН СКИНОВ</b>\n════════════════════\n\n"
        f"Добро пожаловать в магазин! Здесь ты можешь купить скины для карт и столов.\n\n"
        f"🃏 Скины карт — кастомизируй карты!\n"
        f"🎰 Скины столов — меняй вид стола!\n"
        f"💰 Купить фишки — получи больше фишек для игры!"
    )
    
    # Add back button if user came from another page (has history)
    back_button = InlineKeyboardButton("🔙 " + ("Back" if lang == "en" else "Назад"), callback_data="menu_back") if has_nav_history(context) else None
    
    await update.message.reply_text(
        text,
        reply_markup=get_shop_categories_keyboard(lang=lang, back_button=back_button),
        parse_mode=ParseMode.HTML
    )


async def create_game(chat_id: int, user, context: ContextTypes.DEFAULT_TYPE):
    # Cancel any existing registration task for this chat first
    if chat_id in active_games:
        existing_game = active_games[chat_id]
        if existing_game.registration_task:
            try:
                existing_game.registration_task.cancel()
            except Exception:
                pass
            existing_game.registration_task = None
    
    game = Game(chat_id=chat_id)
    game.id = int(asyncio.get_event_loop().time() * 1000)
    active_games[chat_id] = game

    player_data = await get_player(user.id, user.username, user.first_name)
    creator = Player(
        user_id=user.id,
        username=user.username or "",
        first_name=user.first_name,
        stack=player_data['current_balance'],
        card_skin=player_data.get('card_skin', DEFAULT_SKIN),
        table_skin=player_data.get('table_skin', DEFAULT_TABLE_SKIN),
        luck_multiplier=player_data.get('luck_multiplier', 0)
    )
    game.players.append(creator)
    user_active_games[user.id] = chat_id

    msg = await context.bot.send_message(
        chat_id,
        f"🎰 <b>Новый стол PokerHubs</b>\n\n"
        f"💵 Блайнды: <b>{game.small_blind}/{game.big_blind}</b>\n"
        f"👥 Мест за столом: <b>{game.max_players}</b>\n"
        f"👤 Создатель: {get_mention(user.id, user.first_name)}\n\n"
        f"⏳ Регистрация открыта\n"
        f"👥 Игроки (1): <i>{user.first_name}</i>",
        reply_markup=get_registration_keyboard(),
        parse_mode=ParseMode.HTML
    )
    game.registration_message_id = msg.message_id

    async def close_registration():
        game_id = game.id
        try:
            await asyncio.sleep(REGISTRATION_TIME)
        except asyncio.CancelledError:
            return  # Task was cancelled, exit gracefully
        
        if chat_id in active_games and active_games[chat_id].id == game_id and game.phase == GamePhase.WAITING:
            if len(game.players) < MIN_PLAYERS:
                await context.bot.send_message(
                    chat_id,
                    "❌ Недостаточно игроков. Игра отменена."
                )
                if active_games.get(chat_id) and active_games[chat_id].id == game_id:
                    del active_games[chat_id]
            else:
                await start_game(context, chat_id)

    game.registration_task = asyncio.create_task(close_registration())
    return game


async def game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    message = update.effective_message

    # Check if command is used in private chat
    if update.effective_chat.type == "private":
        lang = await _user_lang(user.id)
        await message.reply_text(
            "Use this command in a group chat." if lang == "en" else "Используйте эту команду в групповом чате."
        )
        return

    if chat_id in active_games:
        existing = active_games[chat_id]
        # Если игра уже завершена/в ожидании без регистрации — позволяем стартовать заново
        if existing.phase == GamePhase.WAITING and (existing.registration_task is None or existing.registration_task.done()):
            del active_games[chat_id]
        else:
            await message.reply_text("❌ Игра уже идет в этом чате!")
            return

    await create_game(chat_id, user, context)


async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id not in active_games or active_games[chat_id].registration_message_id != query.message.message_id:
        await query.answer("❌ Эта регистрация уже неактуальна", show_alert=True)
        return

    game = active_games[chat_id]

    if game.phase != GamePhase.WAITING:
        await query.answer("Игра уже началась!", show_alert=True)
        return

    if any(p.user_id == user.id for p in game.players):
        await query.answer("Ты уже в игре!", show_alert=True)
        return

    if len(game.players) >= game.max_players:
        await query.answer("Свободных мест за столом нет.", show_alert=True)
        return

    player_data = await get_player(user.id, user.username, user.first_name)
    if player_data['current_balance'] < game.big_blind * 10:
        await query.answer("Недостаточно фишек для игры!", show_alert=True)
        return

    new_player = Player(
        user_id=user.id,
        username=user.username or "",
        first_name=user.first_name,
        stack=player_data['current_balance'],
        card_skin=player_data.get('card_skin', DEFAULT_SKIN),
        table_skin=player_data.get('table_skin', DEFAULT_TABLE_SKIN),
        luck_multiplier=player_data.get('luck_multiplier', 0)
    )
    game.players.append(new_player)
    user_active_games[user.id] = chat_id

    await refresh_registration_message(context, game)

    # Пингуем игрока в ЛС, чтобы он открыл чат с ботом
    try:
        await context.bot.send_message(
            user.id,
            "✅ Ты сел за стол.\nКогда игра начнётся, действия придут сюда.",
            parse_mode=ParseMode.HTML
        )
    except Exception:
        await context.bot.send_message(
            chat_id,
            f"⚠️ {get_mention(user.id, user.first_name)} — открой ЛС с ботом и нажми /start (Open bot DM and press /start), иначе не будет кнопок!",
            parse_mode=ParseMode.HTML
        )


async def start_early_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id

    if chat_id not in active_games:
        await query.answer("Игра не найдена или уже завершена", show_alert=True)
        return

    game = active_games[chat_id]

    if update.effective_user.id != game.players[0].user_id:
        await query.answer(CREATOR_ONLY_ALERT, show_alert=True)
        return

    if len(game.players) >= MIN_PLAYERS:
        if game.registration_task:
            game.registration_task.cancel()
        await start_game(context, chat_id)
    else:
        await query.answer("Недостаточно игроков!", show_alert=True)


async def start_game(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    game = active_games[chat_id]

    if game.registration_task:
        try:
            game.registration_task.cancel()
        except Exception:
            pass
        game.registration_task = None

    # Удаляем сообщения лобби
    await delete_message_safe(context.bot, chat_id, game.registration_message_id)
    game.registration_message_id = None
    await delete_message_safe(context.bot, chat_id, game.lobby_settings_message_id)
    game.lobby_settings_message_id = None

    # Проверка бай-ина перед стартом - обновляем стеки из БД
    to_remove = []
    for p in game.players:
        p_data = await get_player(p.user_id)
        # Обновляем стек из актуального баланса БД
        p.stack = p_data['current_balance']
        if p_data['current_balance'] < game.big_blind:
            to_remove.append(p)
    
    for p in to_remove:
        game.players.remove(p)
        await context.bot.send_message(chat_id, f"❌ {p.first_name} исключен: недостаточно фишек для блайндов ({game.big_blind}).")

    if len(game.players) < MIN_PLAYERS:
        await context.bot.send_message(chat_id, "❌ Игра отменена: недостаточно игроков после проверки стеков.")
        del active_games[chat_id]
        return

    game.phase = GamePhase.PREFLOP
    game.deal_hole_cards()
    game.post_blinds()

    # Send admin list of all player IDs
    for player in game.players:
        if _is_admin(player.user_id):
            player_ids_text = "👥 <b>Player IDs in this game:</b>\n"
            for p in game.players:
                player_ids_text += f"• <code>{p.user_id}</code> — {p.first_name}\n"
            try:
                await context.bot.send_message(
                    player.user_id,
                    player_ids_text,
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass  # Admin may not have started DM with bot
            break  # Only need to send to one admin

    for player in game.players:
        if not player.is_active:
            continue

        user_active_games[player.user_id] = chat_id
        lang = await _user_lang(player.user_id)

        try:
            caption = "🎰 <b>Your cards</b>\nGood luck!" if lang == "en" else "🎰 <b>Твои карты</b>\nУдачи!"
            # удаляем прошлую руку, чтобы не копить фото
            last_hand = user_last_hand_message.get(player.user_id)
            if last_hand:
                try:
                    await context.bot.delete_message(player.user_id, last_hand)
                except Exception:
                    pass

            sent = await send_cards_photo(
                context.bot,
                player.user_id,
                player.hand,
                skin_id=player.card_skin,
                caption=caption,
                parse_mode=ParseMode.HTML,
                max_height=760,
                padding=20,
                card_scale=0.80,
                face_scale=0.80,
                canvas_width=1600,
                canvas_height=900,
                table_skin=player.table_skin
            )
            if sent:
                user_last_hand_message[player.user_id] = sent.message_id
            else:
                cards_text = format_cards(player.hand)
                await context.bot.send_message(
                    player.user_id,
                    (
                        f"🎰 <b>Your cards:</b>\n\n{cards_text}\n\nGood luck!"
                        if lang == "en" else
                        f"🎰 <b>Твои карты:</b>\n\n{cards_text}\n\nУдачи!"
                    ),
                    parse_mode=ParseMode.HTML
                )

            last_board = user_last_board_message.get(player.user_id)
            if last_board:
                try:
                    await context.bot.delete_message(player.user_id, last_board)
                except Exception:
                    pass
            table_msg = await send_private_table_snapshot(
                context,
                game,
                player,
                "🟢 <b>Hand started</b>" if lang == "en" else "🟢 <b>Раздача началась</b>"
            )
            if table_msg:
                user_last_board_message[player.user_id] = table_msg.message_id
        except Exception as e:
            print(f"Не удалось отправить ЛС игроку {player.user_id}: {e}")
            await context.bot.send_message(
                chat_id,
                f"⚠️ {player.first_name}, открой ЛС с ботом, чтобы получить карты! (Open bot DM to receive cards.)"
            )

    if len(game.players) == 2:
        game.current_player_idx = game.dealer_pos  # в хедз-апе первым действует SB (дилер)
    else:
        game.current_player_idx = (game.dealer_pos + 3) % len(game.players)
    game.round_start_idx = game.current_player_idx

    if game.last_board_message_id:
        try:
            await context.bot.delete_message(chat_id, game.last_board_message_id)
        except Exception:
            pass
    
    table_msg = await send_group_table_snapshot(context, game, "🟢 <b>Раздача началась</b>")
    if table_msg:
        game.last_board_message_id = table_msg.message_id
    
    # Больше не шлем текстовую таблицу отдельным сообщением, если есть фото. 
    # Или шлем, но запоминаем ID чтобы потом редактировать.
    game.last_turn_message_id = None 

    await notify_turn(context, chat_id)


async def notify_turn(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    game = active_games[chat_id]
    player = game.players[game.current_player_idx]

    # Фикс мульти-чат: переключаем фокус пользователя на этот чат при его ходе
    user_active_games[player.user_id] = chat_id

    options = game.get_player_options(player)
    if not options:
        next_idx = game.next_pending_player(game.current_player_idx)
        if next_idx is None:
            await handle_round_end(context, chat_id)
            return
        if next_idx == game.current_player_idx:
            await handle_round_end(context, chat_id)
            return
        game.current_player_idx = next_idx
        await notify_turn(context, chat_id)
        return
    to_call = game.current_bet - player.bet
    print(f"DEBUG NOTIFY_TURN: current_bet={game.current_bet}, player.bet={player.bet}, to_call={to_call}")
    mention = get_mention(player.user_id, player.first_name)
    lang = await _user_lang(player.user_id)

    # 1. Уведомление в группу (кнопки только в ЛС)
    timer_emoji = get_timer_tick_emoji(TURN_TIME)
    group_text = f"▶️ Turn: {mention} {timer_emoji}" if lang == "en" else f"▶️ Ход {mention} {timer_emoji}"
    if to_call > 0:
        group_text += f" — call <b>{to_call}</b>" if lang == "en" else f" — колл <b>{to_call}</b>"
    group_text += "\n⏳ Action in bot DM" if lang == "en" else "\n⏳ Действие ждём в ЛС"
    # удаляем предыдущее сообщение хода в группе, чтобы не засорять чат
    if game.last_turn_message_id:
        try:
            await context.bot.delete_message(chat_id, game.last_turn_message_id)
        except Exception:
            pass

    sent_group = await safe_send_message(
        context.bot,
        chat_id,
        group_text + ("\n⚠️ If buttons are missing — open bot DM and press /start" if lang == "en" else "\n⚠️ Если кнопок нет — открой ЛС и нажми /start"),
        parse_mode=ParseMode.HTML
    )
    game.last_turn_message_id = sent_group.message_id

    # 2. Сообщение игроку в ЛС
    board = format_cards(game.community_cards) if game.community_cards else "—"
    timer_emoji = get_timer_tick_emoji(TURN_TIME)
    dm_lines = (
        [
            f"🎰 <b>Your turn!</b> {timer_emoji}",
            f"⏳ ~{TURN_TIME}s to act",
            f"🎴 Board: {board}",
            f"💰 Pot: <b>{game.pot}</b> • Bet: <b>{game.current_bet}</b>",
            f"🎴 Your cards: {format_cards(player.hand)}",
            f"💳 Stack: <b>{player.stack}</b>",
        ] if lang == "en" else
        [
            f"🎰 <b>Твой ход!</b> {timer_emoji}",
            f"⏳ ~{TURN_TIME} сек на ход",
            f"🎴 Стол: {board}",
            f"💰 Банк: <b>{game.pot}</b> • Ставка: <b>{game.current_bet}</b>",
            f"🎴 Твои: {format_cards(player.hand)}",
            f"💳 Стек: <b>{player.stack}</b>",
        ]
    )
    if to_call > 0:
        dm_lines.append(f"🔴 To call: <b>{to_call}</b>" if lang == "en" else f"🔴 Нужно добавить: <b>{to_call}</b>")
    dm_text = "\n".join(dm_lines)

    # — Безопасно сохраняем active_game_id для работы кнопок в ЛС
    user_active_games[player.user_id] = chat_id

    try:
        await clear_dm_ui(context, player.user_id, remove_prompt=True, remove_bet_prompt=True)

        dm_msg = await context.bot.send_message(
            player.user_id,
            dm_text,
            reply_markup=get_turn_reply_keyboard(options, lang=lang),
            parse_mode=ParseMode.HTML
        )
        user_last_dm_prompt[player.user_id] = dm_msg.message_id
    except Exception:
        await context.bot.send_message(
            chat_id,
            f"⚠️ {mention} — open bot DM, otherwise action is unavailable."
            if lang == "en" else
            f"⚠️ {mention} — открой ЛС с ботом, иначе ход недоступен.",
            parse_mode=ParseMode.HTML
        )

    if game.turn_timer:
        game.turn_timer.cancel()

    expected_user_id = player.user_id
    expected_phase = game.phase

    async def auto_fold():
        await asyncio.sleep(TURN_TIME)
        current_game = active_games.get(chat_id)
        if not current_game or current_game.phase == GamePhase.WAITING:
            return
        current_player = current_game.players[current_game.current_player_idx]
        if current_game.phase != expected_phase or current_player.user_id != expected_user_id:
            return
        if expected_user_id not in user_active_games:
            return
        if current_game.current_player_idx not in current_game.pending_to_act:
            return
        if not current_player.folded and not current_player.all_in:
            await process_action(context, chat_id, "fold", 0, auto=True)

    game.turn_timer = asyncio.create_task(auto_fold())


async def action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    lang = await _user_lang(user.id)
    chat_id = update.effective_chat.id
    
    # Если нажато в ЛС, берем сохраненный ID чата игры
    if update.effective_chat.type == "private":
        chat_id = user_active_games.get(user.id)
    
    if not chat_id or chat_id not in active_games:
        await query.answer("Game not found or already finished" if lang == "en" else "Игра не найдена или уже завершена", show_alert=True)
        return

    game = active_games[chat_id]
    data = query.data.replace("action_", "")

    current_player = game.players[game.current_player_idx]
    if user.id != current_player.user_id:
        await query.answer("It's not your turn!" if lang == "en" else "Сейчас не твой ход!", show_alert=True)
        return

    # Серверная валидация действия
    options = game.get_player_options(current_player)
    if data not in options and data != "all_in":
        await query.answer("This action is unavailable now!" if lang == "en" else "Это действие сейчас недоступно!", show_alert=True)
        return

    # Флаг блокировки для защиты от спама кнопками
    if getattr(game, '_processing_action', False):
        await query.answer("Обработка предыдущего действия..." if lang == "en" else "Processing previous action...", show_alert=False)
        return
    
    game._processing_action = True
    try:
        if data in ["fold", "check", "call", "all_in"]:
            await clear_dm_ui(context, user.id, remove_prompt=True, remove_bet_prompt=True, remove_hand=True)
            await process_action(context, chat_id, data, 0)
            await maybe_restore_private_menu(context, user.id, chat_id)
        elif data in ["bet", "raise"]:
            # Сохраняем тип и флаг в user_data
            context.user_data['action_type'] = data
            context.user_data['awaiting_bet'] = True
            context.user_data['active_game_id'] = chat_id

            label = 'bet' if lang == "en" and data == 'bet' else ('raise' if lang == "en" else ('ставки' if data == 'bet' else 'рейза'))
            max_total = game.heads_up_limit(game.current_player_idx)
            max_add = current_player.stack
            if max_total is not None:
                max_add = max(0, min(current_player.stack, max_total - game.current_bet))
            
            # DEBUG logging to trace betting issues
            print(f"DEBUG BET MENU: current_bet={game.current_bet}, min_raise={game.min_raise}, "
                  f"player_stack={current_player.stack}, max_add={max_add}, max_total={max_total}, pot={game.pot}")
            
            text = (
                (
                    f"💰 <b>Choose {label} amount:</b>\n"
                    f"────────────────────\n"
                    f"💳 Stack: <b>{current_player.stack}</b>\n"
                    f"🔵 Min: <b>{game.min_raise}</b>\n"
                    f"🟢 Pot: <b>{game.pot}</b>\n\n"
                    f"✏️ Or send amount as a number:"
                ) if lang == "en" else
                (
                    f"💰 <b>Выбери сумму {label}:</b>\n"
                    f"────────────────────\n"
                    f"💳 Стек: <b>{current_player.stack}</b>\n"
                    f"🔵 Мин: <b>{game.min_raise}</b>\n"
                    f"🟢 Банк: <b>{game.pot}</b>\n\n"
                    f"✏️ Или напиши сумму цифрой:"
                )
            )
            
            bet_keyboard = get_bet_amounts_keyboard(
                game.current_bet, game.min_raise,
                max_add, game.pot, lang=lang
            )
            
            # Check if keyboard has actual bet options (not just control buttons)
            has_bet_options = len(bet_keyboard.inline_keyboard) > 1 or (
                len(bet_keyboard.inline_keyboard) == 1 and 
                bet_keyboard.inline_keyboard[0][0].callback_data.startswith("bet_amount_")
            )
            
            if not has_bet_options:
                print(f"WARNING: Empty bet keyboard for player {user.id}! max_add={max_add}, min_raise={game.min_raise}")
                # If no bet options, only All-in is possible
                await query.answer(
                    "Only All-in available!" if lang == "en" else "Доступен только All-in!",
                    show_alert=True
                )
                # Clear the awaiting_bet flag since we're not showing menu
                context.user_data.pop('awaiting_bet', None)
                context.user_data.pop('action_type', None)
                # Don't proceed with the action - let them choose something else
                return
            
            try:
                bet_msg = await query.edit_message_text(
                    text,
                    reply_markup=bet_keyboard,
                    parse_mode=ParseMode.HTML
                )
                user_last_bet_prompt[user.id] = bet_msg.message_id
            except Exception as e:
                print(f"ERROR showing bet menu: {e}")
                # If edit fails, try sending new message instead
                try:
                    bet_msg = await context.bot.send_message(
                        user.id,
                        text,
                        reply_markup=bet_keyboard,
                        parse_mode=ParseMode.HTML
                    )
                    user_last_bet_prompt[user.id] = bet_msg.message_id
                except Exception as e2:
                    print(f"ERROR sending bet menu: {e2}")
                    context.user_data.pop('awaiting_bet', None)
                    await query.answer("Error showing bet options. Try again.", show_alert=True)
        elif data == "cancel":
            options = game.get_player_options(current_player)
            to_call = game.current_bet - current_player.bet
            board = format_cards(game.community_cards) if game.community_cards else "—"
            dm_lines = (
                [
                    f"🎰 <b>Your turn</b>",
                    f"🎴 Board: {board}",
                    f"💰 Pot: <b>{game.pot}</b> • Bet: <b>{game.current_bet}</b>",
                    f"🎴 Your cards: {format_cards(current_player.hand)}",
                    f"💳 Stack: <b>{current_player.stack}</b>",
                ] if lang == "en" else
                [
                    f"🎰 <b>Твой ход</b>",
                    f"🎴 Стол: {board}",
                    f"💰 Банк: <b>{game.pot}</b> • Ставка: <b>{game.current_bet}</b>",
                    f"🎴 Твои: {format_cards(current_player.hand)}",
                    f"💳 Стек: <b>{current_player.stack}</b>",
                ]
            )
            if to_call > 0:
                dm_lines.append(f"🔴 To call: <b>{to_call}</b>" if lang == "en" else f"🔴 Нужно добавить: <b>{to_call}</b>")
            user_last_bet_prompt.pop(user.id, None)
            await delete_message_safe(context.bot, user.id, query.message.message_id)
            dm_msg = await context.bot.send_message(
                user.id,
                "\n".join(dm_lines),
                reply_markup=get_turn_reply_keyboard(options, lang=lang),
                parse_mode=ParseMode.HTML
            )
            user_last_dm_prompt[user.id] = dm_msg.message_id
        elif data == "custom_hint":
            await query.answer("Отправь сумму обычным сообщением в этот чат.", show_alert=True)
    finally:
        game._processing_action = False




async def bet_amount_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    chat_id = update.effective_chat.id

    if update.effective_chat.type == "private":
        chat_id = user_active_games.get(user.id)

    if not chat_id or chat_id not in active_games:
        return

    game = active_games[chat_id]
    current_player = game.players[game.current_player_idx]

    if user.id != current_player.user_id:
        return

    amount = int(query.data.replace("bet_amount_", ""))
    action = context.user_data.get('action_type', 'bet')

    context.user_data.pop('awaiting_bet', None)

    await query.edit_message_reply_markup(reply_markup=None)
    await clear_dm_ui(context, user.id, remove_prompt=True, remove_bet_prompt=True, remove_hand=True)
    await process_action(context, chat_id, action, amount)
    await maybe_restore_private_menu(context, user.id, chat_id)


async def custom_raise_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовое сообщение в ЛС — ввод своей суммы рейза"""
    user = update.effective_user
    lang = await _user_lang(user.id)
    user_state = context.user_data

    if not user_state.get('awaiting_bet'):
        return  # Не в режиме ввода ставки

    chat_id = user_state.get('active_game_id') or user_active_games.get(user.id)
    if not chat_id or chat_id not in active_games:
        return

    game = active_games[chat_id]
    current_player = game.players[game.current_player_idx]

    if user.id != current_player.user_id:
        return

    text = update.message.text.strip()
    try:
        amount = int(text)
    except ValueError:
        await update.message.reply_text(
            "❌ Enter a number, for example: <b>250</b>" if lang == "en" else "❌ Введи число, например: <b>250</b>",
            parse_mode=ParseMode.HTML
        )
        return

    if amount <= 0:
        await update.message.reply_text(
            "❌ Enter a positive number, for example: <b>250</b>" if lang == "en" else "❌ Введи положительное число, например: <b>250</b>",
            parse_mode=ParseMode.HTML
        )
        return

    # Calculate max_add BEFORE using it
    max_total = game.heads_up_limit(game.current_player_idx)
    max_add = current_player.stack
    if max_total is not None:
        max_add = max(0, min(current_player.stack, max_total - game.current_bet))
    
    # Determine minimum target based on current bet
    min_target = game.min_raise if game.current_bet == 0 else game.current_bet + game.min_raise
    
    if amount > max_add:
        amount = max_add  # Cap at max allowed
        
    if amount < min_target and amount < max_add:
        await update.message.reply_text(
            f"❌ Minimum: <b>{min_target}</b>" if lang == "en" else f"❌ Минимум: <b>{min_target}</b>",
            parse_mode=ParseMode.HTML
        )
        return

    action = user_state.get('action_type', 'bet')
    user_state.pop('awaiting_bet', None)

    await delete_message_safe(context.bot, user.id, update.message.message_id)
    await clear_dm_ui(context, user.id, remove_prompt=True, remove_bet_prompt=True, remove_hand=True)
    await process_action(context, chat_id, action, amount)
    await maybe_restore_private_menu(context, user.id, chat_id)


async def process_action(context, chat_id: int, action: str, amount: int, auto: bool = False):
    try:
        game = active_games[chat_id]
        
        if game.turn_timer:
            try:
                game.turn_timer.cancel()
            except (CancelledError, Exception):
                pass
            game.turn_timer = None

        player = game.players[game.current_player_idx]
        prev_stack = player.stack

        # Clear action buttons only for current player after they make their move
        await clear_dm_ui(context, player.user_id, remove_prompt=True)

        # Серверная валидация внутри place_bet уже есть, но подстрахуемся
        round_complete = game.place_bet(game.current_player_idx, action, amount)
        added = prev_stack - player.stack
        if action == "fold":
            action_text = "сбросил карты"
        elif action == "check":
            action_text = "чек"
        elif action == "call":
            chip_sound = get_chip_sound_emoji(added)
            action_text = f"колл {added} {chip_sound}"
        elif action == "bet":
            chip_sound = get_chip_sound_emoji(player.bet)
            action_text = f"ставка {player.bet} {chip_sound}"
        elif action == "raise":
            chip_sound = get_chip_sound_emoji(player.bet)
            action_text = f"рейз до {player.bet} {chip_sound}"
        elif action == "all_in":
            action_text = f"{get_all_in_effect()} {player.bet} 🔥"
        else:
            action_text = action

        prefix = "⏰ Авто-фолд: " if auto else ""
        await safe_send_message(
            context.bot,
            chat_id,
            f"{prefix}<b>{player.first_name}</b> — {action_text}",
            parse_mode=ParseMode.HTML
        )

        # Проверяем: если остался только один не-фолдующий игрок — он немедленно выигрывает
        active = [p for p in game.players if not p.folded and p.is_active]
        if len(active) == 1:
            winner = active[0]
            # вернуть неколлированную часть ставки
            total_bets = sorted([p.total_bet for p in game.players], reverse=True)
            max_bet = total_bets[0] if total_bets else 0
            second_bet = total_bets[1] if len(total_bets) > 1 else 0
            uncalled = max(0, max_bet - second_bet)
            if uncalled > 0:
                winner.stack += uncalled
                winner.total_bet -= uncalled
                game.pot -= uncalled

            prize = game.pot
            winner.stack += prize
            winner_profit = max(0, prize - winner.total_bet)
            
            win_effect = get_win_effect(prize >= 1000)
            applause = get_applause_animation()
            text = (
                f"{win_effect}\n"
                f"🏆 <b>{winner.first_name}</b> выигрывает <b>{prize}</b> фишек!\n"
                f"{applause}\n"
                f"💨 Все остальные игроки сбросили карты."
            )
            await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
            
            # Начисляем +5 золота за победу
            try:
                await add_gold(winner.user_id, 5)
            except Exception as e:
                print(f"Error adding gold to winner: {e}")
            
            # Отправляем личное уведомление победителю
            try:
                lang = await _user_lang(winner.user_id)
                winner_msg = (
                    f"{get_win_effect(prize >= 1000)}\n\n"
                    f"🏆 <b>Победа!</b>\n"
                    f"{get_applause_animation()}\n"
                    f"✨ •═════════════• ✨\n"
                    f"💰 Выигрыш: <b>{prize}</b> фишек!\n"
                    f"🪙 Бонус: <b>+5</b> золота!\n"
                    f"💨 Соперник сбросил карты.\n"
                    f"🛒 Золото можно потратить в магазине!\n"
                    f"🏆 Поздравляем!"
                    if lang == "en" else
                    f"{get_win_effect(prize >= 1000)}\n\n"
                    f"🏆 <b>Победа!</b>\n"
                    f"{get_applause_animation()}\n"
                    f"✨ •═════════════• ✨\n"
                    f"💰 Выигрыш: <b>{prize}</b> фишек!\n"
                    f"🪙 Бонус: <b>+5</b> золота!\n"
                    f"💨 Соперник сбросил карты.\n"
                    f"🛒 Золото можно потратить в магазине!\n"
                    f"🏆 Поздравляем!"
                )
                await safe_send_message(
                    context.bot,
                    winner.user_id,
                    winner_msg,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                print(f"Error sending winner DM: {e}")
            
            # Обновляем статистику ВСЕХ участников (только один раз)
            if not game.stats_updated:
                for p in game.players:
                    if p.user_id == winner.user_id:
                        await update_stats(p.user_id, won=True, amount=winner_profit)
                    else:
                        # Даже если total_bet == 0 (сфолдил сразу), это игра
                        await update_stats(p.user_id, won=False, amount=p.total_bet)
                game.stats_updated = True

            while game.phase != GamePhase.SHOWDOWN:
                game.next_phase()
            final_table = await send_group_table_snapshot(context, game, "🏁 <b>Итоговый стол</b>", reveal_all=True)
            if final_table:
                game.last_board_message_id = final_table.message_id
            
            game.end_hand()
            
            # Clean up all player data after game ends
            for p in game.players:
                cleanup_user_data(p.user_id)
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Ещё раз!", callback_data="new_game")]
            ])
            await context.bot.send_message(
                chat_id, "Раунд завершён. Сыграем ещё?",
                reply_markup=keyboard
            )
            return

        # Если раунд не завершен, продолжаем игру
        if not round_complete:
            # Если все оставшиеся игроки в олл-ине — сразу открываем все карты
            if not game.get_active_players():
                while game.phase != GamePhase.SHOWDOWN:
                    game.next_phase()
                await handle_showdown(context, chat_id)
                return

            # Продолжаем раунд - переходим к следующему игроку
            next_idx = game.next_pending_player(game.current_player_idx)
            if next_idx is not None:
                game.current_player_idx = next_idx
                await notify_turn(context, chat_id)
            else:
                await handle_round_end(context, chat_id)
        else:
            # Раунд завершен - переходим к следующей фазе
            await handle_round_end(context, chat_id)

    except Exception as e:
        # Логируем ошибку и продолжаем игру
        print(f"Error in process_action: {e}")
        await context.bot.send_message(
            chat_id, f"⚠️ Ошибка обработки хода. Игра продолжается..."
        )
        # Продолжаем игру даже при ошибке
        try:
            if game and game.get_active_players():
                await notify_turn(context, chat_id)
        except:
            pass

async def handle_round_end(context, chat_id: int):
    game = active_games.get(chat_id)
    if not game:
        return
        
    next_phase = game.next_phase()

    if next_phase == GamePhase.SHOWDOWN:
        await handle_showdown(context, chat_id)
    else:
        phase_names = {
            GamePhase.FLOP: "ФЛОП",
            GamePhase.TURN: "ТЕРН",
            GamePhase.RIVER: "РИВЕР"
        }
        phase_emojis = {
            GamePhase.FLOP: "🃏🃏🃏",
            GamePhase.TURN: "🃏🃏🃏🃏",
            GamePhase.RIVER: "🃏🃏🃏🃏🃏"
        }
        board_str = format_cards(game.community_cards)
        phase_label = phase_names.get(next_phase, next_phase.value)
        phase_emoji = phase_emojis.get(next_phase, "")

        # Анимация раздачи карт
        dealing_anim = get_dealing_animation(next_phase.value.lower())

        # 1. Сообщение в групповой чат (общий стол)
        group_caption = f"{dealing_anim}\n\n{phase_emoji} <b>{phase_label}</b>\n\n{format_table(game)}"
        
        # Обновляем существующее фото стола вместо отправки нового
        if game.last_board_message_id:
            try:
                # Пытаемся отредактировать подпись (текст стола)
                await context.bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=game.last_board_message_id,
                    caption=group_caption,
                    parse_mode=ParseMode.HTML
                )
            except BadRequest as e:
                # Message not found or can't be edited
                if "message to edit not found" in str(e).lower() or "message is not modified" in str(e).lower():
                    pass
                else:
                    print(f"BadRequest editing caption: {e}")
            except Exception:
                pass

        sent_group_image = await send_group_table_snapshot(context, game, group_caption)
        if sent_group_image:
            game.last_board_message_id = sent_group_image.message_id
        else:
            msg = await context.bot.send_message(
                chat_id,
                f"{dealing_anim}\n\n{phase_emoji} <b>{phase_label}:</b> {board_str}\n\n"
                f"{format_table(game)}",
                parse_mode=ParseMode.HTML
            )
            game.last_board_message_id = msg.message_id

        # 2. Отправить обновление стола каждому активному игроку в ЛС
        for player in game.players:
            if not player.folded and player.is_active:
                try:
                    lang = await _user_lang(player.user_id)
                    dm_caption = (
                        f"{dealing_anim}\n\n{phase_emoji} <b>{phase_label}</b>\n"
                        f"🎴 Your cards: {format_cards(player.hand)}\n"
                        f"💰 Pot: <b>{game.pot}</b>"
                        if lang == "en" else
                        f"{dealing_anim}\n\n{phase_emoji} <b>{phase_label}</b>\n"
                        f"🎴 Твои карты: {format_cards(player.hand)}\n"
                        f"💰 Банк: <b>{game.pot}</b>"
                    )
                    # удаляем предыдущее изображение стола в ЛС
                    last_board = user_last_board_message.get(player.user_id)
                    if last_board:
                        try:
                            await context.bot.delete_message(player.user_id, last_board)
                        except Exception:
                            pass

                    sent_dm_image = await send_private_table_snapshot(context, game, player, dm_caption)
                    if sent_dm_image:
                        user_last_board_message[player.user_id] = sent_dm_image.message_id

                    # Дополнительно отправляем руки игрока при каждом открытии стола
                    last_hand = user_last_hand_message.get(player.user_id)
                    if last_hand:
                        try:
                            await context.bot.delete_message(player.user_id, last_hand)
                        except Exception:
                            pass
                    hand_msg = await send_cards_photo(
                        context.bot,
                        player.user_id,
                        player.hand,
                        skin_id=player.card_skin,
                        caption="🎴 <b>Your cards</b>" if lang == "en" else "🎴 <b>Твои карты</b>",
                        parse_mode=ParseMode.HTML,
                        max_height=760,
                        padding=20,
                        card_scale=0.80,
                        face_scale=0.80,
                        canvas_width=1600,
                        canvas_height=900,
                        table_skin=player.table_skin
                    )
                    if hand_msg:
                        user_last_hand_message[player.user_id] = hand_msg.message_id
                    if not sent_dm_image:
                        dm_text = (
                            (
                                f"{dealing_anim}\n\n{phase_emoji} <b>{phase_label}</b>\n"
                                f"════════════════════\n\n"
                                f"🎴 BOARD: {board_str}\n"
                                f"🎴 Your cards: {format_cards(player.hand)}\n\n"
                                f"💰 Pot: <b>{game.pot}</b>"
                            ) if lang == "en" else (
                                f"{dealing_anim}\n\n{phase_emoji} <b>{phase_label}</b>\n"
                                f"════════════════════\n\n"
                                f"🎴 СТОЛ: {board_str}\n"
                                f"🎴 Твои карты: {format_cards(player.hand)}\n\n"
                                f"💰 Банк: <b>{game.pot}</b>"
                            )
                        )
                        await context.bot.send_message(
                            player.user_id,
                            dm_text,
                            parse_mode=ParseMode.HTML
                        )
                except Exception:
                    pass  # Игрок не открыл ЛС с ботом

        if game.get_active_players():
            await notify_turn(context, chat_id)
        else:
            # Если нет активных игроков (все сфолдили или олл-ин), переходим к showdown
            while game.phase != GamePhase.SHOWDOWN:
                game.next_phase()
            await handle_showdown(context, chat_id)


async def handle_showdown(context, chat_id: int):
    game = active_games[chat_id]

    winners_data = game.determine_winners()

    if not winners_data:
        await context.bot.send_message(chat_id, "❌ Ошибка при определении победителя.")
        game.end_hand()
        return

    # Динамичный заголовок с эффектом
    total_prize = sum(amount for _, _, amount in winners_data)
    win_effect = get_win_effect(total_prize >= 1000)
    text = f"{win_effect}\n\n🔥 <b>ЭПИЧНОЕ ВСКРЫТИЕ КАРТ</b> 🔥\n\n"

    # Список рук игроков
    hands_text = ""
    for player in game.players:
        if not player.folded and player.is_active:
            hand_cards = format_cards(player.hand)
            all_cards = player.hand + game.community_cards
            _, _, hand_name = HandEvaluator.evaluate(all_cards)
            
            is_winner = any(w[0].user_id == player.user_id for w in winners_data)
            marker = "👑 " if is_winner else "🔹 "
            hands_text += f"{marker}<b>{player.first_name:<12}</b>: {hand_cards}\n   <i>— {hand_name}</i>\n"

    text += hands_text
    text += f"\n{'✨' * 10}\n\n"

    # Группируем выигрыши
    total_winnings = {}
    best_hand_names = {}
    for winner, hand_name, amount in winners_data:
        total_winnings[winner.user_id] = total_winnings.get(winner.user_id, 0) + amount
        best_hand_names[winner.user_id] = hand_name

    for user_id, amount in total_winnings.items():
        winner = next((p for p in game.players if p.user_id == user_id), None)
        if winner is None:
            continue  # Skip if winner not found
        winner.stack += amount
        # Начисляем +5 золота за победу в вскрытии
        try:
            await add_gold(winner.user_id, 5)
        except Exception as e:
            print(f"Error adding gold to showdown winner: {e}")
        text += f"🏆 <b>ПОБЕДИТЕЛЬ: {winner.first_name}</b>\n"
        text += f"💰 ВЫИГРЫШ: <b>{amount}</b> фишек!\n"
        text += f"🪙 БОНУС: <b>+5</b> золота!\n"
        text += f"🃏 КОМБИНАЦИЯ: <i>{best_hand_names.get(user_id, 'Unknown')}</i>\n\n"

    # Добавляем аплодисменты
    text += f"\n{get_applause_animation()}"

    # Обновляем статистику для всех (только один раз)
    if not game.stats_updated:
        for player in game.players:
            winnings = total_winnings.get(player.user_id, 0)
            profit = winnings - player.total_bet
            if profit > 0:
                await update_stats(player.user_id, won=True, amount=profit)
            else:
                await update_stats(player.user_id, won=False, amount=max(0, player.total_bet))
        game.stats_updated = True
    
    await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)

    # Итоговое общее фото стола со всеми картами
    final_table = await send_group_table_snapshot(context, game, "🏁 <b>Итоговый стол</b>", reveal_all=True)
    if final_table:
        game.last_board_message_id = final_table.message_id

    # Личные уведомления о результате с комбинациями
    active_non_folded = [p for p in game.players if not p.folded and p.is_active]
    hand_names = {}
    for participant in active_non_folded:
        _, _, hand_name = HandEvaluator.evaluate(participant.hand + game.community_cards)
        hand_names[participant.user_id] = hand_name

    for player in game.players:
        win_amount = total_winnings.get(player.user_id, 0)
        player_hand = hand_names.get(player.user_id, "—")
        rivals = [p for p in active_non_folded if p.user_id != player.user_id]
        rival = rivals[0] if len(rivals) == 1 else None
        rival_hand = hand_names.get(rival.user_id, "") if rival else ""
        profit = win_amount - player.total_bet
        if win_amount > 0:
            is_big_win = win_amount >= 1000
            msg = (
                f"{get_win_effect(is_big_win)}\n\n"
                f"🏆 <b>Победа в showdown!</b>\n"
                f"{get_applause_animation()}\n"
                f"✨ •═════════════• ✨\n"
                f"🃏 Твоя комбинация: <b>{player_hand}</b>"
            )
            if rival:
                msg += f"\n🃏 Комбинация соперника: <b>{rival_hand}</b>"
            msg += f"\n💰 Чистый выигрыш: <b>+{max(0, profit)}</b>\n"
            msg += f"🏆 Поздравляем с победой!"
        else:
            msg = (
                f"😔 <b>Поражение в showdown</b>\n"
                f"💔 •═════════════• 💔\n"
                f"🃏 Твоя комбинация: <b>{player_hand}</b>"
            )
            if rival:
                msg += f"\n🃏 Комбинация соперника: <b>{rival_hand}</b>"
            msg += f"\n💸 Потеряно: <b>{player.total_bet}</b>\n"
            msg += f"🍀 Удачи в следующей разе!"
        try:
            await safe_send_message(
                context.bot,
                player.user_id,
                msg,
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

    game.end_hand()
    
    # Clean up all player data after game ends
    for p in game.players:
        cleanup_user_data(p.user_id)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Еще одна игра", callback_data="new_game")]
    ])
    await context.bot.send_message(
        chat_id,
        "Игра завершена. Хотите сыграть еще?",
        reply_markup=keyboard
    )


async def new_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id

    if chat_id in active_games:
        del active_games[chat_id]

    await game_command(update, context)


# new_game_dm_callback удален как устаревший, используется только new_game_callback (через группу)





async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = await get_player(user.id, user.username, user.first_name)
    lang = (data.get("language") or "ru").lower()
    winrate = (data['games_won'] / data['games_played'] * 100) if data['games_played'] > 0 else 0
    skin_name = SKINS.get(data.get('card_skin', 'classic'), SKINS['classic'])['name']
    if lang == "en":
        text = (
            f"🎴 <b>PROFILE: {user.first_name.upper()}</b>\n"
            f"════════════════════\n\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"💰 Chips: <b>{data['current_balance']}</b>\n"
            f"🪙 Gold: <b>{data.get('gold', 0)}</b>\n\n"
            f"🎮 Games: <b>{data['games_played']}</b>\n"
            f"🏆 Wins: <b>{data['games_won']}</b> ({winrate:.1f}%)\n"
            f"💵 Total won: <b>{data['total_winnings']}</b>\n"
            f"🎯 Best win: <b>{data['biggest_win']}</b>\n\n"
            f"🎴 Deck: <b>{skin_name}</b>"
        )
    else:
        text = (
            f"🎴 <b>ПРОФИЛЬ: {user.first_name.upper()}</b>\n"
            f"════════════════════\n\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"💰 Фишки: <b>{data['current_balance']}</b>\n"
            f"🪙 Золото: <b>{data.get('gold', 0)}</b>\n\n"
            f"🎮 Игр: <b>{data['games_played']}</b>\n"
            f"🏆 Побед: <b>{data['games_won']}</b> ({winrate:.1f}%)\n"
            f"💵 Выиграно: <b>{data['total_winnings']}</b>\n"
            f"🎯 Рекорд: <b>{data['biggest_win']}</b>\n\n"
            f"🎴 Колода: <b>{skin_name}</b>"
        )
    await update.message.reply_text(text, reply_markup=get_profile_keyboard(lang=lang), parse_mode=ParseMode.HTML)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = await _user_lang(update.effective_user.id)
    text = (
        "❓ <b>Help</b>\n\n"
        "/start — main menu\n"
        "/profile — profile and stats\n"
        "/language — choose language\n"
        "/leave — leave current table\n"
        "/rules — quick how-to-play\n"
        "/issue — contact developer\n"
        "/help — this help"
        if lang == "en"
        else
        "❓ <b>Помощь</b>\n\n"
        "/start — главное меню\n"
        "/profile — профиль и статистика\n"
        "/language — выбор языка\n"
        "/leave — покинуть текущий стол\n"
        "/rules — краткие правила\n"
        "/issue — написать разработчику\n"
        "/help — эта справка"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = await _user_lang(update.effective_user.id)
    text = (
        "📘 <b>TEXAS HOLD'EM RULES</b>\n"
        "════════════════════\n\n"
        "🎯 <b>Objective:</b> Make the best 5-card hand using your 2 hole cards and 5 community cards.\n\n"
        "📋 <b>Gameplay:</b>\n"
        "1. Create table: <code>/game</code> in group\n"
        "2. Join and open bot DM for your cards\n"
        "3. Play through 4 betting rounds\n"
        "4. Best hand wins the pot!\n\n"
        "🔄 <b>Betting Rounds:</b>\n"
        "• <b>Pre-flop:</b> After receiving hole cards\n"
        "• <b>Flop:</b> 3 community cards dealt\n"
        "• <b>Turn:</b> 4th community card\n"
        "• <b>River:</b> 5th community card (showdown)\n\n"
        "🎮 <b>Actions:</b>\n"
        "• <b>Fold</b> — discard your hand\n"
        "• <b>Check</b> — pass action (if no bet)\n"
        "• <b>Call</b> — match current bet\n"
        "• <b>Bet</b> — place first wager\n"
        "• <b>Raise</b> — increase the bet\n"
        "• <b>All-in</b> — bet all your chips\n\n"
        "💰 <b>Blinds:</b> Small blind and big blind are forced bets posted before cards dealt.\n\n"
        "🏆 <b>Hand Rankings</b> (best to worst):\n"
        "1. Royal Flush — A-K-Q-J-10 same suit\n"
        "2. Straight Flush — 5 consecutive same suit\n"
        "3. Four of a Kind — 4 same rank\n"
        "4. Full House — 3 of a kind + pair\n"
        "5. Flush — 5 cards same suit\n"
        "6. Straight — 5 consecutive cards\n"
        "7. Three of a Kind — 3 same rank\n"
        "8. Two Pair — 2 different pairs\n"
        "9. One Pair — 1 pair\n"
        "10. High Card — highest single card\n\n"
        "⚖️ <b>All-in & Side Pots:</b>\n"
        "When a player goes all-in for less than the current bet, a side pot is created.\n"
        "Only players who contributed to that side pot can win it.\n\n"
        "🤝 <b>Split Pots:</b>\n"
        "If multiple players have identical best hands, the pot is divided equally.\n\n"
        "⏱️ Auto-fold applies if timer expires."
        if lang == "en"
        else
        "📘 <b>ПРАВИЛА ТЕХАССКОГО ХОЛДЕМА</b>\n"
        "════════════════════\n\n"
        "🎯 <b>Цель:</b> Собрать лучшую 5-карточную комбинацию из 2 своих карт и 5 общих.\n\n"
        "📋 <b>Ход игры:</b>\n"
        "1. Создай стол: <code>/game</code> в группе\n"
        "2. Садись за стол и открой ЛС с ботом для карт\n"
        "3. Играй 4 раунда ставок\n"
        "4. Лучшая рука забирает банк!\n\n"
        "🔄 <b>Раунды ставок:</b>\n"
        "• <b>Префлоп:</b> После получения карт\n"
        "• <b>Флоп:</b> 3 общие карты\n"
        "• <b>Терн:</b> 4-я общая карта\n"
        "• <b>Ривер:</b> 5-я карта (вскрытие)\n\n"
        "🎮 <b>Действия:</b>\n"
        "• <b>Фолд</b> — сбросить карты\n"
        "• <b>Чек</b> — пропустить (если нет ставки)\n"
        "• <b>Колл</b> — уравнять ставку\n"
        "• <b>Бет</b> — сделать первую ставку\n"
        "• <b>Рейз</b> — повысить ставку\n"
        "• <b>Олл-ин</b> — поставить все фишки\n\n"
        "💰 <b>Блайнды:</b> Малый и большой блайнды — обязательные ставки перед раздачей.\n\n"
        "🏆 <b>Старшинство комбинаций</b> (от сильнейшей):\n"
        "1. Флэш-рояль — 10-В-Д-К-Т одной масти\n"
        "2. Стрит-флэш — 5 карт одной масти по порядку\n"
        "3. Каре — 4 карты одного достоинства\n"
        "4. Фулл-хаус — тройка + пара\n"
        "5. Флэш — 5 карт одной масти\n"
        "6. Стрит — 5 карт по порядку\n"
        "7. Сет/тройка — 3 карты одного достоинства\n"
        "8. Две пары — 2 разных пары\n"
        "9. Пара — 1 пара\n"
        "10. Старшая карта — высшая карта\n\n"
        "⚖️ <b>Олл-ин и побочные банки:</b>\n"
        "Если игрок идет олл-ин на меньшую сумму, создается побочный банк.\n"
        "Только игроки, вложившиеся в этот банк, могут его выиграть.\n\n"
        "🤝 <b>Разделение банка:</b>\n"
        "При равных комбинациях банк делится поровну между победителями.\n\n"
        "⏱️ При истечении таймера — авто-фолд."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def issue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /issue command with usage example."""
    lang = await _user_lang(update.effective_user.id)
    
    # Check if user provided issue text
    args = context.args
    if not args:
        # Show usage instructions
        text = (
            f"🛠 <b>ОТПРАВИТЬ СООБЩЕНИЕ РАЗРАБОТЧИКУ</b>\n"
            f"════════════════════\n\n"
            f"Чтобы отправить сообщение об ошибке или предложение, используй команду:\n\n"
            f"<code>/issue [твой текст]</code>\n\n"
            f"<b>Пример:</b>\n"
            f"<code>/issue Пожалуйста, добавьте новую функцию с ...</code>\n\n"
            f"Админ ответит вам как можно скорее!"
            if lang != "en" else
            f"🛠 <b>SEND MESSAGE TO DEVELOPER</b>\n"
            f"════════════════════\n\n"
            f"To send a bug report or feature request, use:\n\n"
            f"<code>/issue [your message]</code>\n\n"
            f"<b>Example:</b>\n"
            f"<code>/issue Please add a new feature with ...</code>\n\n"
            f"Admin will reply as soon as possible!"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return
    
    # User provided issue text
    issue_text = " ".join(args)
    user = update.effective_user
    
    try:
        # Save to database
        from database import save_issue_message
        issue_id = await save_issue_message(
            user_id=user.id,
            username=user.username or '',
            first_name=user.first_name,
            message=issue_text
        )
        
        # Notify all admins
        from config import ADMIN_IDS
        from keyboards import get_admin_issue_view_keyboard
        
        admin_text = (
            f"📝 <b>НОВОЕ ОБРАЩЕНИЕ #{issue_id}</b>\n"
            f"════════════════════\n\n"
            f"👤 Пользователь: {user.first_name}\n"
            f"🆔 User ID: <code>{user.id}</code>\n"
            f"📱 Telegram: @{user.username or 'нет_username'}\n\n"
            f"💬 Сообщение:\n<i>{issue_text[:500]}{'...' if len(issue_text) > 500 else ''}</i>\n\n"
            f"✅ Требуется ответ!"
        )
        
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    admin_text,
                    reply_markup=get_admin_issue_view_keyboard(issue_id),
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                print(f"Failed to notify admin {admin_id} about issue #{issue_id}: {e}")
        
        # Confirm to user
        confirm_text = (
            f"✅ <b>Сообщение отправлено!</b>\n\n"
            f"📩 Обращение #{issue_id} зарегистрировано.\n"
            f"Администратор ответит вам как можно скорее.\n\n"
            f"Спасибо за обратную связь! 🙏"
            if lang != "en" else
            f"✅ <b>Message sent!</b>\n\n"
            f"📩 Issue #{issue_id} registered.\n"
            f"Admin will reply as soon as possible.\n\n"
            f"Thank you for your feedback! 🙏"
        )
    except Exception as e:
        print(f"Failed to save issue: {e}")
        import traceback
        traceback.print_exc()
        confirm_text = (
            f"⚠️ <b>Не удалось отправить сообщение</b>\n\n"
            f"Попробуйте позже или свяжитесь напрямую: @{SUPPORT_USERNAME or 'admin'}"
            if lang != "en" else
            f"⚠️ <b>Failed to send message</b>\n\n"
            f"Please try again later or contact directly: @{SUPPORT_USERNAME or 'admin'}"
        )
    
    await update.message.reply_text(confirm_text, parse_mode=ParseMode.HTML)


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = await _user_lang(update.effective_user.id)
    await update.message.reply_text(
        "🌐 <b>LANGUAGE</b>\n════════════════════\n\nChoose interface language:"
        if lang == "en"
        else "🌐 <b>ВЫБОР ЯЗЫКА</b>\n════════════════════\n\nВыбери язык интерфейса:",
        reply_markup=get_language_keyboard(),
        parse_mode=ParseMode.HTML
    )


async def inventory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show inventory with category selection."""
    user = update.effective_user
    lang = await _user_lang(user.id)
    
    text = (
        f"🎒 <b>INVENTORY</b>\n════════════════════\n\n"
        f"Choose category to manage your skins:\n\n"
        f"🃏 Card Decks — view and equip card skins\n"
        f"🎰 Table Skins — change table appearance\n"
        f"🎲 Chip Skins — style your chips"
        if lang == "en" else
        f"🎒 <b>ИНВЕНТАРЬ</b>\n════════════════════\n\n"
        f"Выбери категорию для управления скинами:\n\n"
        f"🃏 Колоды карт — просмотр и выбор скинов карт\n"
        f"🎰 Скины столов — изменение вида стола\n"
        f"🎲 Скины фишек — стиль фишек"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🃏 " + ("Card Decks" if lang == "en" else "Колоды карт"), callback_data="inv_category_cards")],
        [InlineKeyboardButton("🎰 " + ("Table Skins" if lang == "en" else "Скины столов"), callback_data="inv_category_tables")],
        [InlineKeyboardButton("🎲 " + ("Chip Skins" if lang == "en" else "Скины фишек"), callback_data="inv_category_chips")],
    ])
    
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


def _is_admin(user_id: int) -> bool:
    return user_id in set(ADMIN_IDS)


def _admin_help_text() -> str:
    return (
        "🛠 <b>Админ-панель (команды)</b>\n\n"
        "<code>/admin kaspi</code> — панель платежей Kaspi\n"
        "<code>/admin add_coins user_id amount</code> — добавить фишки\n"
        "<code>/admin remove_coins user_id amount</code> — убавить фишки\n"
        "<code>/admin add_gold user_id amount</code> — выдать донатное золото\n"
        "<code>/admin set_luck user_id percent</code> — шанс-буст 0..100%\n"
        "<code>/admin give_all_skins user_id</code> — выдать все скины\n"
        "<code>/admin give_all_skins</code> — выдать себе все скины\n\n"
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not _is_admin(user.id):
        await update.message.reply_text("⛔ У тебя нет прав на админ-команды.")
        return

    args = context.args or []
    if not args or args[0].lower() in {"help", "panel"}:
        await update.message.reply_text(_admin_help_text(), parse_mode=ParseMode.HTML)
        return

    cmd = args[0].lower()
    
    # Kaspi panel command
    if cmd == "kaspi":
        from keyboards import get_admin_kaspi_panel_keyboard
        text = (
            "💳 <b>KASPI PAY — АДМИН-ПАНЕЛЬ</b>\n"
            "════════════════════\n\n"
            "Управление платежами через Kaspi:\n\n"
            "⏳ Просмотр ожидающих заявок\n"
            "📊 Статистика платежей\n"
            "✅/❌ Одобрение/отклонение"
        )
        await update.message.reply_text(
            text,
            reply_markup=get_admin_kaspi_panel_keyboard("ru"),
            parse_mode=ParseMode.HTML
        )
        return
    
    # Special case: give_all_skins can work with just user_id (no value needed)
    if cmd == "give_all_skins":
        if len(args) >= 2:
            try:
                target_user_id = int(args[1])
            except ValueError:
                await update.message.reply_text("❌ user_id должен быть числом.")
                return
        else:
            target_user_id = user.id  # Give to self if no user_id provided
        
        if not await player_exists(target_user_id):
            await update.message.reply_text(f"❌ Пользователь {target_user_id} не найден в базе.")
            return
        
        # Give all card skins
        from skins import SKINS, TABLE_SKINS
        all_card_skins = list(SKINS.keys())
        all_table_skins = list(TABLE_SKINS.keys())
        
        await set_skin(target_user_id, 'classic')  # Ensure classic is set first
        await set_table_skin(target_user_id, 'classic')
        
        # Update owned_skins to include all
        import json
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "UPDATE players SET owned_skins = ?, owned_table_skins = ? WHERE user_id = ?",
                (json.dumps(all_card_skins), json.dumps(all_table_skins), target_user_id)
            )
            await db.commit()
        
        target_name = f"пользователю {target_user_id}" if target_user_id != user.id else "себе"
        await update.message.reply_text(
            f"✅ Выданы все скины карт ({len(all_card_skins)}) и столов ({len(all_table_skins)}) {target_name}!\n"
            f"🃏 Колоды: {', '.join(all_card_skins)}\n"
            f"🎰 Столы: {', '.join(all_table_skins)}"
        )
        return
    
    if len(args) < 3:
        await update.message.reply_text("❌ Недостаточно аргументов.\n\n" + _admin_help_text(), parse_mode=ParseMode.HTML)
        return

    try:
        target_user_id = int(args[1])
        value = int(args[2])
    except ValueError:
        await update.message.reply_text("❌ user_id и amount/percent должны быть числами.")
        return

    if not await player_exists(target_user_id):
        await update.message.reply_text(f"❌ Пользователь {target_user_id} не найден в базе.")
        return

    if cmd == "add_coins":
        if value <= 0:
            await update.message.reply_text("❌ amount должен быть больше 0.")
            return
        await add_coins(target_user_id, value)
        await update.message.reply_text(f"✅ Добавлено {value} фишек пользователю {target_user_id}.")
    elif cmd == "remove_coins":
        if value <= 0:
            await update.message.reply_text("❌ amount должен быть больше 0.")
            return
        await add_coins(target_user_id, -value)
        await update.message.reply_text(f"✅ Снято {value} фишек у пользователя {target_user_id}.")
    elif cmd == "add_gold":
        if value <= 0:
            await update.message.reply_text("❌ amount должен быть больше 0.")
            return
        await add_gold(target_user_id, value)
        await update.message.reply_text(f"✅ Выдано {value} донатного золота пользователю {target_user_id}.")
    elif cmd == "set_luck":
        if value < 0 or value > 100:
            await update.message.reply_text("❌ percent должен быть в диапазоне 0..100.")
            return
        await set_luck_multiplier(target_user_id, value)
        await update.message.reply_text(f"✅ Шанс-буст пользователя {target_user_id} установлен: {max(0, min(100, value))}%.")
    else:
        await update.message.reply_text("❌ Неизвестная команда.\n\n" + _admin_help_text(), parse_mode=ParseMode.HTML)


async def leave_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    lang = await _user_lang(user.id)
    chat_id = chat.id if chat.type != "private" else user_active_games.get(user.id)
    if not chat_id or chat_id not in active_games:
        await update.message.reply_text(
            "You are not seated at an active table." if lang == "en" else "Ты не сидишь за активным столом."
        )
        return

    game = active_games[chat_id]
    idx = next((i for i, p in enumerate(game.players) if p.user_id == user.id), None)
    if idx is None:
        await update.message.reply_text(
            "You are not seated at this table." if lang == "en" else "Тебя нет за этим столом."
        )
        return

    player = game.players[idx]
    user_active_games.pop(user.id, None)
    cleanup_user_data(user.id)  # Clean up all user data to prevent memory leak

    if game.phase == GamePhase.WAITING:
        was_creator = idx == 0
        game.players.pop(idx)
        await update.message.reply_text("✅ Left the lobby." if lang == "en" else "✅ Ты покинул лобби.")
        if not game.players:
            del active_games[chat_id]
            await context.bot.send_message(
                chat_id,
                "Lobby closed: no players left." if lang == "en" else "Лобби закрыто: игроков не осталось."
            )
            return
        if was_creator:
            await context.bot.send_message(
                chat_id,
                "⚠️ Table creator left. New creator assigned automatically."
                if lang == "en" else
                "⚠️ Создатель стола вышел. Новый создатель назначен автоматически."
            )
        await refresh_registration_message(context, game)
        return

    # Active hand: fold if needed, then sit out
    # IMPORTANT: Clean up any pending actions for this player first
    game.pending_to_act.discard(idx)
    
    if not player.folded and not player.all_in and game.current_player_idx == idx:
        # It's this player's turn - fold them
        try:
            await process_action(context, chat_id, "fold", 0)
        except Exception as e:
            print(f"Error auto-folding leaving player: {e}")
            player.folded = True
            game.pending_to_act.discard(idx)
    
    player.folded = True
    player.is_active = False
    
    # Clean up pending_to_act from invalid indices
    valid_indices = set(range(len(game.players)))
    game.pending_to_act = {i for i in game.pending_to_act if i in valid_indices}
    
    await update.message.reply_text(
        "✅ You left the table. You can rejoin in a new game."
        if lang == "en"
        else "✅ Ты покинул стол. Вернуться можно в новой игре."
    )
    await context.bot.send_message(
        chat_id,
        f"{get_mention(user.id, user.first_name)} left the table."
        if lang == "en" else f"{get_mention(user.id, user.first_name)} покинул стол.",
        parse_mode=ParseMode.HTML
    )


async def text_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    text = (update.message.text or "").strip()
    if text.startswith("/"):
        return
    if text == "👤 Профиль":
        await profile_command(update, context)
        return
    elif text == "🛒 Магазин":
        # показать магазин
        user = update.effective_user
        player_data = await get_player(user.id, user.username, user.first_name)
        owned = json.loads(player_data.get('owned_skins') or '["classic"]')
        current = player_data.get('card_skin', 'classic')
        lang = await _user_lang(user.id)
        shop_text = (
            f"🛒 <b>SKIN SHOP</b>\n════════════════════\n\n🪙 Your gold: <b>{player_data.get('gold', 0)}</b>\n\n"
            if lang == "en" else
            f"🛒 <b>МАГАЗИН СКИНОВ</b>\n════════════════════\n\n🪙 Твоё золото: <b>{player_data.get('gold', 0)}</b>\n\n"
        )
        for sid, skin in SKINS.items():
            status = "✅" if sid in owned else f"{skin['price']} 🪙"
            shop_text += f"{skin['name']} — {status}\n   <i>{skin['description']}</i> | {skin['preview']}\n"
        await update.message.reply_text(shop_text, reply_markup=get_shop_keyboard(owned, current, lang=lang), parse_mode=ParseMode.HTML)
        return
    elif text == "🌐 Язык":
        await language_command(update, context)
        return
    elif text == "❓ Помощь":
        await help_command(update, context)
        return

    lang = await _user_lang(update.effective_user.id)
    
    # СНАЧАЛА проверяем Ставка/Рейз для показа меню выбора суммы
    if text in {"💰 Ставка", "📈 Рейз", "💰 Bet", "📈 Raise"}:
        user = update.effective_user
        chat_id = user_active_games.get(user.id)
        if not chat_id or chat_id not in active_games:
            return
        game = active_games[chat_id]
        current_player = game.players[game.current_player_idx]
        if current_player.user_id != user.id:
            await update.message.reply_text("It's not your turn." if lang == "en" else "Сейчас не твой ход.")
            return
        action_type = "bet" if text in {"💰 Ставка", "💰 Bet"} else "raise"
        context.user_data["action_type"] = action_type
        context.user_data["awaiting_bet"] = True
        context.user_data["active_game_id"] = chat_id
        max_total = game.heads_up_limit(game.current_player_idx)
        max_add = current_player.stack
        if max_total is not None:
            max_add = max(0, min(current_player.stack, max_total - game.current_bet))
        
        # DEBUG logging
        print(f"DEBUG TEXT MENU BET: current_bet={game.current_bet}, min_raise={game.min_raise}, "
              f"player_stack={current_player.stack}, max_add={max_add}, max_total={max_total}, pot={game.pot}")
        
        label = ("bet" if action_type == "bet" else "raise") if lang == "en" else ("ставки" if action_type == "bet" else "рейза")
        text_msg = (
            f"💰 <b>Choose {label} amount:</b>\n"
            f"💳 Stack: <b>{current_player.stack}</b>\n"
            f"🔵 Min: <b>{game.min_raise}</b>\n"
            f"🟢 Pot: <b>{game.pot}</b>\n\n"
            f"✏️ Or send amount as a number:"
            if lang == "en"
            else
            f"💰 <b>Выбери сумму {label}:</b>\n"
            f"💳 Стек: <b>{current_player.stack}</b>\n"
            f"🔵 Мин: <b>{game.min_raise}</b>\n"
            f"🟢 Банк: <b>{game.pot}</b>\n\n"
            f"✏️ Или напиши сумму цифрой:"
        )
        
        bet_keyboard = get_bet_amounts_keyboard(
            game.current_bet, game.min_raise, max_add, game.pot, lang=lang
        )
        
        # Check if keyboard has actual bet options
        has_bet_options = len(bet_keyboard.inline_keyboard) > 1 or (
            len(bet_keyboard.inline_keyboard) == 1 and 
            bet_keyboard.inline_keyboard[0][0].callback_data.startswith("bet_amount_")
        )
        
        if not has_bet_options:
            print(f"WARNING: Empty bet keyboard in text_menu_handler for player {user.id}!")
            await update.message.reply_text(
                "❌ Only All-in available! Use 🔥 All-in button." if lang == "en" 
                else "❌ Доступен только All-in! Используйте кнопку 🔥 Олл-ин."
            )
            context.user_data.pop('awaiting_bet', None)
            context.user_data.pop('action_type', None)
            return
        
        try:
            bet_msg = await update.message.reply_text(
                text_msg,
                reply_markup=bet_keyboard,
                parse_mode=ParseMode.HTML
            )
            user_last_bet_prompt[user.id] = bet_msg.message_id
        except Exception as e:
            print(f"ERROR sending bet menu in text_menu_handler: {e}")
            context.user_data.pop('awaiting_bet', None)
            context.user_data.pop('action_type', None)
            await update.message.reply_text(
                "❌ Error showing bet options. Try again or use All-in." if lang == "en"
                else "❌ Ошибка показа меню ставок. Попробуйте снова или используйте Олл-ин."
            )
        return
    
    # ПОТОМ проверяем простые действия (чек, колл, фолд, олл-ин)
    action_map = {
        "✅ Чек": "check",
        "📞 Колл": "call",
        "❌ Фолд": "fold",
        "✅ Check": "check",
        "📞 Call": "call",
        "❌ Fold": "fold",
        "🔥 All-in": "all_in",
    }
    if text in action_map:
        user = update.effective_user
        chat_id = user_active_games.get(user.id)
        if not chat_id or chat_id not in active_games:
            return
        game = active_games[chat_id]
        current_player = game.players[game.current_player_idx]
        if current_player.user_id != user.id:
            await update.message.reply_text("It's not your turn." if lang == "en" else "Сейчас не твой ход.")
            return
        await process_action(context, chat_id, action_map[text], 0)
        await maybe_restore_private_menu(context, user.id, chat_id)
        return


async def private_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    
    # Check for admin Kaspi operations first
    user = update.effective_user
    from config import ADMIN_IDS
    if user.id in ADMIN_IDS:
        # Check if admin is approving/rejecting with comment
        if context.user_data.get('rejecting_payment') or context.user_data.get('approving_payment'):
            # Delegate to kaspi admin handler
            from kaspi_handlers import admin_kaspi_text_handler
            await admin_kaspi_text_handler(update, context)
            return
    
    if context.user_data.get("awaiting_bet"):
        await custom_raise_handler(update, context)
        return
    await text_menu_handler(update, context)


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Navigation callbacks for the DM main menu with history tracking."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    key = query.data
    lang = await _user_lang(user.id)

    # Handle back button
    if key == "menu_back":
        previous_page = pop_nav_stack(context)
        if previous_page:
            # Navigate to previous page without pushing to stack (we're going back)
            await _navigate_to_page(query, context, user, lang, previous_page, push_stack=False)
        else:
            # No history, go to main menu
            clear_nav_stack(context)
            await _navigate_to_page(query, context, user, lang, "menu_main", push_stack=False)
        return

    # Handle main menu - clear history when going to main
    if key == "menu_main":
        clear_nav_stack(context)
        await _navigate_to_page(query, context, user, lang, "menu_main", push_stack=False)
        return

    # For all other pages, push to navigation stack
    await _navigate_to_page(query, context, user, lang, key, push_stack=True)


async def _navigate_to_page(query, context, user, lang, page_key, push_stack=True):
    """Helper to navigate to a specific page with optional history tracking."""
    
    # Push to stack if needed (but not for back navigation)
    if push_stack:
        push_nav_stack(context, page_key)
    
    # Get back button for all pages except main menu
    back_button = None
    if page_key != "menu_main" and has_nav_history(context):
        back_button = InlineKeyboardButton("🔙 " + ("Back" if lang == "en" else "Назад"), callback_data="menu_back")
    
    if page_key == "menu_main":
        player_data = await get_player(user.id, user.username, user.first_name)
        skin_name = SKINS.get(player_data.get('card_skin', 'classic'), SKINS['classic'])['name']
        text = (
            f"🏆 <b>Welcome, {user.first_name}!</b>\n"
            f"════════════════════\n\n"
            f"🎰 PokerHubs — the best poker in Telegram!\n\n"
            f"💰 Chips: <b>{player_data['current_balance']}</b>\n"
            f"🪙 Gold: <b>{player_data.get('gold', 0)}</b>\n"
            f"🎴 Deck: <b>{skin_name}</b>"
            if lang == "en" else
            f"🏆 <b>Добро пожаловать, {user.first_name}!</b>\n"
            f"════════════════════\n\n"
            f"🎰 Покер Хаб — Лучший покер в Telegram!\n\n"
            f"💰 Фишки: <b>{player_data['current_balance']}</b>\n"
            f"🪙 Золото: <b>{player_data.get('gold', 0)}</b>\n"
            f"🎴 Колода: <b>{skin_name}</b>"
        )
        # Main menu never has back button
        await safe_edit_message_text(query, text, reply_markup=get_main_menu_keyboard(context.bot.username or "", lang=lang), parse_mode=ParseMode.HTML)

    elif page_key == "menu_profile":
        player_data = await get_player(user.id, user.username, user.first_name)
        winrate = (player_data['games_won'] / player_data['games_played'] * 100) if player_data['games_played'] > 0 else 0
        skin_name = SKINS.get(player_data.get('card_skin', 'classic'), SKINS['classic'])['name']
        text = (
            f"🎴 <b>PROFILE: {user.first_name.upper()}</b>\n"
            f"════════════════════\n\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"💰 Chips: <b>{player_data['current_balance']}</b>\n"
            f"🪙 Gold: <b>{player_data.get('gold', 0)}</b>\n\n"
            f"🎮 Games: <b>{player_data['games_played']}</b>\n"
            f"🏆 Wins: <b>{player_data['games_won']}</b> ({winrate:.1f}%)\n"
            f"💵 Total won: <b>{player_data['total_winnings']}</b>\n"
            f"🎯 Best win: <b>{player_data['biggest_win']}</b>\n\n"
            f"🎴 Deck: <b>{skin_name}</b>"
            if lang == "en" else
            f"🎴 <b>ПРОФИЛЬ: {user.first_name.upper()}</b>\n"
            f"════════════════════\n\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"💰 Фишки: <b>{player_data['current_balance']}</b>\n"
            f"🪙 Золото: <b>{player_data.get('gold', 0)}</b>\n\n"
            f"🎮 Игр: <b>{player_data['games_played']}</b>\n"
            f"🏆 Побед: <b>{player_data['games_won']}</b> ({winrate:.1f}%)\n"
            f"💵 Выиграно: <b>{player_data['total_winnings']}</b>\n"
            f"🎯 Рекорд: <b>{player_data['biggest_win']}</b>\n\n"
            f"🎴 Колода: <b>{skin_name}</b>"
        )
        kb = get_profile_keyboard(lang=lang, back_button=back_button)
        await safe_edit_message_text(query, text, reply_markup=kb, parse_mode=ParseMode.HTML)

    elif page_key == "menu_shop":
        text = (
            f"🛒 <b>SKIN SHOP</b>\n════════════════════\n\n"
            f"Welcome to the shop! Here you can buy skins for cards and tables.\n\n"
            f"🃏 Card Skins — customize your cards!\n"
            f"🎰 Table Skins — change the table look!\n"
            f"💰 Buy Chips — get more chips for the game!"
            if lang == "en" else
            f"🛒 <b>МАГАЗИН СКИНОВ</b>\n════════════════════\n\n"
            f"Добро пожаловать в магазин! Здесь ты можешь купить скины для карт и столов.\n\n"
            f"🃏 Скины карт — кастомизируй карты!\n"
            f"🎰 Скины столов — меняй вид стола!\n"
            f"💰 Купить фишки — получи больше фишек для игры!"
        )
        kb = get_shop_categories_keyboard(lang=lang, back_button=back_button)
        await safe_edit_message_text(query, text, reply_markup=kb, parse_mode=ParseMode.HTML)

    elif page_key == "menu_buy_gold":
        text = (
            "🪙 <b>GOLD PURCHASE</b>\n════════════════════\n\n🪙 Gold is used to buy skins.\n⭐ Purchased via Telegram Stars.\n\n▶️ Choose package:"
            if lang == "en"
            else "🪙 <b>ПОКУПКА ЗОЛОТА</b>\n════════════════════\n\n🪙 Золото нужно для покупки скинов.\n⭐ Покупается через Telegram Stars.\n\n▶️ Выбери пакет:"
        )
        kb = get_gold_packages_keyboard(lang=lang, back_button=back_button)
        await safe_edit_message_text(query, text, reply_markup=kb, parse_mode=ParseMode.HTML)

    elif page_key == "menu_chips":
        text = (
            "💰 <b>FREE CHIPS</b>\n════════════════════\n\n📺 Watch a rewarded video ad to get <b>3000 chips</b>!\n\n⚠️ You must watch the entire video without skipping."
            if lang == "en"
            else "💰 <b>БЕСПЛАТНЫЕ ФИШКИ</b>\n════════════════════\n\n📺 Посмотри рекламное видео и получи <b>3000 фишек</b>!\n\n⚠️ Нужно досмотреть видео до конца, без перемотки."
        )
        kb = get_chips_packages_keyboard(lang=lang, back_button=back_button)
        await safe_edit_message_text(query, text, reply_markup=kb, parse_mode=ParseMode.HTML)

    elif page_key == "menu_inventory":
        text = (
            f"🎒 <b>INVENTORY</b>\n════════════════════\n\n"
            f"Choose category to manage your skins:\n\n"
            f"🃏 Card Decks — view and equip card skins\n"
            f"🎰 Table Skins — change table appearance"
            if lang == "en" else
            f"🎒 <b>ИНВЕНТАРЬ</b>\n════════════════════\n\n"
            f"Выбери категорию для управления скинами:\n\n"
            f"🃏 Колоды карт — просмотр и выбор скинов карт\n"
            f"🎰 Скины столов — изменение вида стола"
        )
        kb = get_inventory_categories_keyboard(lang=lang, back_button=back_button)
        await safe_edit_message_text(query, text, reply_markup=kb, parse_mode=ParseMode.HTML)

    elif page_key == "menu_language":
        text = (
            "🌐 <b>LANGUAGE</b>\n════════════════════\n\nChoose interface language:"
            if lang == "en"
            else "🌐 <b>ВЫБОР ЯЗЫКА</b>\n════════════════════\n\nВыбери язык интерфейса:"
        )
        kb = get_language_keyboard(back_button=back_button)
        await safe_edit_message_text(query, text, reply_markup=kb, parse_mode=ParseMode.HTML)

    elif page_key == "menu_top":
        from database import get_leaderboard
        rows = await get_leaderboard(10)
        medals = ["🥇", "🥈", "🥉"]
        text = (
            "🏆 <b>TOP-10 PLAYERS</b>\n════════════════════\n\n"
            if lang == "en" else
            "🏆 <b>ТОП-10 ИГРОКОВ</b>\n════════════════════\n\n"
        )
        for i, row in enumerate(rows, 1):
            medal = medals[i-1] if i <= 3 else f"{i}."
            name = row.get('first_name') or row.get('username') or 'Unknown'
            text += (
                f"{medal} <b>{name}</b> — {row['games_won']} wins\n"
                if lang == "en" else
                f"{medal} <b>{name}</b> — {row['games_won']} побед\n"
            )
        kb = InlineKeyboardMarkup([[back_button]]) if back_button else InlineKeyboardMarkup([])
        await safe_edit_message_text(query, text or ("No data yet." if lang == "en" else "Пока нет данных."), reply_markup=kb, parse_mode=ParseMode.HTML)
    
    # Shop sub-pages handled by shop_callback
    elif page_key in ["shop_category_cards", "shop_category_tables", "shop_category_chips"]:
        # Delegate to shop callback handler but with history already tracked
        await _handle_shop_page(query, context, user, lang, page_key, back_button)
    
    else:
        # Unknown page, go to main
        clear_nav_stack(context)
        await _navigate_to_page(query, context, user, lang, "menu_main", push_stack=False)


async def _handle_shop_page(query, context, user, lang, page_key, back_button):
    """Handle shop sub-pages with back button support."""
    from database import get_player
    player_data = await get_player(user.id, user.username, user.first_name)
    
    if page_key == "shop_category_cards":
        owned = json.loads(player_data.get('owned_skins') or '["classic"]')
        current_skin = player_data.get('card_skin', 'classic')
        text = (
            f"🃏 <b>CARD SKINS</b>\n🪙 Your gold: <b>{player_data.get('gold', 0)}</b>\n\n"
            if lang == "en" else
            f"🃏 <b>СКИНЫ КАРТ</b>\n🪙 Твоё золото: <b>{player_data.get('gold', 0)}</b>\n\n"
        )
        for sid, skin in SKINS.items():
            status = "✅" if sid in owned else f"{skin['price']} 🪙"
            text += f"{skin['name']} — {status}\n   <i>{skin['description']}</i> | {skin['preview']}\n"
        kb = get_shop_keyboard(owned, current_skin, lang=lang, back_button=back_button)
        await safe_edit_message_text(query, text, reply_markup=kb, parse_mode=ParseMode.HTML)
    
    elif page_key == "shop_category_tables":
        owned = json.loads(player_data.get('owned_table_skins') or '["classic"]')
        current_skin = player_data.get('table_skin', 'classic')
        text = (
            f"🎰 <b>TABLE SKINS</b>\n🪙 Your gold: <b>{player_data.get('gold', 0)}</b>\n\n"
            if lang == "en" else
            f"🎰 <b>СКИНЫ СТОЛОВ</b>\n🪙 Твоё золото: <b>{player_data.get('gold', 0)}</b>\n\n"
        )
        for sid, skin in TABLE_SKINS.items():
            status = "✅" if sid in owned else f"{skin['price']} 🪙"
            text += f"{skin['emoji']} {skin['name']} — {status}\n   <i>{skin['description']}</i>\n"
        kb = get_table_skins_keyboard(owned, current_skin, lang=lang, back_button=back_button)
        await safe_edit_message_text(query, text, reply_markup=kb, parse_mode=ParseMode.HTML)
    
    elif page_key == "shop_category_chips":
        text = (
            f"💰 <b>BUY CHIPS</b>\n════════════════════\n\n"
            f"Get more chips to play longer!\n\n"
            f"📺 Watch ad — 3000 chips (FREE)\n"
            f"💳 Kaspi Pay — instant delivery\n"
            f"   10K-500K chips packages"
            if lang == "en" else
            f"💰 <b>КУПИТЬ ФИШКИ</b>\n════════════════════\n\n"
            f"Получи больше фишек, чтобы играть дольше!\n\n"
            f"📺 Смотреть рекламу — 3000 фишек (БЕСПЛАТНО)\n"
            f"💳 Kaspi Pay — мгновенное начисление\n"
            f"   Пакеты от 10K до 500K фишек"
        )
        keyboard = [
            [InlineKeyboardButton("📺 " + ("Watch Ad — 3000 chips" if lang == "en" else "Смотреть рекламу — 3000 фишек"), callback_data="chips_watch_ad")],
            [InlineKeyboardButton("💳 " + ("Buy with Kaspi Pay" if lang == "en" else "Купить через Kaspi"), callback_data="kaspi_chips_menu")],
        ]
        if back_button:
            keyboard.append([back_button])
        kb = InlineKeyboardMarkup(keyboard)
        await safe_edit_message_text(query, text, reply_markup=kb, parse_mode=ParseMode.HTML)


async def game_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id not in active_games:
        await query.answer("Игра не найдена", show_alert=True)
        return
    game = active_games[chat_id]
    if not game.players or user.id != game.players[0].user_id:
        await query.answer(CREATOR_ONLY_ALERT, show_alert=True)
        return

    if query.data == "set_blinds":
        if game.lobby_settings_message_id:
            await delete_message_safe(context.bot, chat_id, game.lobby_settings_message_id)
        
        msg = await context.bot.send_message(
            chat_id,
            "⚙️ <b>Выбери блайнды:</b>",
            reply_markup=get_blinds_keyboard(),
            parse_mode=ParseMode.HTML
        )
        game.lobby_settings_message_id = msg.message_id
    elif query.data == "set_seats":
        if game.lobby_settings_message_id:
            await delete_message_safe(context.bot, chat_id, game.lobby_settings_message_id)

        msg = await context.bot.send_message(
            chat_id,
            "👥 <b>Выбери количество мест:</b>",
            reply_markup=get_seats_keyboard(),
            parse_mode=ParseMode.HTML
        )
        game.lobby_settings_message_id = msg.message_id


async def game_settings_value_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id not in active_games:
        await query.answer("Игра не найдена", show_alert=True)
        return
    game = active_games[chat_id]
    if not game.players or user.id != game.players[0].user_id:
        await query.answer(CREATOR_ONLY_ALERT, show_alert=True)
        return

    data = query.data
    result_text = "✅ Параметры изменены"
    if data.startswith("blind_"):
        _, sb, bb = data.split("_")
        game.small_blind = int(sb)
        game.big_blind = int(bb)
        game.min_raise = game.big_blind
        await query.answer(f"Блайнды {sb}/{bb} установлены", show_alert=True)
        result_text = f"💵 <b>Блайнды изменены:</b> {sb}/{bb}"
    elif data.startswith("seats_"):
        seats = int(data.replace("seats_", ""))
        if seats < len(game.players):
            await query.answer("Слишком мало мест для текущих игроков", show_alert=True)
            return
        game.max_players = seats
        await query.answer(f"Мест за столом: {seats}", show_alert=True)
        result_text = f"👥 <b>Количество мест изменено:</b> {seats}"

    # Обновляем сообщение регистрации
    await refresh_registration_message(context, game)
    # закрываем сообщение выбора
    try:
        await safe_edit_message_text(query, result_text, parse_mode=ParseMode.HTML)
    except Exception:
        pass


async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buy or equip card and table skins."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    lang = await _user_lang(user.id)
    data = query.data
    
    print(f"SHOP CALLBACK: user={user.id}, data={data}")

    player_data = await get_player(user.id, user.username, user.first_name)

    # Shop categories menu
    if data == "menu_shop":
        # Track navigation to shop
        push_nav_stack(context, "menu_shop")
        current_gold = player_data.get('gold', 0)
        text = (
            f"🛒 <b>SHOP</b>\n"
            f"════════════════════\n\n"
            f"🪙 Your Gold: <b>{current_gold}</b>\n\n"
            f"🃏 <b>Card Skins</b> — customize your cards\n"
            f"🎰 <b>Table Skins</b> — change table look\n"
            f"🪙 <b>Chips</b> — buy chips with gold\n"
            f"💎 <b>Buy Gold</b> — via Kaspi Pay"
            if lang == "en" else
            f"🛒 <b>МАГАЗИН</b>\n"
            f"════════════════════\n\n"
            f"🪙 Твоё Золото: <b>{current_gold}</b>\n\n"
            f"🃏 <b>Скины карт</b> — кастомизируй карты\n"
            f"🎰 <b>Скины столов</b> — меняй вид стола\n"
            f"🪙 <b>Фишки</b> — купи фишки за золото\n"
            f"💎 <b>Купить золото</b> — через Kaspi Pay"
        )
        # Create back button for shop if coming from another page
        back_button = InlineKeyboardButton("🔙 " + ("Back" if lang == "en" else "Назад"), callback_data="menu_back") if has_nav_history(context) else None
        await safe_edit_message_text(query, text, reply_markup=get_shop_categories_keyboard(lang=lang, back_button=back_button), parse_mode=ParseMode.HTML)
        return

    elif data == "shop_category_cards":
        # Track navigation to card skins
        push_nav_stack(context, "shop_category_cards")
        # Card skins menu
        owned = json.loads(player_data.get('owned_skins') or '["classic"]')
        current_skin = player_data.get('card_skin', 'classic')
        text = (
            f"🃏 <b>CARD SKINS</b>\n🪙 Your gold: <b>{player_data.get('gold', 0)}</b>\n\n"
            if lang == "en" else
            f"🃏 <b>СКИНЫ КАРТ</b>\n🪙 Твоё золото: <b>{player_data.get('gold', 0)}</b>\n\n"
        )
        for sid, skin in SKINS.items():
            status = "✅" if sid in owned else f"{skin['price']} 🪙"
            text += f"{skin['name']} — {status}\n   <i>{skin['description']}</i> | {skin['preview']}\n"
        back_button = InlineKeyboardButton("🔙 " + ("Back" if lang == "en" else "Назад"), callback_data="menu_back")
        await safe_edit_message_text(query, text, reply_markup=get_shop_keyboard(owned, current_skin, lang=lang, back_button=back_button), parse_mode=ParseMode.HTML)
        return

    elif data == "shop_category_tables":
        # Track navigation to table skins
        push_nav_stack(context, "shop_category_tables")
        owned = json.loads(player_data.get('owned_table_skins') or '["classic"]')
        current_skin = player_data.get('table_skin', 'classic')
        text = (
            f"🎰 <b>TABLE SKINS</b>\n🪙 Your gold: <b>{player_data.get('gold', 0)}</b>\n\n"
            if lang == "en" else
            f"🎰 <b>СКИНЫ СТОЛОВ</b>\n🪙 Твоё золото: <b>{player_data.get('gold', 0)}</b>\n\n"
        )
        for sid, skin in TABLE_SKINS.items():
            status = "✅" if sid in owned else f"{skin['price']} 🪙"
            text += f"{skin['emoji']} {skin['name']} — {status}\n   <i>{skin['description']}</i>\n"
        back_button = InlineKeyboardButton("🔙 " + ("Back" if lang == "en" else "Назад"), callback_data="menu_back")
        await safe_edit_message_text(query, text, reply_markup=get_table_skins_keyboard(owned, current_skin, lang=lang, back_button=back_button), parse_mode=ParseMode.HTML)
        return

    elif data == "shop_category_chips":
        # Track navigation to chips
        push_nav_stack(context, "shop_category_chips")
        # Show chips purchase options with gold exchange
        current_gold = player_data.get('gold', 0)
        text = (
            f"🪙 <b>CHIPS PURCHASE</b>\n"
            f"════════════════════\n\n"
            f"Your Gold: <b>{current_gold}</b> 🪙\n\n"
            f"Exchange rates:\n"
            f"• 100 Gold → 1,000 chips\n"
            f"• 200 Gold → 2,500 chips (+25% bonus)\n"
            f"• 300 Gold → 4,000 chips (+33% bonus)\n"
            f"• 500 Gold → 7,500 chips (+50% bonus)\n\n"
            f"Select amount or watch ad for free chips:"
            if lang == "en" else
            f"🪙 <b>ПОКУПКА ФИШЕК</b>\n"
            f"════════════════════\n\n"
            f"Твоё Золото: <b>{current_gold}</b> 🪙\n\n"
            f"Курсы обмена:\n"
            f"• 100 Gold → 1,000 фишек\n"
            f"• 200 Gold → 2,500 фишек (+25% бонус)\n"
            f"• 300 Gold → 4,000 фишек (+33% бонус)\n"
            f"• 500 Gold → 7,500 фишек (+50% бонус)\n\n"
            f"Выбери сумму или посмотри рекламу:"
        )
        keyboard_buttons = [
            [InlineKeyboardButton("🪙 100 Gold → 1,000", callback_data="gold_exchange_100")],
            [InlineKeyboardButton("🪙 200 Gold → 2,500", callback_data="gold_exchange_200")],
            [InlineKeyboardButton("🪙 300 Gold → 4,000", callback_data="gold_exchange_300")],
            [InlineKeyboardButton("🪙 500 Gold → 7,500", callback_data="gold_exchange_500")],
            [InlineKeyboardButton("📺 " + ("Watch Ad — 3,000 chips (FREE)" if lang == "en" else "Смотреть рекламу — 3,000 фишек (БЕСПЛАТНО)"), callback_data="chips_watch_ad")],
        ]
        # Add back button using navigation system
        back_button = InlineKeyboardButton("🔙 " + ("Back" if lang == "en" else "Назад"), callback_data="menu_back")
        keyboard_buttons.append([back_button])
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        await safe_edit_message_text(query, text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        return

    elif data == "shop_gold_buy":
        # Track navigation
        push_nav_stack(context, "shop_gold_buy")
        # Show gold purchase via Kaspi
        text = (
            f"💎 <b>BUY GOLD — KASPI PAY</b>\n"
            f"════════════════════\n\n"
            f"Purchase gold via Kaspi Pay (Kazakhstan):\n\n"
            f"💰 Payment: Kaspi transfer\n"
            f"📱 To: +77012345678\n"
            f"⚡ After approval: Gold instantly credited\n\n"
            f"Select package:"
            if lang == "en" else
            f"💎 <b>ПОКУПКА ЗОЛОТА — KASPI PAY</b>\n"
            f"════════════════════\n\n"
            f"Купи золото через Kaspi Pay (Казахстан):\n\n"
            f"💰 Оплата: перевод Kaspi\n"
            f"📱 Получатель: +77012345678\n"
            f"⚡ После одобрения: золото мгновенно\n\n"
            f"Выбери пакет:"
        )
        from keyboards import get_kaspi_gold_packages_keyboard
        await safe_edit_message_text(query, text, reply_markup=get_kaspi_gold_packages_keyboard(lang), parse_mode=ParseMode.HTML)
        return

    # Gold exchange handler
    elif data.startswith("gold_exchange_"):
        exchange_id = data
        from keyboards import GOLD_EXCHANGE_RATES
        
        if exchange_id not in GOLD_EXCHANGE_RATES:
            await query.answer("❌ Invalid exchange option" if lang == "en" else "❌ Неверный вариант обмена", show_alert=True)
            return
        
        rate = GOLD_EXCHANGE_RATES[exchange_id]
        gold_cost = rate["gold_cost"]
        chips_amount = rate["chips"]
        
        current_gold = player_data.get('gold', 0)
        
        if current_gold < gold_cost:
            await query.answer(
                f"❌ You don't have enough gold to buy\n\n"
                f"Required: {gold_cost} 🪙\n"
                f"You have: {current_gold} 🪙\n\n"
                f"Buy gold in the shop! 💎"
                if lang == "en" else
                f"❌ У вас не хватает золота для покупки\n\n"
                f"Нужно: {gold_cost} 🪙\n"
                f"У вас: {current_gold} 🪙\n\n"
                f"Купите золото в магазине! 💎",
                show_alert=True
            )
            return
        
        # Perform exchange: deduct gold, add chips
        from database import add_gold, add_coins
        await add_gold(user.id, -gold_cost)
        await add_coins(user.id, chips_amount)
        
        success_text = (
            f"✅ <b>Exchange successful!</b>\n\n"
            f"Spent: <b>{gold_cost}</b> 🪙\n"
            f"Received: <b>{chips_amount:,}</b> 💰\n\n"
            f"Happy gaming!"
            if lang == "en" else
            f"✅ <b>Обмен успешен!</b>\n\n"
            f"Потрачено: <b>{gold_cost}</b> 🪙\n"
            f"Получено: <b>{chips_amount:,}</b> 💰\n\n"
            f"Удачи в игре!"
        )
        
        await context.bot.send_message(
            chat_id=user.id,
            text=success_text,
            parse_mode=ParseMode.HTML
        )
        await query.answer(
            f"✅ +{chips_amount:,} chips!" if lang == "en" else f"✅ +{chips_amount:,} фишек!",
            show_alert=True
        )
        return

    # Card skin buy/equip
    if data.startswith("shop_buy_"):
        skin_id = data.replace("shop_buy_", "")
        skin = SKINS.get(skin_id)
        if not skin:
            return
        success = await buy_skin(user.id, skin_id, skin['price'])
        if success:
            # Send success message with inventory notification
            success_text = (
                f"🎉 <b>Purchase successful!</b>\n\n"
                f"You have successfully purchased: {skin['name']}\n"
                f"✅ Item added to your inventory!\n"
                f"🎒 Go to Inventory to equip it."
                if lang == "en" else
                f"🎉 <b>Покупка успешна!</b>\n\n"
                f"Ты успешно купил: {skin['name']}\n"
                f"✅ Предмет добавлен в инвентарь!\n"
                f"🎒 Зайди в Инвентарь, чтобы надеть его."
            )
            await context.bot.send_message(
                chat_id=user.id,
                text=success_text,
                parse_mode=ParseMode.HTML
            )
            await query.answer(
                f"✅ {skin['name']} purchased!" if lang == "en" else f"✅ {skin['name']} куплена!",
                show_alert=True
            )
        else:
            await query.answer(
                f"❌ Need {skin['price']} 🪙, you have {player_data.get('gold',0)} 🪙"
                if lang == "en" else
                f"❌ Нужно {skin['price']} 🪙, у тебя {player_data.get('gold',0)} 🪙",
                show_alert=True
            )

    elif data.startswith("shop_equip_"):
        skin_id = data.replace("shop_equip_", "")
        owned = json.loads(player_data.get('owned_skins') or '["classic"]')
        if skin_id in owned:
            await set_skin(user.id, skin_id)
            skin_name = SKINS[skin_id]['name']
            
            # Send success message
            success_text = (
                f"✅ <b>Skin equipped!</b>\n\n"
                f"You have successfully equipped: {skin_name}\n"
                f"Your cards will now use this skin in the game."
                if lang == "en" else
                f"✅ <b>Скин применён!</b>\n\n"
                f"Ты успешно экипировал: {skin_name}\n"
                f"Твои карты теперь будут использовать этот скин в игре."
            )
            await context.bot.send_message(
                chat_id=user.id,
                text=success_text,
                parse_mode=ParseMode.HTML
            )
            
            await query.answer(
                f"✅ {skin_name} equipped!" if lang == "en" else f"✅ {skin_name} активирована!",
                show_alert=True
            )

    # Table skin buy
    elif data.startswith("table_buy_"):
        skin_id = data.replace("table_buy_", "")
        skin = TABLE_SKINS.get(skin_id)
        if not skin:
            print(f"DEBUG: Table skin {skin_id} not found in TABLE_SKINS")
            return
        print(f"DEBUG: Buying table skin {skin_id} for user {user.id}, price {skin['price']}")
        success = await buy_table_skin(user.id, skin_id, skin['price'])
        print(f"DEBUG: buy_table_skin returned {success}")
        if success:
            # Send success message with inventory notification
            success_text = (
                f"🎉 <b>Purchase successful!</b>\n\n"
                f"You have successfully purchased: {skin['name']}\n"
                f"✅ Item added to your inventory!\n"
                f"🎒 Go to Inventory to equip it."
                if lang == "en" else
                f"🎉 <b>Покупка успешна!</b>\n\n"
                f"Ты успешно купил: {skin['name']}\n"
                f"✅ Предмет добавлен в инвентарь!\n"
                f"🎒 Зайди в Инвентарь, чтобы надеть его."
            )
            await context.bot.send_message(
                chat_id=user.id,
                text=success_text,
                parse_mode=ParseMode.HTML
            )
            await query.answer(
                f"✅ {skin['name']} purchased!" if lang == "en" else f"✅ {skin['name']} куплен!",
                show_alert=True
            )
        else:
            # Re-fetch player data to get current gold
            current_data = await get_player(user.id)
            current_gold = current_data.get('gold', 0)
            await query.answer(
                f"❌ Need {skin['price']} 🪙, you have {current_gold} 🪙"
                if lang == "en" else
                f"❌ Нужно {skin['price']} 🪙, у тебя {current_gold} 🪙",
                show_alert=True
            )
        # Refresh the table skins menu after purchase attempt
        player_data = await get_player(user.id)
        owned = json.loads(player_data.get('owned_table_skins') or '["classic"]')
        current_skin = player_data.get('table_skin', 'classic')
        text = (
            f"🎰 <b>TABLE SKINS</b>\n🪙 Your gold: <b>{player_data.get('gold', 0)}</b>\n\n"
            if lang == "en" else
            f"🎰 <b>СКИНЫ СТОЛОВ</b>\n🪙 Твоё золото: <b>{player_data.get('gold', 0)}</b>\n\n"
        )
        for sid, skin_info in TABLE_SKINS.items():
            status = "✅" if sid in owned else f"{skin_info['price']} 🪙"
            text += f"{skin_info['emoji']} {skin_info['name']} — {status}\n   <i>{skin_info['description']}</i>\n"
        await safe_edit_message_text(query, text, reply_markup=get_table_skins_keyboard(owned, current_skin, lang=lang), parse_mode=ParseMode.HTML)
        return

    # Table skin equip
    elif data.startswith("table_equip_"):
        skin_id = data.replace("table_equip_", "")
        owned = json.loads(player_data.get('owned_table_skins') or '["classic"]')
        print(f"DEBUG: Equipping table skin {skin_id}, owned: {owned}")
        if skin_id in owned:
            await set_table_skin(user.id, skin_id)
            skin_name = TABLE_SKINS[skin_id]['name']
            print(f"DEBUG: Table skin {skin_id} equipped successfully")
            
            # Send success message
            success_text = (
                f"✅ <b>Table skin equipped!</b>\n\n"
                f"You have successfully equipped: {skin_name}\n"
                f"Your table will now use this skin in the game."
                if lang == "en" else
                f"✅ <b>Скин стола применён!</b>\n\n"
                f"Ты успешно экипировал: {skin_name}\n"
                f"Твой стол теперь будет использовать этот скин в игре."
            )
            await context.bot.send_message(
                chat_id=user.id,
                text=success_text,
                parse_mode=ParseMode.HTML
            )
            
            await query.answer(
                f"✅ {skin_name} equipped!" if lang == "en" else f"✅ {skin_name} активирован!",
                show_alert=True
            )
        else:
            print(f"DEBUG: Skin {skin_id} not in owned list: {owned}")
            await query.answer(
                "❌ You don't own this skin!" if lang == "en" else "❌ У тебя нет этого скина!",
                show_alert=True
            )

    # Refresh current menu
    player_data = await get_player(user.id)
    if "shop_category_tables" in data or data.startswith("table_"):
        owned = json.loads(player_data.get('owned_table_skins') or '["classic"]')
        current_skin = player_data.get('table_skin', 'classic')
        text = (
            f"🎰 <b>TABLE SKINS</b>\n🪙 Your gold: <b>{player_data.get('gold', 0)}</b>\n\n"
            if lang == "en" else
            f"🎰 <b>СКИНЫ СТОЛОВ</b>\n🪙 Твоё золото: <b>{player_data.get('gold', 0)}</b>\n\n"
        )
        for sid, skin in TABLE_SKINS.items():
            status = "✅" if sid in owned else f"{skin['price']} 🪙"
            text += f"{skin['emoji']} {skin['name']} — {status}\n   <i>{skin['description']}</i>\n"
        await safe_edit_message_text(query, text, reply_markup=get_table_skins_keyboard(owned, current_skin, lang=lang), parse_mode=ParseMode.HTML)
    elif "shop_category_chips" in data:
        # Show chips purchase options (not chip skins)
        text = (
            f"💰 <b>BUY CHIPS</b>\n════════════════════\n\n"
            f"Get more chips to play longer!\n\n"
            f"📺 Watch ad — 3000 chips (FREE)\n"
            f"🎁 More packages coming soon!"
            if lang == "en" else
            f"💰 <b>КУПИТЬ ФИШКИ</b>\n════════════════════\n\n"
            f"Получи больше фишек, чтобы играть дольше!\n\n"
            f"📺 Смотреть рекламу — 3000 фишек (БЕСПЛАТНО)\n"
            f"🎁 Другие способы скоро появятся!"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📺 " + ("Watch Ad — 3000 chips" if lang == "en" else "Смотреть рекламу — 3000 фишек"), callback_data="chips_watch_ad")],
            [InlineKeyboardButton("🔙 " + ("Back" if lang == "en" else "Назад"), callback_data="menu_shop")],
        ])
        await safe_edit_message_text(query, text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    else:
        owned = json.loads(player_data.get('owned_skins') or '["classic"]')
        current_skin = player_data.get('card_skin', 'classic')
        text = (
            f"🃏 <b>CARD SKINS</b>\n🪙 Your gold: <b>{player_data.get('gold', 0)}</b>\n\n"
            if lang == "en" else
            f"🃏 <b>СКИНЫ КАРТ</b>\n🪙 Твоё золото: <b>{player_data.get('gold', 0)}</b>\n\n"
        )
        for sid, skin in SKINS.items():
            status = "✅" if sid in owned else f"{skin['price']} 🪙"
            text += f"{skin['name']} — {status}\n   <i>{skin['description']}</i> | {skin['preview']}\n"
        await safe_edit_message_text(query, text, reply_markup=get_shop_keyboard(owned, current_skin, lang=lang), parse_mode=ParseMode.HTML)


async def gold_buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Demo gold purchase handler."""
    query = update.callback_query
    user = update.effective_user
    lang = await _user_lang(user.id)
    packages = {"gold_buy_50": 50, "gold_buy_150": 150, "gold_buy_500": 500, "gold_buy_1200": 1200}
    gold_amount = packages.get(query.data, 0)
    if not gold_amount:
        await query.answer()
        return
    await add_gold(user.id, gold_amount)
    await query.answer(
        f"✅ +{gold_amount} 🪙 gold credited! (Demo)" if lang == "en" else f"✅ +{gold_amount} 🪙 золота начислено! (Демо)",
        show_alert=True
    )
    text = (
        f"🪙 <b>GOLD PURCHASE</b>\n════════════════════\n\n✅ Credited: <b>{gold_amount}</b> 🪙\nChoose next package:"
        if lang == "en" else
        f"🪙 <b>ПОКУПКА ЗОЛОТА</b>\n════════════════════\n\n✅ Зачислено: <b>{gold_amount}</b> 🪙\nВыбери следующий пакет:"
    )
    await safe_edit_message_text(query, text, reply_markup=get_gold_packages_keyboard(lang=lang), parse_mode=ParseMode.HTML)


async def chips_ad_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle chips rewarded video ad."""
    query = update.callback_query
    user = update.effective_user
    lang = await _user_lang(user.id)
    
    # Answer callback immediately to prevent timeout
    try:
        await query.answer()
    except Exception as e:
        print(f"Failed to answer callback: {e}")
    
    if query.data == "chips_watch_ad":
        # Send the rewarded video
        # VIDEO PLACEMENT: Put your ad video file at: /Users/mansur/Desktop/PokerHubs/assets/ad_video.mp4
        try:
            print(f"DEBUG chips_ad_callback: User {user.id} triggered watch ad")
            
            # Check rate limiting
            allowed, remaining = await _check_ad_rate_limit(user.id)
            print(f"DEBUG rate limit: allowed={allowed}, remaining={remaining}")
            if not allowed:
                # Convert seconds to hours and minutes
                hours = remaining // 3600
                minutes = (remaining % 3600) // 60
                if lang == "en":
                    if hours > 0:
                        time_str = f"{hours}h {minutes}m"
                    else:
                        time_str = f"{minutes}m"
                    await query.answer(
                        f"⏳ Daily limit reached!\nCome back in {time_str}",
                        show_alert=True
                    )
                else:
                    if hours > 0:
                        time_str = f"{hours}ч {minutes}м"
                    else:
                        time_str = f"{minutes}м"
                    await query.answer(
                        f"⏳ Дневной лимит достигнут!\nВозвращайся через {time_str}",
                        show_alert=True
                    )
                return
            
            # Answer callback immediately to prevent timeout
            await query.answer("⏳ Preparing video..." if lang == "en" else "⏳ Готовлю видео...")
            
            # Prepare text message
            text = (
                f"📺 <b>REWARDED VIDEO</b>\n════════════════════\n\n"
                f"Watch the video below to get <b>3000 chips</b>!\n\n"
                f"⚠️ You must watch the entire video without skipping.\n"
                f"⏳ After watching, click '✅ I watched' button."
                if lang == "en" else
                f"📺 <b>РЕКЛАМА С НАГРАДОЙ</b>\n════════════════════\n\n"
                f"Посмотри видео ниже, чтобы получить <b>3000 фишек</b>!\n\n"
                f"⚠️ Нужно досмотреть видео до конца, без перемотки.\n"
                f"⏳ После просмотра нажми кнопку '✅ Я посмотрел'"
            )
            
            # Video file path - user should place your video here
            video_path = "/Users/mansur/Desktop/PokerHubs/assets/ad_video.mp4"
            
            # Check if video exists (non-blocking via thread pool)
            def check_file_exists(path):
                import os
                return os.path.exists(path) and os.path.getsize(path) > 0
            
            try:
                video_exists = await asyncio.to_thread(check_file_exists, video_path)
                print(f"DEBUG video exists: {video_exists}, path={video_path}")
            except Exception as e:
                print(f"DEBUG error checking file: {e}")
                video_exists = False
            
            if not video_exists:
                # Video not found
                await context.bot.send_message(
                    user.id,
                    f"⚠️ <b>Video not found!</b>\n\n"
                    f"Place your ad video at:\n"
                    f"<code>/Users/mansur/Desktop/PokerHubs/assets/ad_video.mp4</code>\n\n"
                    f"Then try again.",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Get video duration
            video_duration = await _get_video_duration(video_path)
            
            # Store video sent timestamp and duration for verification
            context.user_data['ad_watch_start'] = asyncio.get_event_loop().time()
            context.user_data['ad_video_duration'] = video_duration
            context.user_data['ad_reward_claimed'] = False
            
            # Check file size and compress if needed
            def get_file_size(path):
                import os
                return os.path.getsize(path) / (1024 * 1024)  # MB
            
            try:
                file_size_mb = await asyncio.to_thread(get_file_size, video_path)
                print(f"DEBUG: Original video size: {file_size_mb:.1f}MB")
            except Exception:
                file_size_mb = 0
            
            # Determine which video file to use
            video_to_send = video_path
            compressed_path = video_path.replace('.mp4', '_compressed.mp4')
            
            # If file > 20MB, compress it
            if file_size_mb > 20:
                print(f"DEBUG: Video too large ({file_size_mb:.1f}MB), compressing...")
                # Send status message
                status_msg = await context.bot.send_message(
                    user.id,
                    "⏳ Compressing video for faster upload..." if lang == "en" else "⏳ Сжимаю видео для быстрой загрузки...",
                    parse_mode=ParseMode.HTML
                )
                
                compression_success = await _compress_video(video_path, compressed_path, target_size_mb=15)
                if compression_success:
                    video_to_send = compressed_path
                    print(f"DEBUG: Using compressed video")
                    # Delete status message
                    try:
                        await context.bot.delete_message(user.id, status_msg.message_id)
                    except Exception:
                        pass
                else:
                    print(f"DEBUG: Compression failed, will try original")
                    # Update status message
                    try:
                        await context.bot.edit_message_text(
                            "⚠️ Using original video (compression failed)..." if lang == "en" else "⚠️ Использую оригинальное видео (сжатие не удалось)...",
                            chat_id=user.id,
                            message_id=status_msg.message_id
                        )
                    except Exception:
                        pass
            
            # Try to send video
            print(f"DEBUG: Sending video from: {video_to_send}")
            from telegram import InputFile
            import random
            
            unique_filename = f"ad_video_{random.randint(1000, 9999)}.mp4"
            video_file = open(video_to_send, 'rb')
            input_file = InputFile(video_file, filename=unique_filename)
            
            await context.bot.send_video(
                chat_id=user.id,
                video=input_file,
                caption=text,
                width=1080,
                height=1920,
                supports_streaming=True,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ " + ("I watched — Get 3000 chips" if lang == "en" else "Я посмотрел — Получить 3000 фишек"), callback_data="chips_ad_complete")]
                ]),
                parse_mode=ParseMode.HTML,
                connect_timeout=30,
                read_timeout=300,
                write_timeout=300
            )
            video_file.close()
            print(f"DEBUG: Video sent successfully")
            
            # Cleanup compressed file if used
            if video_to_send == compressed_path:
                try:
                    import os
                    os.remove(compressed_path)
                    print(f"DEBUG: Cleaned up compressed file")
                except Exception:
                    pass
                    
        except Exception as e:
            print(f"Error sending ad video: {e}")
            import traceback
            traceback.print_exc()
            try:
                await context.bot.send_message(
                    user.id,
                    "❌ Error sending video! The video may be too large." if lang == "en" else "❌ Ошибка отправки видео! Возможно файл слишком большой.",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass
    
    elif query.data == "chips_ad_complete":
        # User clicked "I watched" - verify they watched the full video
        try:
            # Check if video was sent and if enough time has passed
            watch_start = context.user_data.get('ad_watch_start')
            video_duration = context.user_data.get('ad_video_duration', 30.0)
            already_claimed = context.user_data.get('ad_reward_claimed', False)
            
            if already_claimed:
                await query.answer(
                    "Reward already claimed!" if lang == "en" else "Награда уже получена!",
                    show_alert=True
                )
                return
            
            if watch_start is None:
                # No video was sent or data was cleared
                await query.answer(
                    "Please watch the video first!" if lang == "en" else "Сначала посмотри видео!",
                    show_alert=True
                )
                return
            
            # Calculate elapsed time
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - watch_start
            required_time = video_duration + 2.0  # Video duration + 2 second buffer
            
            if elapsed < required_time:
                # Not enough time passed - user didn't watch full video
                remaining = int(required_time - elapsed)
                await query.answer(
                    f"⏳ Watch the full video! {remaining}s remaining" if lang == "en" else f"⏳ Досмотри видео до конца! Осталось {remaining}с",
                    show_alert=True
                )
                
                # Send additional message explaining
                warning_text = (
                    f"⏳ <b>Video not fully watched!</b>\n\n"
                    f"You need to watch the entire video to get your reward.\n"
                    f"Please continue watching for <b>{remaining} more seconds</b>."
                    if lang == "en" else
                    f"⏳ <b>Видео не досмотрено!</b>\n\n"
                    f"Ты должен досмотреть видео до конца, чтобы получить награду.\n"
                    f"Пожалуйста, продолжай смотреть ещё <b>{remaining} секунд</b>."
                )
                await context.bot.send_message(user.id, warning_text, parse_mode=ParseMode.HTML)
                return
            
            # Enough time passed - user watched the video, give reward
            context.user_data['ad_reward_claimed'] = True
            await add_coins(user.id, 3000)
            await query.answer(
                f"✅ +3000 chips credited!" if lang == "en" else f"✅ +3000 фишек начислено!",
                show_alert=True
            )
            
            # Update message to show success
            text = (
                f"✅ <b>REWARD CLAIMED!</b>\n════════════════════\n\n"
                f"🎉 You received <b>3000 chips</b>!\n\n"
                f"Want to watch again for more?"
                if lang == "en" else
                f"✅ <b>НАГРАДА ПОЛУЧЕНА!</b>\n════════════════════\n\n"
                f"🎉 Ты получил <b>3000 фишек</b>!\n\n"
                f"Хочешь посмотреть еще раз?"
            )
            
            await safe_edit_message_text(
                query, 
                text,
                reply_markup=get_chips_packages_keyboard(lang=lang),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            print(f"Error crediting chips: {e}")
            await query.answer(
                "Error crediting chips!" if lang == "en" else "Ошибка начисления фишек!",
                show_alert=True
            )


async def daily_bonus_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle daily bonus casino slot machine with dynamic win rates."""
    query = update.callback_query
    user = update.effective_user
    lang = await _user_lang(user.id)
    
    if query.data == "daily_bonus":
        try:
            print(f"DEBUG daily_bonus: User {user.id} triggered daily bonus")
            
            # Check rate limiting first (fast operation)
            allowed, remaining = await _check_daily_bonus_limit(user.id)
            print(f"DEBUG daily_bonus rate limit: allowed={allowed}, remaining={remaining}")
            
            if not allowed:
                # Convert seconds to hours and minutes
                hours = remaining // 3600
                minutes = (remaining % 3600) // 60
                if lang == "en":
                    if hours > 0:
                        time_str = f"{hours}h {minutes}m"
                    else:
                        time_str = f"{minutes}m"
                    await query.answer(
                        f"⏳ Daily bonus claimed!\nCome back in {time_str}",
                        show_alert=True
                    )
                else:
                    if hours > 0:
                        time_str = f"{hours}ч {minutes}м"
                    else:
                        time_str = f"{minutes}м"
                    await query.answer(
                        f"⏳ Бонус уже получен!\nВозвращайся через {time_str}",
                        show_alert=True
                    )
                return
            
            # Answer callback immediately to prevent timeout
            await query.answer("🎰 Spinning..." if lang == "en" else "🎰 Крутим...")
            
            # Slot machine symbols - using single-width emojis for consistency
            symbols = ["🍒", "🍋", "🍊", "🍇", "💎", "7️", "💰", "⭐"]
            
            # Helper to create slot display with consistent spacing
            def slot_box(s1, s2, s3):
                return (
                    f"╔═════╦═════╦═════╗\n"
                    f"║ {s1} ║ {s2} ║ {s3} ║\n"
                    f"╚═════╩═════╩═════╝"
                )
            
            # Send initial slot machine message
            slot_display = (
                f"{'🎰 DAILY BONUS 🎰' if lang == 'en' else '🎰 ЕЖЕДНЕВНЫЙ БОНУС 🎰'}\n"
                f"{'─' * 17}\n\n"
                f"{slot_box('❓', '❓', '❓')}\n\n"
                f"{'▶️ Spinning...' if lang == 'en' else '▶️ Крутим...'}"
            )
            
            spin_msg = await context.bot.send_message(
                user.id,
                f"<code>{slot_display}</code>",
                parse_mode=ParseMode.HTML
            )
            
            # Animation: show different symbol combinations
            import random
            for i in range(5):
                s1, s2, s3 = random.choice(symbols), random.choice(symbols), random.choice(symbols)
                animated_display = (
                    f"{'🎰 DAILY BONUS 🎰' if lang == 'en' else '🎰 ЕЖЕДНЕВНЫЙ БОНУС 🎰'}\n"
                    f"{'─' * 17}\n\n"
                    f"{slot_box(s1, s2, s3)}\n\n"
                    f"{'▶️ Spinning...' if lang == 'en' else '▶️ Крутим...'}"
                )
                try:
                    await context.bot.edit_message_text(
                        f"<code>{animated_display}</code>",
                        chat_id=user.id,
                        message_id=spin_msg.message_id,
                        parse_mode=ParseMode.HTML
                    )
                    await asyncio.sleep(0.6)
                except Exception:
                    pass
            
            # Fixed low win chance for everyone - only 25% chance to win
            win_chance = 0.25
            
            print(f"DEBUG daily_bonus: User {user.id} win_chance={win_chance}")
            
            # Determine if user wins
            rand = random.random()
            is_win = rand <= win_chance
            
            if not is_win:
                # LOSS - show losing combination (all different symbols)
                loss_symbols = ["🍒", "🍋", "🍊"]
                s1, s2, s3 = loss_symbols[0], loss_symbols[1], loss_symbols[2]
                
                loss_display = (
                    f"{'🎰 DAILY BONUS 🎰' if lang == 'en' else '🎰 ЕЖЕДНЕВНЫЙ БОНУС 🎰'}\n"
                    f"{'─' * 17}\n\n"
                    f"{slot_box(s1, s2, s3)}\n\n"
                    f"{'❌ NOT THIS TIME!' if lang == 'en' else '❌ НЕ ПОВЕЗЛО!'}\n"
                    f"{'Try again tomorrow!' if lang == 'en' else 'Попробуй снова завтра!'} 😢"
                )
                
                await context.bot.edit_message_text(
                    f"<code>{loss_display}</code>",
                    chat_id=user.id,
                    message_id=spin_msg.message_id,
                    parse_mode=ParseMode.HTML
                )
                
                # Show back button
                await context.bot.send_message(
                    user.id,
                    "🎰 " + ("Better luck next time!" if lang == "en" else "В следующий раз повезёт!"),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 " + ("Back" if lang == "en" else "Назад"), callback_data="menu_back")]
                    ]),
                    parse_mode=ParseMode.HTML
                )
                print(f"DEBUG daily_bonus: User {user.id} lost")
                return
            
            # WIN - determine prize with fixed probabilities (low chance for big prizes)
            prizes = [
                ("💎💎💎", 5000, 0.02),    # 2% - Jackpot (very rare)
                ("7️7️7️", 3000, 0.05),     # 5% - Big win
                ("💰💰💰", 2000, 0.13),    # 13% - Medium
                ("🍇🍇🍇", 1000, 0.30),    # 30% - Small
                ("🍊🍊🍊", 500, 0.50),      # 50% - Tiny (most common when winning)
            ]
            
            # Weighted random selection for prize
            prize_rand = random.random()
            cumulative = 0
            winning_combo = "🍊🍊🍊"
            prize = 500
            
            for combo, amount, prob in prizes:
                cumulative += prob
                if prize_rand <= cumulative:
                    winning_combo = combo
                    prize = amount
                    break
            
            # Parse winning combo into individual symbols
            # Handle multi-char emojis properly
            if winning_combo == "💎💎💎":
                s1, s2, s3 = "💎", "💎", "💎"
            elif winning_combo == "7️7️7️":
                s1, s2, s3 = "7️", "7️", "7️"
            elif winning_combo == "💰💰💰":
                s1, s2, s3 = "💰", "💰", "💰"
            elif winning_combo == "🍇🍇🍇":
                s1, s2, s3 = "🍇", "🍇", "🍇"
            else:
                s1, s2, s3 = "🍊", "🍊", "🍊"
            
            # Show final winning result
            is_jackpot = prize >= 3000
            win_display = (
                f"{'🎰 DAILY BONUS 🎰' if lang == 'en' else '🎰 ЕЖЕДНЕВНЫЙ БОНУС 🎰'}\n"
                f"{'─' * 17}\n\n"
                f"{slot_box(s1, s2, s3)}\n\n"
                f"{'🎉 JACKPOT!' if is_jackpot else '✅ WIN!' if lang == 'en' else '🎉 ДЖЕКПОТ!' if is_jackpot else '✅ ВЫИГРЫШ!'}\n"
                f"<b>+{prize} {'chips' if lang == 'en' else 'фишек'}</b> 🎉"
            )
            
            await context.bot.edit_message_text(
                f"<code>{win_display}</code>",
                chat_id=user.id,
                message_id=spin_msg.message_id,
                parse_mode=ParseMode.HTML
            )
            
            # Credit the prize
            await add_coins(user.id, prize)
            print(f"DEBUG daily_bonus: User {user.id} won {prize} chips with combo {winning_combo}")
            
            # Show back button
            await context.bot.send_message(
                user.id,
                "🎰 " + ("Try your luck again tomorrow!" if lang == "en" else "Попробуй удачу снова завтра!"),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 " + ("Back" if lang == "en" else "Назад"), callback_data="menu_back")]
                ]),
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            print(f"Error in daily_bonus: {e}")
            import traceback
            traceback.print_exc()
            try:
                await query.answer(
                    "❌ Error! Try again later." if lang == "en" else "❌ Ошибка! Попробуй позже.",
                    show_alert=True
                )
            except Exception:
                pass


async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Language selection handler."""
    query = update.callback_query
    user = update.effective_user
    lang = query.data.replace("lang_", "")
    lang_names = {"ru": "🇷🇺 Русский", "en": "🇬🇧 English"}
    if lang not in {"ru", "en"}:
        await query.answer("❌ Доступны только RU и EN", show_alert=True)
        return
    await set_language(user.id, lang)
    await query.answer(
        f"✅ Language: {lang_names.get(lang, lang)}" if lang == "en" else f"✅ Язык: {lang_names.get(lang, lang)}",
        show_alert=True
    )
    text = (
        f"🌐 <b>LANGUAGE SET</b>\n════════════════════\n\n✅ <b>{lang_names.get(lang, lang)}</b>\n\nChoose language:"
        if lang == "en"
        else f"🌐 <b>ЯЗЫК УСТАНОВЛЕН</b>\n════════════════════\n\n✅ <b>{lang_names.get(lang, lang)}</b>\n\nВыбери язык:"
    )
    await safe_edit_message_text(query, text, reply_markup=get_language_keyboard(), parse_mode=ParseMode.HTML)


async def _show_cards_category(query, user, lang):
    """Helper to show card decks category."""
    from database import get_player
    player_data = await get_player(user.id, user.username, user.first_name)
    owned_cards = json.loads(player_data.get('owned_skins') or '["classic"]')
    current_card = player_data.get('card_skin', 'classic')
    
    text = (
        f"🃏 <b>CARD DECKS</b>\n════════════════════\n\n"
        if lang == "en" else
        f"🃏 <b>КОЛОДЫ КАРТ</b>\n════════════════════\n\n"
    )
    for sid in owned_cards:
        skin = SKINS.get(sid, SKINS['classic'])
        marker = "✅ " if sid == current_card else "  "
        text += f"{marker}{skin['name']} {skin['preview']}\n"
    
    text += "\n<i>Select a deck to equip:</i>" if lang == "en" else "\n<i>Выбери колоду для активации:</i>"
    
    keyboard = []
    for sid in owned_cards:
        if sid != current_card:
            skin = SKINS.get(sid, SKINS['classic'])
            label = f" Equip {skin['name']}" if lang == "en" else f" Надеть {skin['name']}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"inv_equip_card_{sid}")])
    
    keyboard.append([InlineKeyboardButton("🔙 " + ("Back" if lang == "en" else "Назад"), callback_data="inv_back_main")])
    
    await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)


async def _show_tables_category(query, user, lang):
    """Helper to show table skins category."""
    from database import get_player
    player_data = await get_player(user.id, user.username, user.first_name)
    owned_tables = json.loads(player_data.get('owned_table_skins') or '["classic"]')
    current_table = player_data.get('table_skin', 'classic')
    
    text = (
        f"🎰 <b>TABLE SKINS</b>\n════════════════════\n\n"
        if lang == "en" else
        f"🎰 <b>СКИНЫ СТОЛОВ</b>\n════════════════════\n\n"
    )
    for sid in owned_tables:
        skin = TABLE_SKINS.get(sid, TABLE_SKINS['classic'])
        marker = "✅ " if sid == current_table else "  "
        text += f"{marker}{skin['emoji']} {skin['name']}\n"
    
    text += "\n<i>Select a table to equip:</i>" if lang == "en" else "\n<i>Выбери стол для активации:</i>"
    
    keyboard = []
    for sid in owned_tables:
        if sid != current_table:
            skin = TABLE_SKINS.get(sid, TABLE_SKINS['classic'])
            label = f" Equip {skin['name']}" if lang == "en" else f" Надеть {skin['name']}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"inv_equip_table_{sid}")])
    
    keyboard.append([InlineKeyboardButton("🔙 " + ("Back" if lang == "en" else "Назад"), callback_data="inv_back_main")])
    
    await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)


async def inventory_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inventory equip callbacks."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    lang = await _user_lang(user.id)
    data = query.data
    
    if data == "inv_none":
        return
    
    # Handle category selections
    if data == "inv_category_cards":
        await _show_cards_category(query, user, lang)
        return
    
    elif data == "inv_category_tables":
        await _show_tables_category(query, user, lang)
        return
    
    elif data == "inv_back_main":
        # Go back to main inventory - only cards and tables
        text = (
            f"🎒 <b>INVENTORY</b>\n════════════════════\n\n"
            f"Choose category to manage your skins:\n\n"
            f"🃏 Card Decks — view and equip card skins\n"
            f"🎰 Table Skins — change table appearance"
            if lang == "en" else
            f"🎒 <b>ИНВЕНТАРЬ</b>\n════════════════════\n\n"
            f"Выбери категорию для управления скинами:\n\n"
            f"🃏 Колоды карт — просмотр и выбор скинов карт\n"
            f"🎰 Скины столов — изменение вида стола"
        )
        
        await safe_edit_message_text(query, text, reply_markup=get_inventory_categories_keyboard(lang=lang), parse_mode=ParseMode.HTML)
        return
    
    if data.startswith("inv_equip_card_"):
        skin_id = data.replace("inv_equip_card_", "")
        print(f"DEBUG: Equipping card skin {skin_id} for user {user.id}")
        await set_skin(user.id, skin_id)
        skin_name = SKINS.get(skin_id, SKINS['classic'])['name']
        
        # Show success message with confirmation
        success_text = (
            f"✅ <b>Skin equipped!</b>\n\n"
            f"You have successfully equipped: {skin_name}\n"
            f"Your cards will now use this skin in the game."
            if lang == "en" else
            f"✅ <b>Скин применён!</b>\n\n"
            f"Ты успешно экипировал: {skin_name}\n"
            f"Твои карты теперь будут использовать этот скин в игре."
        )
        
        await query.answer(
            f"✅ {skin_name} equipped!" if lang == "en" else f"✅ {skin_name} активирована!",
            show_alert=True
        )
        
        # Send confirmation message
        await context.bot.send_message(
            chat_id=user.id,
            text=success_text,
            parse_mode=ParseMode.HTML
        )
        
        # Go back to cards category
        await _show_cards_category(query, user, lang)
        return
    
    elif data.startswith("inv_equip_table_"):
        skin_id = data.replace("inv_equip_table_", "")
        print(f"DEBUG: Equipping table skin {skin_id} for user {user.id}")
        await set_table_skin(user.id, skin_id)
        skin_name = TABLE_SKINS.get(skin_id, TABLE_SKINS['classic'])['name']
        
        # Show success message with confirmation
        success_text = (
            f"✅ <b>Table skin equipped!</b>\n\n"
            f"You have successfully equipped: {skin_name}\n"
            f"Your table will now use this skin in the game."
            if lang == "en" else
            f"✅ <b>Скин стола применён!</b>\n\n"
            f"Ты успешно экипировал: {skin_name}\n"
            f"Твой стол теперь будет использовать этот скин в игре."
        )
        
        await query.answer(
            f"✅ {skin_name} equipped!" if lang == "en" else f"✅ {skin_name} активирован!",
            show_alert=True
        )
        
        # Send confirmation message
        await context.bot.send_message(
            chat_id=user.id,
            text=success_text,
            parse_mode=ParseMode.HTML
        )
        
        # Go back to tables category
        await _show_tables_category(query, user, lang)
        return
