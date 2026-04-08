"""
Система скинов для колод карт и столов.
"""

# Скины для карт
SKINS = {
    "classic": {
        "name": "🃏 Classic",
        "description": "Стандартная покерная колода",
        "price": 0,
        "suits": {"♠": "♠️", "♥": "♥️", "♦": "♦️", "♣": "♣️"},
        "preview": "A♠️ K♥️ Q♦️ J♣️"
    },
    "ornamental": {
        "name": "🪄 Ornamental",
        "description": "Орнаментальная колода с узорами",
        "price": 150,
        "suits": {"♠": "♠️", "♥": "♥️", "♦": "♦️", "♣": "♣️"},
        "preview": "A♠️ K♥️ Q♦️ J♣️"
    },
    "minimalist": {
        "name": "⬜ Minimalist",
        "description": "Чистый минималистичный дизайн",
        "price": 200,
        "suits": {"♠": "♠️", "♥": "♥️", "♦": "♦️", "♣": "♣️"},
        "preview": "A♠️ K♥️ Q♦️ J♣️"
    },
    "golden": {
        "name": "👑 Golden",
        "description": "Золотые края и рубиновые масти",
        "price": 400,
        "suits": {"♠": "🖤", "♥": "❤️", "♦": "🔶", "♣": "🍀"},
        "preview": "A🖤 K❤️ Q🔶 J🍀"
    },
    "royal": {
        "name": "🏰 Royal",
        "description": "Королевская колода с гербами",
        "price": 600,
        "suits": {"♠": "⚔️", "♥": "🛡️", "♦": "👑", "♣": "⚜️"},
        "preview": "A⚔️ K🛡️ Q👑 J⚜️"
    },
    "neon": {
        "name": "🌈 Neon",
        "description": "Неоновая светящаяся колода",
        "price": 800,
        "suits": {"♠": "💜", "♥": "💖", "♦": "💙", "♣": "💚"},
        "preview": "A💜 K💖 Q💙 J💚"
    },
    "dark": {
        "name": "🖤 Dark Elite",
        "description": "Тёмная премиум колода для профи",
        "price": 1000,
        "suits": {"♠": "♠️", "♥": "🩸", "♦": "🔴", "♣": "⚫"},
        "preview": "A♠️ K🩸 Q🔴 J⚫"
    },
    "anime": {
        "name": "🎌 Anime",
        "description": "Колода в стиле аниме",
        "price": 1200,
        "suits": {"♠": "🌸", "♥": "🌺", "♦": "⭐", "♣": "🎋"},
        "preview": "A🌸 K🌺 Q⭐ J🎋"
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
    "red": {
        "name": "🔴 Красный",
        "description": "Классический красный стол",
        "price": 100,
        "emoji": "🔴",
        "color": "#8b0000",
        "felt_texture": "solid",
        "border_style": "wood"
    },
    "blue": {
        "name": "� Синий",
        "description": "Спокойный синий стол",
        "price": 150,
        "emoji": "�",
        "color": "#1e3a5f",
        "felt_texture": "solid",
        "border_style": "wood"
    },
    "home": {
        "name": "🏠 Домашний",
        "description": "Уютный домашний стол",
        "price": 250,
        "emoji": "🏠",
        "color": "#8b4513",
        "felt_texture": "cloth",
        "border_style": "rustic"
    },
    "casino": {
        "name": "🎰 Казино",
        "description": "Профессиональный казино-стол",
        "price": 500,
        "emoji": "🎰",
        "color": "#0d3b1a",
        "felt_texture": "velvet",
        "border_style": "gold"
    },
    "underground": {
        "name": "🎭 Подполье",
        "description": "Тёмный стол для серьёзной игры",
        "price": 750,
        "emoji": "🎭",
        "color": "#1a1a1a",
        "felt_texture": "carbon",
        "border_style": "metal"
    },
    "royal": {
        "name": "👑 Королевский",
        "description": "Королевский стол с бархатом",
        "price": 1000,
        "emoji": "👑",
        "color": "#4a0e4e",
        "felt_texture": "velvet",
        "border_style": "gold"
    },
    "luxury": {
        "name": "💎 Люкс",
        "description": "VIP-стол с золотой отделкой",
        "price": 1500,
        "emoji": "💎",
        "color": "#1a1a2e",
        "felt_texture": "leather",
        "border_style": "platinum"
    },
    "space": {
        "name": "🌌 Космос",
        "description": "Космический стол со звёздами",
        "price": 2000,
        "emoji": "🌌",
        "color": "#0a0a2e",
        "felt_texture": "galaxy",
        "border_style": "neon"
    },
}

DEFAULT_SKIN = "classic"
DEFAULT_TABLE_SKIN = "classic"


def format_card_with_skin(rank: str, suit: str, skin_id: str) -> str:
    """Форматирует одну карту с учетом скина игрока."""
    skin = SKINS.get(skin_id, SKINS[DEFAULT_SKIN])
    suit_emoji = skin["suits"].get(suit, suit)
    return f"{rank}{suit_emoji}"


def get_table_skin_info(skin_id: str) -> dict:
    """Получить информацию о скине стола."""
    return TABLE_SKINS.get(skin_id, TABLE_SKINS[DEFAULT_TABLE_SKIN])
