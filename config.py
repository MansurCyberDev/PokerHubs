import os

# Токен задается через ENV (можно также указать напрямую для разработки)
TOKEN = os.getenv("POKER_BOT_TOKEN", "8633427504:AAGXYQm5HwAKO7zCUGx4FIC4VR9lN5_vUn8")

# Вставь сюда свой ID (или несколько через запятую) для админ-прав
ADMIN_IDS = [int(x.strip()) for x in os.getenv("POKER_ADMIN_IDS", "5491969475").split(",") if x.strip()]
SUPPORT_USERNAME = os.getenv("POKER_SUPPORT_USERNAME", "golovorezsm")

# Kaspi Pay configuration
KASPI_CARD = os.getenv("KASPI_CARD", "4400430233136370")  # Номер карты для переводов Kaspi

# Настройки игры (можно переопределить через ENV)
MIN_PLAYERS = int(os.getenv("POKER_MIN_PLAYERS", "2"))
MAX_PLAYERS = int(os.getenv("POKER_MAX_PLAYERS", "9"))
STARTING_STACK = int(os.getenv("POKER_STARTING_STACK", "1000"))  # Фишки при старте
SMALL_BLIND = int(os.getenv("POKER_SMALL_BLIND", "10"))
BIG_BLIND = int(os.getenv("POKER_BIG_BLIND", "20"))
REGISTRATION_TIME = int(os.getenv("POKER_REGISTRATION_TIME", "120"))  # Секунды на регистрацию
TURN_TIME = int(os.getenv("POKER_TURN_TIME", "60"))  # Секунды на ход (авто-fold)

# Масти и ранги
SUITS = ['♠', '♥', '♦', '♣']
SUITS_NAMES = {'♠': 'spades', '♥': 'hearts', '♦': 'diamonds', '♣': 'clubs'}
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
RANK_VALUES = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8,
    '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14
}

# Комбинации (от слабого к сильному)
HAND_RANKINGS = [
    'High Card', 'One Pair', 'Two Pair', 'Three of a Kind',
    'Straight', 'Flush', 'Full House', 'Four of a Kind',
    'Straight Flush', 'Royal Flush'
]