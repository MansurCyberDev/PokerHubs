from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from typing import List


def get_main_menu_keyboard(bot_username: str = "", lang: str = "ru") -> InlineKeyboardMarkup:
    """Главное меню в ЛС бота."""
    add_url = f"https://t.me/{bot_username}?startgroup=true" if bot_username else "https://t.me/"
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton("🎰 " + ("Daily Bonus" if is_en else "Ежедневный бонус"), callback_data="daily_bonus")],
        [InlineKeyboardButton("👤 " + ("My Profile" if is_en else "Мой профиль"), callback_data="menu_profile")],
        [InlineKeyboardButton("🌐 " + ("Language" if is_en else "Язык"), callback_data="menu_language")],
        [InlineKeyboardButton("🏆 " + ("Top Players" if is_en else "Топ игроков"), callback_data="menu_top")],
        [InlineKeyboardButton("➕ " + ("Add to Group" if is_en else "Добавить в группу"), url=add_url)],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_profile_keyboard(lang: str = "ru", back_button: InlineKeyboardButton = None) -> InlineKeyboardMarkup:
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton("💰 " + ("Get Free Chips" if is_en else "Бесплатные фишки"), callback_data="menu_chips")],
        [InlineKeyboardButton("🎒 Inventory" if is_en else "🎒 Инвентарь", callback_data="menu_inventory")],
    ]
    # Add dynamic back button if provided, otherwise default to main menu
    if back_button:
        keyboard.append([back_button])
    else:
        keyboard.append([InlineKeyboardButton("🔙 " + ("Back" if is_en else "Назад"), callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)


def get_shop_categories_keyboard(lang: str = "ru", back_button: InlineKeyboardButton = None) -> InlineKeyboardMarkup:
    """Выбор категории скинов."""
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton("🃏 " + ("Card Skins" if is_en else "Скины карт"), callback_data="shop_category_cards")],
        [InlineKeyboardButton("🎰 " + ("Table Skins" if is_en else "Скины столов"), callback_data="shop_category_tables")],
        [InlineKeyboardButton("💰 " + ("Buy Chips" if is_en else "Купить фишки"), callback_data="shop_category_chips")],
    ]
    # Add dynamic back button if provided, otherwise default to main menu
    if back_button:
        keyboard.append([back_button])
    else:
        keyboard.append([InlineKeyboardButton("🔙 " + ("Back" if is_en else "Назад"), callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)


def get_shop_keyboard(owned_skins: list, current_skin: str, lang: str = "ru", back_button: InlineKeyboardButton = None) -> InlineKeyboardMarkup:
    """Список скинов карт в магазине."""
    from skins import SKINS
    is_en = lang == "en"
    keyboard = []
    for skin_id, skin in SKINS.items():
        if skin_id in owned_skins:
            status_icon = "✨" if skin_id == current_skin else "✅"
            label = f"{status_icon} {skin['name']} ({'equipped' if is_en else 'надето'})"
            cb = f"shop_equip_{skin_id}"
        else:
            label = f"🔒 {skin['name']} — {skin['price']} 💎"
            cb = f"shop_buy_{skin_id}"
        keyboard.append([InlineKeyboardButton(label, callback_data=cb)])
    # Add dynamic back button if provided, otherwise default to shop categories
    if back_button:
        keyboard.append([back_button])
    else:
        keyboard.append([InlineKeyboardButton("🔙 " + ("Back" if is_en else "Назад"), callback_data="menu_shop")])
    return InlineKeyboardMarkup(keyboard)


def get_table_skins_keyboard(owned_skins: list, current_skin: str, lang: str = "ru", back_button: InlineKeyboardButton = None) -> InlineKeyboardMarkup:
    """Список скинов столов в магазине."""
    from skins import TABLE_SKINS
    is_en = lang == "en"
    keyboard = []
    for skin_id, skin in TABLE_SKINS.items():
        if skin_id in owned_skins:
            status_icon = "✨" if skin_id == current_skin else "✅"
            label = f"{status_icon} {skin['name']} ({'equipped' if is_en else 'надето'})"
            cb = f"table_equip_{skin_id}"
        else:
            label = f"🔒 {skin['name']} — {skin['price']} 💎"
            cb = f"table_buy_{skin_id}"
        keyboard.append([InlineKeyboardButton(label, callback_data=cb)])
    # Add dynamic back button if provided, otherwise default to shop categories
    if back_button:
        keyboard.append([back_button])
    else:
        keyboard.append([InlineKeyboardButton("🔙 " + ("Back" if is_en else "Назад"), callback_data="menu_shop")])
    return InlineKeyboardMarkup(keyboard)


def get_inventory_categories_keyboard(lang: str = "ru", back_button: InlineKeyboardButton = None) -> InlineKeyboardMarkup:
    """Inventory categories - only cards and tables."""
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton("🃏 " + ("Card Decks" if is_en else "Колоды карт"), callback_data="inv_category_cards")],
        [InlineKeyboardButton("🎰 " + ("Table Skins" if is_en else "Скины столов"), callback_data="inv_category_tables")],
    ]
    # Add dynamic back button if provided, otherwise default to profile
    if back_button:
        keyboard.append([back_button])
    else:
        keyboard.append([InlineKeyboardButton("🔙 " + ("Back" if is_en else "Назад"), callback_data="menu_profile")])
    return InlineKeyboardMarkup(keyboard)


def get_gold_packages_keyboard(lang: str = "ru", back_button: InlineKeyboardButton = None) -> InlineKeyboardMarkup:
    """Пакеты для покупки золота (Telegram Stars)."""
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton("💎 50 💰 — 25 ⭐", callback_data="gold_buy_50")],
        [InlineKeyboardButton("💎 150 💰 — 69 ⭐", callback_data="gold_buy_150")],
        [InlineKeyboardButton("💎 500 💰 — 199 ⭐", callback_data="gold_buy_500")],
        [InlineKeyboardButton("💎 1200 💰 — 449 ⭐ 🔥", callback_data="gold_buy_1200")],
    ]
    # Add dynamic back button if provided, otherwise default to profile
    if back_button:
        keyboard.append([back_button])
    else:
        keyboard.append([InlineKeyboardButton("🔙 " + ("Back" if is_en else "Назад"), callback_data="menu_profile")])
    return InlineKeyboardMarkup(keyboard)


def get_chips_packages_keyboard(lang: str = "ru", back_button: InlineKeyboardButton = None) -> InlineKeyboardMarkup:
    """Пакеты для получения фишек через рекламу и покупки."""
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton("📺 " + ("Watch Ad — 3000 chips" if is_en else "Смотреть рекламу — 3000 фишек"), callback_data="chips_watch_ad")],
    ]
    # Add dynamic back button if provided, otherwise default to profile
    if back_button:
        keyboard.append([back_button])
    else:
        keyboard.append([InlineKeyboardButton("🔙 " + ("Back" if is_en else "Назад"), callback_data="menu_profile")])
    return InlineKeyboardMarkup(keyboard)


def get_language_keyboard(back_button: InlineKeyboardButton = None, lang: str = "ru") -> InlineKeyboardMarkup:
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
    ]
    # Add dynamic back button if provided, otherwise default to main menu
    if back_button:
        keyboard.append([back_button])
    else:
        keyboard.append([InlineKeyboardButton("🔙 " + ("Back" if is_en else "Назад"), callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)


def get_registration_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🪑 " + "Сесть за стол", callback_data="join_game")],
        [
            InlineKeyboardButton("🎮 " + "Начать игру", callback_data="start_early")
        ],
        [
            InlineKeyboardButton("⚙️ " + "Блайнды", callback_data="set_blinds"),
            InlineKeyboardButton("👥 " + "Места", callback_data="set_seats")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_blinds_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🎯 " + "10/20", callback_data="blind_10_20")],
        [InlineKeyboardButton("🎯 " + "25/50", callback_data="blind_25_50")],
        [InlineKeyboardButton("🎯 " + "50/100", callback_data="blind_50_100")],
        [InlineKeyboardButton("🎯 " + "100/200", callback_data="blind_100_200")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_seats_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("👥 " + "2 игрока", callback_data="seats_2")],
        [InlineKeyboardButton("👥 " + "4 игрока", callback_data="seats_4")],
        [InlineKeyboardButton("👥 " + "6 игроков", callback_data="seats_6")],
        [InlineKeyboardButton("👥 " + "9 игроков", callback_data="seats_9")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_play_again_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🔄 " + "Сыграть еще раз", callback_data="new_game_dm")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_private_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("👤 Профиль"), KeyboardButton("🛍️ Магазин")],
        [KeyboardButton("🌐 Язык"), KeyboardButton("❓ Помощь")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_turn_reply_keyboard(options: List[str], lang: str = "ru") -> ReplyKeyboardMarkup:
    is_en = lang == "en"
    keyboard = []
    
    # Основные действия - первая строка
    primary_actions = []
    if "check" in options:
        primary_actions.append(KeyboardButton("✅ " + ("Check" if is_en else "Чек")))
    if "call" in options:
        primary_actions.append(KeyboardButton("📞 " + ("Call" if is_en else "Колл")))
    if "fold" in options:
        primary_actions.append(KeyboardButton("❌ " + ("Fold" if is_en else "Фолд")))
    
    if primary_actions:
        keyboard.append(primary_actions)

    # Второстепенные действия - вторая строка
    secondary_actions = []
    if "bet" in options:
        secondary_actions.append(KeyboardButton("💰 " + ("Bet" if is_en else "Ставка")))
    if "raise" in options:
        secondary_actions.append(KeyboardButton("📈 " + ("Raise" if is_en else "Рейз")))
    if "all_in" in options:
        secondary_actions.append(KeyboardButton("🔥 " + ("All-in" if is_en else "All-in")))
        
    if secondary_actions:
        keyboard.append(secondary_actions)

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)


def get_game_keyboard(options: List[str]) -> InlineKeyboardMarkup:
    keyboard = []
    row = []

    if "check" in options:
        row.append(InlineKeyboardButton("✅ Чек", callback_data="action_check"))
    if "call" in options:
        row.append(InlineKeyboardButton("📞 Колл", callback_data="action_call"))
    if "fold" in options:
        row.append(InlineKeyboardButton("❌ Фолд", callback_data="action_fold"))

    if row:
        keyboard.append(row)

    row2 = []
    if "bet" in options:
        row2.append(InlineKeyboardButton("💰 Ставка", callback_data="action_bet"))
    if "raise" in options:
        row2.append(InlineKeyboardButton("📈 Рейз", callback_data="action_raise"))
    if "all_in" in options:
        row2.append(InlineKeyboardButton("🔥 All-in", callback_data="action_all_in"))

    if row2:
        keyboard.append(row2)

    return InlineKeyboardMarkup(keyboard)


def get_bet_amounts_keyboard(current_bet: int, min_raise: int, player_stack: int, pot: int, lang: str = "ru") -> InlineKeyboardMarkup:
    is_en = lang == "en"
    keyboard = []
    
    # Если стек меньше минимального рейза - только All-in
    if player_stack < min_raise:
        if player_stack > 0:
            keyboard.append([InlineKeyboardButton(
                f"🔥 All-in ({player_stack})", 
                callback_data=f"bet_amount_{player_stack}"
            )])
        keyboard.append([
            InlineKeyboardButton("✏️ " + ("Custom" if is_en else "Своя сумма"), callback_data="action_custom_hint"),
            InlineKeyboardButton("🔙 " + ("Cancel" if is_en else "Отмена"), callback_data="action_cancel")
        ])
        return InlineKeyboardMarkup(keyboard)
    
    # Предложенные ставки - первая строка
    pot_suggestions = [
        ("½ " + ("Pot" if is_en else "Банка"), pot // 2),
        ("¾ " + ("Pot" if is_en else "Банка"), int(pot * 0.75)),
        ("1x " + ("Pot" if is_en else "Банк"), pot),
    ]
    
    pot_row = []
    for label, amount in pot_suggestions:
        # Для bet (current_bet=0): amount - это target_total
        # Для raise (current_bet>0): amount должен быть >= current_bet + min_raise
        min_target = min_raise if current_bet == 0 else current_bet + min_raise
        if amount >= min_target and amount <= player_stack:
            pot_row.append(InlineKeyboardButton(f"{label} ({amount})", callback_data=f"bet_amount_{amount}"))
    
    if pot_row:
        keyboard.append(pot_row)
    
    # Множители рейза - вторая строка
    raise_multipliers = [
        ("2x " + ("Raise" if is_en else "Рейз"), min_raise * 2),
        ("3x " + ("Raise" if is_en else "Рейз"), min_raise * 3),
    ]
    
    raise_row = []
    for label, amount in raise_multipliers:
        min_target = min_raise if current_bet == 0 else current_bet + min_raise
        if amount >= min_target and amount <= player_stack:
            raise_row.append(InlineKeyboardButton(f"{label} ({amount})", callback_data=f"bet_amount_{amount}"))
    
    if raise_row:
        keyboard.append(raise_row)
    
    # Фиксированные суммы - третья строка
    fixed_amounts = []
    for amount in [min_raise, min_raise * 2, player_stack]:
        min_target = min_raise if current_bet == 0 else current_bet + min_raise
        if amount >= min_target and amount <= player_stack and amount not in [a for _, a in pot_suggestions + raise_multipliers]:
            fixed_amounts.append(InlineKeyboardButton(f"{amount} 💰", callback_data=f"bet_amount_{amount}"))
    
    if fixed_amounts:
        keyboard.append(fixed_amounts)

    # Кнопки управления - четвертая строка
    control_row = [
        InlineKeyboardButton("✏️ " + ("Custom" if is_en else "Своя сумма"), callback_data="action_custom_hint"),
        InlineKeyboardButton("🔙 " + ("Cancel" if is_en else "Отмена"), callback_data="action_cancel")
    ]
    keyboard.append(control_row)
    
    return InlineKeyboardMarkup(keyboard)
