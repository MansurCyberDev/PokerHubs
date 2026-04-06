import asyncio
import random
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from cards import Card, Deck, HandEvaluator
from config import STARTING_STACK, SMALL_BLIND, BIG_BLIND, TURN_TIME


class GamePhase(Enum):
    WAITING = "waiting"
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"


@dataclass
class Player:
    user_id: int
    username: str
    first_name: str
    stack: int = STARTING_STACK
    card_skin: str = "classic"
    table_skin: str = "classic"
    luck_multiplier: int = 0
    hand: List[Card] = field(default_factory=list)
    bet: int = 0
    total_bet: int = 0
    folded: bool = False
    all_in: bool = False
    is_active: bool = True
    last_action_seq: int = -1

    def reset_hand(self):
        self.hand = []
        self.bet = 0
        self.total_bet = 0
        self.folded = False
        self.all_in = False
        self.last_action_seq = -1


@dataclass
class SidePot:
    amount: int
    eligible_players: List[int]  # user_ids

@dataclass
class Game:
    chat_id: int
    id: int = field(default_factory=lambda: 0) # assigned on creation
    players: List[Player] = field(default_factory=list)
    phase: GamePhase = GamePhase.WAITING
    deck: Optional[Deck] = None
    community_cards: List[Card] = field(default_factory=list)
    pot: int = 0
    side_pots: List[SidePot] = field(default_factory=list)
    dealer_pos: int = 0
    current_player_idx: int = 0
    round_start_idx: int = 0
    current_bet: int = 0
    min_raise: int = BIG_BLIND
    last_full_raise_size: int = BIG_BLIND
    last_full_raise_seq: int = 0
    action_seq: int = 0
    small_blind: int = SMALL_BLIND
    big_blind: int = BIG_BLIND
    max_players: int = 9
    registration_task: Optional[asyncio.Task] = None
    turn_timer: Optional[asyncio.Task] = None
    last_raiser: Optional[int] = None
    pending_to_act: set[int] = field(default_factory=set)
    last_turn_message_id: Optional[int] = None
    last_board_message_id: Optional[int] = None
    registration_message_id: Optional[int] = None
    lobby_settings_message_id: Optional[int] = None
    stats_updated: bool = False

    def get_active_players(self) -> List[Player]:
        return [p for p in self.players if not p.folded and p.is_active and not p.all_in]

    def get_all_in_players(self) -> List[Player]:
        return [p for p in self.players if p.all_in and not p.folded]

    def next_active_player(self, start_idx: int) -> Optional[int]:
        count = len(self.players)
        for i in range(1, count + 1):
            idx = (start_idx + i) % count
            player = self.players[idx]
            if not player.folded and player.is_active and not player.all_in:
                return idx
        return None

    def next_pending_player(self, start_idx: int) -> Optional[int]:
        count = len(self.players)
        for i in range(1, count + 1):
            idx = (start_idx + i) % count
            player = self.players[idx]
            if idx in self.pending_to_act and not player.folded and player.is_active and not player.all_in:
                return idx
        return None

    def deal_hole_cards(self):
        self.deck = Deck()
        for player in self.players:
            if player.is_active:
                player.hand = self._deal_hand_with_luck(player)

    def _deal_hand_with_luck(self, player: Player) -> List[Card]:
        """Раздача с бустом шанса: чем выше процент, тем лучше рука."""
        luck = max(0, min(100, int(player.luck_multiplier or 0)))
        if luck <= 0:
            return self.deck.deal(2)

        # 100% luck = guaranteed best possible hand
        if luck == 100:
            return self._deal_best_possible_hand()
        
        # Пропорциональная система: чем выше удача, тем больше вариантов и лучше рука
        num_options = 1 + (luck // 20)  # 1-6 вариантов в зависимости от процента
        num_options = min(num_options, 6)  # максимум 6 вариантов
        
        if len(self.deck.cards) < num_options * 2 + 2:  # оставляем карты для других игроков
            return self.deck.deal(2)
        
        # Генерируем несколько вариантов стартовых рук
        options = []
        for _ in range(num_options):
            hand = self.deck.deal(2)
            score = self._hole_strength(hand)
            options.append((hand, score))
        
        # Выбираем лучший вариант с вероятностью, зависящей от удачи
        luck_factor = luck / 100.0
        if random.random() < luck_factor:
            # Выбираем лучшую руку
            best_option = max(options, key=lambda x: x[1])
            selected_hand = best_option[0]
        else:
            # Выбираем случайную руку из вариантов
            random_option = random.choice(options)
            selected_hand = random_option[0]
        
        # Возвращаем неиспользованные карты в колоду
        for hand, _ in options:
            if hand != selected_hand:
                self.deck.cards.extend(hand)
        
        # Перемешиваем колоду после возврата карт
        random.shuffle(self.deck.cards)
        
        return selected_hand

    def _deal_best_possible_hand(self) -> List[Card]:
        """Раздает лучшую возможную стартовую руку (пара тузов)."""
        # Ищем тузы в колоде
        aces = [card for card in self.deck.cards if card.rank == 'A']
        if len(aces) >= 2:
            # Убираем два туза из колоды и возвращаем их
            self.deck.cards.remove(aces[0])
            self.deck.cards.remove(aces[1])
            return [aces[0], aces[1]]
        else:
            # Если тузов меньше двух, ищем лучшую пару
            ranks = {}
            for card in self.deck.cards:
                if card.rank not in ranks:
                    ranks[card.rank] = []
                ranks[card.rank].append(card)
            
            # Ищем самую старшую пару
            best_rank = None
            for rank in ['A', 'K', 'Q', 'J', '10', '9', '8', '7', '6', '5', '4', '3', '2']:
                if rank in ranks and len(ranks[rank]) >= 2:
                    best_rank = rank
                    break
            
            if best_rank:
                cards = ranks[best_rank][:2]
                self.deck.cards.remove(cards[0])
                self.deck.cards.remove(cards[1])
                return cards
            else:
                # Если нет пар, возвращаем две старшие карты
                sorted_cards = sorted(self.deck.cards, key=lambda c: c.value, reverse=True)
                card1, card2 = sorted_cards[0], sorted_cards[1]
                self.deck.cards.remove(card1)
                self.deck.cards.remove(card2)
                return [card1, card2]

    def _hole_strength(self, hand: List[Card]) -> int:
        """Упрощенная сила стартовой руки для префлопа."""
        if len(hand) != 2:
            return 0
        c1, c2 = hand[0], hand[1]
        high = max(c1.value, c2.value)
        low = min(c1.value, c2.value)
        pair_bonus = 40 if c1.value == c2.value else 0
        suited_bonus = 8 if c1.suit == c2.suit else 0
        connector_bonus = 6 if abs(c1.value - c2.value) == 1 else 0
        broadway_bonus = 5 if high >= 11 and low >= 10 else 0
        return pair_bonus + high * 3 + low + suited_bonus + connector_bonus + broadway_bonus

    def post_blinds(self):
        # В игре 1 на 1 Дилер - это Малый Блайнд
        if len(self.players) == 2:
            sb_pos = self.dealer_pos
            bb_pos = (self.dealer_pos + 1) % 2
        else:
            sb_pos = (self.dealer_pos + 1) % len(self.players)
            bb_pos = (self.dealer_pos + 2) % len(self.players)

        sb_player = self.players[sb_pos]
        bb_player = self.players[bb_pos]

        sb_amount = min(self.small_blind, sb_player.stack)
        sb_player.stack -= sb_amount
        sb_player.bet = sb_amount
        sb_player.total_bet = sb_amount
        if sb_player.stack == 0:
            sb_player.all_in = True

        bb_amount = min(self.big_blind, bb_player.stack)
        bb_player.stack -= bb_amount
        bb_player.bet = bb_amount
        bb_player.total_bet = bb_amount
        if bb_player.stack == 0:
            bb_player.all_in = True

        self.pot = sb_amount + bb_amount
        self.current_bet = bb_amount
        self.min_raise = self.big_blind
        self.last_full_raise_size = self.big_blind
        self.last_full_raise_seq = 0
        self.action_seq = 0
        self.pending_to_act = {
            i for i, p in enumerate(self.players)
            if p.is_active and not p.folded and not p.all_in
        }
        for player in self.players:
            player.last_action_seq = -1

    def deal_community(self, count: int):
        if self.deck is None or len(self.deck.cards) < count + 1:  # +1 for burn card
            print(f"ERROR: Not enough cards in deck. Need {count + 1}, have {len(self.deck.cards) if self.deck else 0}")
            return  # Don't deal if not enough cards
        
        self.deck.burn()
        cards = self.deck.deal(count)
        
        # Удача влияет на общие карты для игроков с высоким процентом
        if count > 0:  # флоп (3), терн (1), ривер (1)
            self._apply_luck_to_community_cards(cards)
        
        self.community_cards.extend(cards)
    
    def _apply_luck_to_community_cards(self, cards: List[Card]):
        """Применяет удачу к общим картам - улучшает комбинации для игроков с высокой удачей."""
        if not cards:
            return
        
        # Находим игроков с максимальной удачей
        max_luck = 0
        lucky_players = []
        for player in self.players:
            if not player.folded and player.is_active:
                luck = max(0, min(100, int(player.luck_multiplier or 0)))
                if luck > 0:
                    lucky_players.append((player, luck))
                    max_luck = max(max_luck, luck)
        
        if not lucky_players or max_luck < 50:  # удача влияет только при 50%+
            return
        
        # Чем выше удача, тем выше шанс улучшить общие карты
        luck_factor = max_luck / 100.0
        if random.random() < luck_factor * 0.7:  # 70% от удачи как шанс
            self._improve_community_cards(cards, lucky_players)
    
    def _improve_community_cards(self, cards: List[Card], lucky_players: List[Tuple[Player, int]]):
        """Улучшает общие карты в пользу игроков с высокой удачей."""
        if len(self.deck.cards) < 5:
            return
        
        # Собираем все карты игроков с высокой удачей
        player_cards = []
        for player, luck in lucky_players:
            if luck >= 50:  # только для игроков с 50%+ удачи
                player_cards.extend(player.hand)
        
        if not player_cards:
            return
        
        # Ищем карты, которые могут улучшить комбинации
        improved_cards = self._find_better_community_cards(cards, player_cards)
        
        if improved_cards and len(improved_cards) == len(cards):
            # Заменяем карты в колоде
            for i, card in enumerate(cards):
                self.deck.cards.append(card)  # возвращаем старую карту
            
            for i, new_card in enumerate(improved_cards):
                cards[i] = new_card
                if new_card in self.deck.cards:
                    self.deck.cards.remove(new_card)
            
            random.shuffle(self.deck.cards)
    
    def _find_better_community_cards(self, current_cards: List[Card], player_cards: List[Card]) -> List[Card]:
        """Ищет лучшие общие карты для игроков с удачей."""
        if not current_cards or not player_cards:
            return current_cards
        
        # Создаем все возможные комбинации с текущими картами
        best_improvements = []
        
        # Пробуем найти карты, которые создают лучшие комбинации
        for _ in range(10):  # пробуем 10 вариантов
            test_cards = []
            for _ in current_cards:
                if self.deck.cards:
                    test_card = random.choice(self.deck.cards)
                    test_cards.append(test_card)
            
            if len(test_cards) == len(current_cards):
                # Оцениваем потенциальные комбинации
                current_score = self._evaluate_potential(current_cards, player_cards)
                test_score = self._evaluate_potential(test_cards, player_cards)
                
                if test_score > current_score:
                    best_improvements = test_cards
        
        return best_improvements if best_improvements else current_cards
    
    def _evaluate_potential(self, community_cards: List[Card], player_cards: List[Card]) -> int:
        """Оценивает потенциал общих карт для игроков."""
        if not community_cards or not player_cards:
            return 0
        
        max_score = 0
        for i in range(0, len(player_cards), 2):
            if i + 1 < len(player_cards):
                hand = player_cards[i:i+2] + community_cards
                if len(hand) >= 5:
                    try:
                        rank, kickers, _ = HandEvaluator.evaluate(hand[:5])
                        score = rank * 1000000 + sum(kickers)
                        max_score = max(max_score, score)
                    except:
                        pass
        
        return max_score

    def get_player_options(self, player: Player) -> List[str]:
        options = []

        if player.folded or player.all_in:
            return options

        player_idx = next((i for i, p in enumerate(self.players) if p.user_id == player.user_id), None)
        if player_idx is None:
            return options

        to_call = self.current_bet - player.bet

        if to_call <= 0:
            options.append("check")
            if self.current_bet == 0:
                if player.stack >= min(self.big_blind, player.stack):
                    options.append("bet")
            elif self._can_make_full_raise(player_idx):
                options.append("raise")
        else:
            options.append("fold")
            options.append("call")
            if self._can_make_full_raise(player_idx):
                options.append("raise")

        if player.stack > 0:
            options.append("all_in")
        return options

    def place_bet(self, player_idx: int, action: str, amount: int = 0) -> bool:
        player = self.players[player_idx]
        max_total = self._heads_up_limit(player_idx)
        current_bet_before_action = self.current_bet

        def cap_total(target_total: int) -> int:
            capped = player.stack + player.bet
            if max_total is not None:
                capped = min(capped, max_total)
            return max(player.bet, min(target_total, capped))

        def commit_to_total(target_total: int):
            to_add = max(0, target_total - player.bet)
            player.stack -= to_add
            player.bet += to_add
            player.total_bet += to_add
            self.pot += to_add
            if player.stack == 0:
                player.all_in = True
            return to_add

        valid_options = self.get_player_options(player)
        if action not in valid_options and action != "all_in": # all_in can be a secondary option for raise/bet
             if not (action == "all_in" and "all_in" in valid_options):
                return self.is_round_complete()

        def note_action(full_raise: bool = False, current_target: Optional[int] = None):
            self.action_seq += 1
            player.last_action_seq = self.action_seq
            if current_target is not None and current_target > current_bet_before_action:
                raise_size = current_target - current_bet_before_action
                self.current_bet = current_target
                if full_raise:
                    self.last_full_raise_size = raise_size
                    self.min_raise = self.last_full_raise_size
                    self.last_full_raise_seq = self.action_seq
                self.pending_to_act = {
                    i for i, p in enumerate(self.players)
                    if i != player_idx and p.is_active and not p.folded and not p.all_in
                }
            else:
                self.pending_to_act.discard(player_idx)

        if action == "fold":
            player.folded = True
            note_action(full_raise=False)
        elif action == "check":
            note_action(full_raise=False)
        elif action == "call":
            target_total = cap_total(self.current_bet)
            commit_to_total(target_total)
            note_action(full_raise=False)

        elif action == "bet" or action == "raise":
            if self.current_bet == 0:
                target_total = cap_total(max(amount, self.big_blind))
                commit_to_total(target_total)
                full_raise = target_total >= self.big_blind
                note_action(full_raise=full_raise, current_target=target_total)
                if full_raise:
                    self.last_raiser = player_idx
            else:
                # Fix: amount from keyboard is already the target total, not the raise increment
                # Keyboard shows: "2x Raise (20000)" where 20000 is the target total
                # So we should use amount directly, not current_bet + amount
                target_total = cap_total(max(amount, self.current_bet + self.min_raise))
                print(f"DEBUG RAISE: current_bet={self.current_bet}, amount={amount}, min_raise={self.min_raise}, target_total={target_total}")
                commit_to_total(target_total)
                full_raise = (target_total - current_bet_before_action) >= self.last_full_raise_size
                note_action(full_raise=full_raise, current_target=target_total)
                if full_raise:
                    self.last_raiser = player_idx

        elif action == "all_in":
            target_total = cap_total(player.stack + player.bet)
            commit_to_total(target_total)
            if target_total > current_bet_before_action:
                full_raise = (target_total - current_bet_before_action) >= self.last_full_raise_size
                note_action(full_raise=full_raise, current_target=target_total)
                if full_raise:
                    self.last_raiser = player_idx
            else:
                note_action(full_raise=False)

        return self.is_round_complete()

    def is_round_complete(self) -> bool:
        active = [i for i, p in enumerate(self.players) if p.is_active and not p.folded and not p.all_in]
        if not active:
            return True
        return len(self.pending_to_act) == 0

    def next_phase(self) -> GamePhase:
        for p in self.players:
            p.bet = 0
            p.last_action_seq = -1
        self.current_bet = 0
        self.min_raise = self.big_blind
        self.last_full_raise_size = self.big_blind
        self.last_full_raise_seq = 0
        self.action_seq = 0
        self.last_raiser = None  # FIX: Reset last_raiser for new phase

        if self.phase == GamePhase.PREFLOP:
            self.deal_community(3)
            self.phase = GamePhase.FLOP
            self.current_player_idx = (self.dealer_pos + 1) % len(self.players)
            self.round_start_idx = self.current_player_idx
        elif self.phase == GamePhase.FLOP:
            self.deal_community(1)
            self.phase = GamePhase.TURN
            self.current_player_idx = (self.dealer_pos + 1) % len(self.players)
            self.round_start_idx = self.current_player_idx
        elif self.phase == GamePhase.TURN:
            self.deal_community(1)
            self.phase = GamePhase.RIVER
            self.current_player_idx = (self.dealer_pos + 1) % len(self.players)
            self.round_start_idx = self.current_player_idx
        elif self.phase == GamePhase.RIVER:
            self.phase = GamePhase.SHOWDOWN

        self.pending_to_act = {
            i for i, p in enumerate(self.players)
            if p.is_active and not p.folded and not p.all_in
        }
        self._skip_inactive()
        return self.phase

    def _skip_inactive(self):
        while self.players[self.current_player_idx].folded or \
                self.players[self.current_player_idx].all_in or \
                not self.players[self.current_player_idx].is_active:
            next_idx = self.next_active_player(self.current_player_idx)
            if next_idx is None:
                break
            self.current_player_idx = next_idx

    def _seat_order_after_button(self, user_ids: List[int]) -> List[int]:
        ordered = []
        if not self.players:
            return ordered
        start_idx = (self.dealer_pos + 1) % len(self.players)
        for offset in range(len(self.players)):
            idx = (start_idx + offset) % len(self.players)
            user_id = self.players[idx].user_id
            if user_id in user_ids:
                ordered.append(user_id)
        return ordered

    def determine_winners(self) -> List[Tuple[Player, str, int]]:
        """
        Возвращает список (победитель, название_руки, сумма)
        """
        # Сначала рассчитаем побочные банки
        self._calculate_side_pots()
        
        results = []
        # Сортируем банки от последнего к первому (или наоборот, главное - последовательно)
        # Обычно сначала распределяем основной банк, потом побочные.
        # Но проще пройтись по всем созданным SidePot.
        
        for pot in self.side_pots:
            if pot.amount <= 0:
                continue
                
            eligible = [p for p in self.players if p.user_id in pot.eligible_players and not p.folded]
            if not eligible:
                # Если никто не претендует (все сбросились), отдаем последнему активному
                # Но в побочный банк попадают только те, кто вложился.
                # В реальном покере это редкая ситуация, фиксим упрощенно.
                continue
                
            # Оцениваем руки претендентов
            best_hands = []
            for player in eligible:
                all_cards = player.hand + self.community_cards
                rank, kickers, name = HandEvaluator.evaluate(all_cards)
                best_hands.append((player, rank, kickers, name))
            
            max_rank = max(h[1] for h in best_hands)
            candidates = [h for h in best_hands if h[1] == max_rank]
            max_kickers = max(h[2] for h in candidates)
            pot_winners = [h for h in candidates if h[2] == max_kickers]
            ordered_winner_ids = self._seat_order_after_button([winner.user_id for winner, *_ in pot_winners])
            pot_winners.sort(key=lambda hand: ordered_winner_ids.index(hand[0].user_id))

            share = pot.amount // len(pot_winners)
            remainder = pot.amount % len(pot_winners)
            
            for i, (winner, rank, kickers, name) in enumerate(pot_winners):
                win_amount = share + (remainder if i == 0 else 0)
                results.append((winner, name, win_amount))
                
        return results

    def _calculate_side_pots(self):
        """Расчет побочных банков на основе вложений (total_bet)"""
        self.side_pots = []
        # Копируем вложения, чтобы не портить статистику
        remaining_bets = {p.user_id: p.total_bet for p in self.players if p.total_bet > 0}
        
        while any(bet > 0 for bet in remaining_bets.values()):
            # Находим минимальное вложение среди тех, кто еще претендует на что-то
            active_bets = [bet for bet in remaining_bets.values() if bet > 0]
            if not active_bets: break
            min_bet = min(active_bets)
            
            pot_amount = 0
            eligible = []
            for p in self.players:
                if p.user_id in remaining_bets and remaining_bets[p.user_id] > 0:
                    contribution = min(remaining_bets[p.user_id], min_bet)
                    pot_amount += contribution
                    remaining_bets[p.user_id] -= contribution
                    eligible.append(p.user_id)
            
            self.side_pots.append(SidePot(pot_amount, eligible))

    def end_hand(self):
        self.dealer_pos = (self.dealer_pos + 1) % len(self.players)
        self.phase = GamePhase.WAITING
        self.community_cards = []
        self.pot = 0
        self.side_pots = []
        self.current_bet = 0
        self.min_raise = self.big_blind
        self.last_full_raise_size = self.big_blind
        self.last_full_raise_seq = 0
        self.action_seq = 0
        self.pending_to_act = set()
        self.stats_updated = False

        for p in self.players:
            if p.stack > 0:
                p.reset_hand()
            else:
                p.is_active = False

    def _heads_up_limit(self, player_idx: int) -> Optional[int]:
        active = [i for i, p in enumerate(self.players) if p.is_active and not p.folded]
        if len(active) != 2:
            return None
        opp_idx = active[0] if active[1] == player_idx else active[1]
        player = self.players[player_idx]
        opp = self.players[opp_idx]
        return min(player.stack + player.bet, opp.stack + opp.bet)

    def heads_up_limit(self, player_idx: int) -> Optional[int]:
        return self._heads_up_limit(player_idx)

    def _can_make_full_raise(self, player_idx: int) -> bool:
        player = self.players[player_idx]
        to_call = max(0, self.current_bet - player.bet)
        if player.stack <= to_call:
            return False
        if player.last_action_seq >= self.last_full_raise_seq and self.current_bet > 0:
            return False

        max_total = self._heads_up_limit(player_idx)
        if self.current_bet == 0:
            min_target = self.big_blind
        else:
            min_target = self.current_bet + self.last_full_raise_size

        if max_total is not None and max_total < min_target:
            return False
        return (player.stack + player.bet) >= min_target


active_games: Dict[int, Game] = {}
