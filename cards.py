import random
from typing import List, Tuple, Dict
from itertools import combinations
from config import SUITS, RANKS, RANK_VALUES


class Card:
    def __init__(self, suit: str, rank: str):
        self.suit = suit
        self.rank = rank
        self.value = RANK_VALUES[rank]

    def __repr__(self):
        return f"{self.rank}{self.suit}"

    def to_str(self):
        return f"{self.rank}{self.suit}"

    def emoji_format(self):
        """Юникод эмодзи для карт"""
        suit_emojis = {'♠': '♠️', '♥': '♥️', '♦': '♦️', '♣': '♣️'}
        return f"{self.rank}{suit_emojis[self.suit]}"


class Deck:
    def __init__(self):
        self.cards: List[Card] = [Card(s, r) for s in SUITS for r in RANKS]
        random.shuffle(self.cards)

    def deal(self, count: int = 1) -> List[Card]:
        dealt = self.cards[:count]
        self.cards = self.cards[count:]
        return dealt

    def burn(self):
        """Сжечь карту (убрать из колоды)"""
        if self.cards:
            return self.cards.pop(0)


class HandEvaluator:
    """Оценщик покерных комбинаций"""

    @staticmethod
    def evaluate(cards: List[Card]) -> Tuple[int, List[int], str]:
        """
        Возвращает: (ранг_комбинации, кикеры, название_комбинации)
        ранг: 0-9 (0=High Card, 9=Royal Flush)
        """
        if len(cards) < 5:
            raise ValueError("Нужно минимум 5 карт")

        best_rank = -1
        best_kickers = []
        best_name = ""

        for combo in combinations(cards, 5):
            rank, kickers, name = HandEvaluator._evaluate_five(combo)
            if rank > best_rank or (rank == best_rank and kickers > best_kickers):
                best_rank = rank
                best_kickers = kickers
                best_name = name

        return best_rank, best_kickers, best_name

    @staticmethod
    def _evaluate_five(cards: Tuple[Card, ...]) -> Tuple[int, List[int], str]:
        values = sorted([c.value for c in cards], reverse=True)
        suits = [c.suit for c in cards]
        is_flush = len(set(suits)) == 1

        # Проверка на стрит
        is_straight = False
        straight_high = 0

        unique_vals = sorted(list(set(values)), reverse=True)
        if len(unique_vals) >= 5:
            for i in range(len(unique_vals) - 4):
                if unique_vals[i] - unique_vals[i + 4] == 4:
                    is_straight = True
                    straight_high = unique_vals[i]
                    break

        # Младший стрит (A-2-3-4-5)
        if set([14, 2, 3, 4, 5]).issubset(set(values)):
            is_straight = True
            straight_high = 5

        # Royal Flush
        if is_flush and is_straight and straight_high == 14:
            return 9, [14], "Royal Flush"

        # Straight Flush
        if is_flush and is_straight:
            return 8, [straight_high], "Straight Flush"

        # Four of a Kind
        counts = {}
        for v in values:
            counts[v] = counts.get(v, 0) + 1

        if 4 in counts.values():
            quad = [k for k, v in counts.items() if v == 4][0]
            kicker = [k for k in values if k != quad][0]
            return 7, [quad, kicker], "Four of a Kind"

        # Full House
        if 3 in counts.values() and 2 in counts.values():
            trip = [k for k, v in counts.items() if v == 3][0]
            pair = [k for k, v in counts.items() if v == 2][0]
            return 6, [trip, pair], "Full House"

        # Flush
        if is_flush:
            return 5, values, "Flush"

        # Straight
        if is_straight:
            return 4, [straight_high], "Straight"

        # Three of a Kind
        if 3 in counts.values():
            trip = [k for k, v in counts.items() if v == 3][0]
            kickers = [k for k in values if k != trip][:2]
            return 3, [trip] + kickers, "Three of a Kind"

        # Two Pair
        if list(counts.values()).count(2) == 2:
            pairs = sorted([k for k, v in counts.items() if v == 2], reverse=True)
            kicker = [k for k in values if k not in pairs][0]
            return 2, pairs + [kicker], "Two Pair"

        # One Pair
        if 2 in counts.values():
            pair = [k for k, v in counts.items() if v == 2][0]
            kickers = [k for k in values if k != pair][:3]
            return 1, [pair] + kickers, "One Pair"

        # High Card
        return 0, values, "High Card"

    @staticmethod
    def compare_hands(hand1_cards: List[Card], hand2_cards: List[Card]) -> int:
        """
        Сравнивает две руки (7 карт каждая)
        Возвращает: 1 если hand1 сильнее, 2 если hand2, 0 если ничья
        """
        rank1, kickers1, _ = HandEvaluator.evaluate(hand1_cards)
        rank2, kickers2, _ = HandEvaluator.evaluate(hand2_cards)

        if rank1 > rank2:
            return 1
        elif rank2 > rank1:
            return 2
        else:
            if kickers1 > kickers2:
                return 1
            elif kickers2 > kickers1:
                return 2
            else:
                return 0