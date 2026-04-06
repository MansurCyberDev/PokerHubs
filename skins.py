"""
Система скинов для колод карт и столов.
"""

# Скины для карт
SKINS = {
    "classic": {
        "name": "🃏 Bordered",
        "description": "Стандартная колода с рамкой",
        "price": 0,
        "suits": {"♠": "♠️", "♥": "♥️", "♦": "♦️", "♣": "♣️"},
        "preview": "A♠️ K♥️ Q♦️ J♣️"
    },
    "ornamental": {
        "name": "🪄 Ornamental",
        "description": "Орнаментальная колода",
        "price": 300,
        "suits": {"♠": "♠️", "♥": "♥️", "♦": "♦️", "♣": "♣️"},
        "preview": "A♠️ K♥️ Q♦️ J♣️"
    },
}

# Скины для столов
TABLE_SKINS = {
    "classic": {
        "name": "🟢 Классический",
        "description": "Стандартный зелёный стол",
        "price": 0,
        "emoji": "🟢",
        "color": "#2d5a27",
        "felt_texture": "solid",
        "border_style": "wood"
    },
    "casino": {
        "name": "🎰 Казино",
        "description": "Профессиональный казино-стол",
        "price": 400,
        "emoji": "🎰",
        "color": "#0d3b1a",
        "felt_texture": "velvet",
        "border_style": "gold"
    },
    "luxury": {
        "name": "💎 Люкс",
        "description": "VIP-стол с золотой отделкой",
        "price": 800,
        "emoji": "💎",
        "color": "#1a1a2e",
        "felt_texture": "leather",
        "border_style": "platinum"
    },
    "home": {
        "name": "🏠 Домашний",
        "description": "Уютный домашний стол",
        "price": 200,
        "emoji": "🏠",
        "color": "#8b4513",
        "felt_texture": "cloth",
        "border_style": "rustic"
    },
    "underground": {
        "name": "🎭 Подполье",
        "description": "Тёмный стол для серьёзной игры",
        "price": 600,
        "emoji": "🎭",
        "color": "#1a1a1a",
        "felt_texture": "carbon",
        "border_style": "metal"
    },
}

DEFAULT_SKIN = "classic"
DEFAULT_TABLE_SKIN = "classic"
DEFAULT_CHIP_SKIN = "classic"

# Скины для фишек
CHIP_SKINS = {
    "classic": {
        "name": "🟤 Классические",
        "description": "Стандартные покерные фишки",
        "price": 0,
        "emoji": "🟤",
        "color": "#8D6E63"
    },
    "casino": {
        "name": "🔴 Казино",
        "description": "Профессиональные казино-фишки",
        "price": 300,
        "emoji": "🔴",
        "color": "#D32F2F"
    },
    "gold": {
        "name": "🟡 Золотые",
        "description": "Премиум золотые фишки",
        "price": 600,
        "emoji": "🟡",
        "color": "#FBC02D"
    },
    "diamond": {
        "name": "💎 Бриллиантовые",
        "description": "VIP бриллиантовые фишки",
        "price": 1000,
        "emoji": "💎",
        "color": "#00BCD4"
    },
    "neon": {
        "name": "🌈 Неоновые",
        "description": "Современные неоновые фишки",
        "price": 800,
        "emoji": "🌈",
        "color": "#E040FB"
    },
}


def format_card_with_skin(rank: str, suit: str, skin_id: str) -> str:
    """Форматирует одну карту с учетом скина игрока."""
    skin = SKINS.get(skin_id, SKINS[DEFAULT_SKIN])
    suit_emoji = skin["suits"].get(suit, suit)
    return f"{rank}{suit_emoji}"


def get_table_skin_info(skin_id: str) -> dict:
    """Получить информацию о скине стола."""
    return TABLE_SKINS.get(skin_id, TABLE_SKINS[DEFAULT_TABLE_SKIN])


def get_chip_skin_info(skin_id: str) -> dict:
    """Получить информацию о скине фишек."""
    return CHIP_SKINS.get(skin_id, CHIP_SKINS[DEFAULT_CHIP_SKIN])
