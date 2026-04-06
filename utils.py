from typing import List, Optional
from io import BytesIO
from pathlib import Path
from cards import Card
from skins import DEFAULT_SKIN
import asyncio
import os

try:
    from PIL import Image
except Exception:  # Pillow not installed or broken
    Image = None
try:
    from telegram.error import RetryAfter
except Exception:
    RetryAfter = None


def format_cards(cards: List[Card], hide: bool = False) -> str:
    if hide:
        return "🂠 " * len(cards)

    suits_colors = {
        '♠': '♠️',
        '♣': '♣️',
        '♥': '♥️',
        '♦': '♦️'
    }

    result = []
    for card in cards:
        emoji = suits_colors[card.suit]
        result.append(f"{card.rank}{emoji}")

    return " ".join(result)


def format_timer_bar(seconds_left: int, total_seconds: int = 30) -> str:
    """Create visual countdown progress bar for timer."""
    filled = int((seconds_left / total_seconds) * 10)
    empty = 10 - filled
    bar = "█" * filled + "░" * empty
    emoji = "🔴" if seconds_left <= 5 else "🟡" if seconds_left <= 15 else "🟢"
    return f"{emoji} [{bar}] {seconds_left}s"


def get_dealing_animation(phase: str) -> str:
    """Get animation text for dealing cards at different phases."""
    animations = {
        "flop": "🎴 🎴 🎴 Карты вылетают из колоды...",
        "turn": "🃏 Карта вылетает из колоды...",
        "river": "🎴 Карта вылетает из колоды...",
    }
    return animations.get(phase, "🃏 Раздача карт...")


def get_all_in_effect() -> str:
    """Visual effect for all-in moment."""
    return "🔥🔥🔥 ВСЁ В БАНК! 🔥🔥🔥"


def get_win_effect(is_big_win: bool = False) -> str:
    """Visual effect for win moment."""
    if is_big_win:
        return "🏆🎉💰 ДЖЕКПОТ! ОГРОМНАЯ ПОБЕДА! 💰🎉🏆"
    return "🎉🏆 ПОБЕДА! 🏆🎉"


def get_bad_beat_effect() -> str:
    """Visual effect for bad beat moment."""
    return "😱💔 БЭД-БИТ! НЕВЕРОЯТНО! 💔😱"


def get_chip_sound_emoji(amount: int) -> str:
    """Get chip emoji based on bet amount."""
    if amount >= 1000:
        return "💎💎💎"
    elif amount >= 500:
        return "💰💰"
    elif amount >= 100:
        return "💰"
    else:
        return "🪙"


def get_applause_animation() -> str:
    """Applause animation for winner."""
    return "👏👏👏 Аплодисменты! 👏👏👏"


def get_timer_tick_emoji(seconds_left: int) -> str:
    """Timer ticking emoji based on remaining time."""
    if seconds_left <= 5:
        return "⏰🔥"
    elif seconds_left <= 15:
        return "⏰⚡"
    else:
        return "⏰"


def format_mini_table_map(players: List[dict], current_idx: int, dealer_idx: int) -> str:
    """Create mini table map for corner display."""
    if len(players) <= 4:
        layout = [
            "  [2]  ",
            "[3]   [1]",
            "  [0]  "
        ]
    elif len(players) <= 6:
        layout = [
            "  [3]   ",
            "[4]   [2]",
            "[5]   [1]",
            "  [0]  "
        ]
    else:
        layout = [
            " [4] [3] [2] ",
            "[5]     [1]",
            "[6]     [0]",
            " [7] [8]    "
        ]
    
    result = []
    for line in layout:
        new_line = line
        for i, p in enumerate(players):
            marker = "▶️" if i == current_idx else "D" if i == dealer_idx else "●"
            status = "💀" if p.get('folded') else "🔥" if p.get('all_in') else marker
            new_line = new_line.replace(f"[{i}]", status)
        result.append(new_line)
    
    return "🗺️ <b>Стол:</b>\n<code>" + "\n".join(result) + "</code>"


def format_table(game) -> str:
    phase_names = {
        "waiting": "🎯 СБОР ИГРОКОВ",
        "preflop": "🃏 ПРЕФЛОП",
        "flop": "🎴 ФЛОП",
        "turn": "🃏 ТЕРН",
        "river": "🎴 РИВЕР",
        "showdown": "🏁 ВСКРЫТИЕ"
    }

    board = format_cards(game.community_cards) if game.community_cards else "🂠 🂠 🂠 🂠 🂠"
    
    header = f"🎰 <b>{phase_names.get(game.phase.value, game.phase.value.upper())}</b>"
    table_st = f"💰 <b>Банк:</b> {game.pot}\n"
    table_st += f"🃏 <b>Стол:</b> {board}\n\n"
    table_st += f"👥 <b>Игроки:</b>\n"

    player_list = ""
    for i, player in enumerate(game.players):
        pos = ""
        if i == game.dealer_pos: pos = "D"
        elif len(game.players) == 2:
            if i == (game.dealer_pos + 1) % 2: pos = "BB"
        else:
            if i == (game.dealer_pos + 1) % len(game.players): pos = "SB"
            elif i == (game.dealer_pos + 2) % len(game.players): pos = "BB"

        pos_str = f"[{pos}]" if pos else ""
        marker = "▶️" if i == game.current_player_idx and game.phase.value != "waiting" else "•"

        status = ""
        if player.folded:
            status = " 📴"
        elif player.all_in:
            status = " 🔥"
        elif not player.is_active:
            status = " ❌"

        bet_info = f" | {player.bet}" if player.bet > 0 else ""
        player_list += f"{marker} {player.first_name[:12]:<12} {pos_str:<4} {player.stack:>5}{bet_info}{status}\n"

    footer = f"🎯 <b>Текущая ставка:</b> {game.current_bet}"
    return f"{header}\n{table_st}<pre>{player_list.rstrip()}</pre>\n{footer}"


def get_mention(user_id: int, first_name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{first_name}</a>'


_CARD_ASSETS_ROOT = Path(__file__).resolve().parent / "Cards Design"
_SUIT_TO_FILENAME = {
    "♠": "spade",
    "♥": "heart",
    "♦": "diamond",
    "♣": "club",
}
_SKIN_FOLDER_MAP = {
    "classic": "Bordered",
    "ornate": "Ornamental",
}

_BACKS_FOLDER = _CARD_ASSETS_ROOT / "Backs"


def _resolve_skin_folder(skin_id: str) -> Optional[Path]:
    if not _CARD_ASSETS_ROOT.exists():
        return None
    folder_name = _SKIN_FOLDER_MAP.get(skin_id, "")
    if folder_name:
        path = _CARD_ASSETS_ROOT / folder_name
        if path.exists():
            return path
    # Fallback: try Title Case of skin_id (e.g., "golden" -> "Golden")
    candidate = _CARD_ASSETS_ROOT / skin_id.replace("_", " ").title()
    if candidate.exists():
        return candidate
    # Final fallback to Classic
    classic = _CARD_ASSETS_ROOT / _SKIN_FOLDER_MAP[DEFAULT_SKIN]
    return classic if classic.exists() else None


def _card_image_path(card: Card, skin_id: str) -> Optional[Path]:
    folder = _resolve_skin_folder(skin_id)
    if folder is None:
        return None
    suit_part = _SUIT_TO_FILENAME.get(card.suit)
    if not suit_part:
        return None
    filename = f"{card.rank}_{suit_part}.png"
    path = folder / filename
    return path if path.exists() else None


def card_image_path(card: Card, skin_id: str) -> Optional[Path]:
    return _card_image_path(card, skin_id)


def back_image_path(back_id: str) -> Optional[Path]:
    if not _BACKS_FOLDER.exists():
        return None
    path = _BACKS_FOLDER / f"{back_id}.png"
    if path.exists():
        return path
    blue_back = _BACKS_FOLDER / "blue_back.png"
    if blue_back.exists():
        return blue_back
    return None


def _build_cards_image(cards: List[Card], skin_id: str, max_height: int = 240, padding: int = 16,
                       card_scale: float = 0.84, face_scale: Optional[float] = None,
                       canvas_width: Optional[int] = None, canvas_height: Optional[int] = None,
                       table_skin: str = "classic"):
    if Image is None:
        return None
    if not cards:
        return None
    resample = Image.LANCZOS if hasattr(Image, "LANCZOS") else Image.Resampling.LANCZOS
    images = []
    face_ranks = {"J", "Q", "K"}
    face_scale = face_scale if face_scale is not None else card_scale
    for card in cards:
        path = _card_image_path(card, skin_id)
        if path is None:
            return None
        img = Image.open(path).convert("RGBA")
        target_h = int(max_height * card_scale)
        if card.rank in face_ranks:
            target_h = int(max_height * face_scale)
        scale = target_h / img.height
        new_w = max(1, int(img.width * scale))
        img = img.resize((new_w, target_h), resample)
        images.append(img)

    return _compose_images(
        images,
        max_height=max_height,
        padding=padding,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        table_skin=table_skin
    )


def _build_felt_canvas(width: int, height: int, table_skin: str = "classic"):
    if Image is None:
        return None
    # Get table skin color
    from skins import get_table_skin_info
    skin_info = get_table_skin_info(table_skin)
    base_color = skin_info.get("color", "#1c6e46")  # Default green
    
    # Parse hex color to RGB
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    base_rgb = hex_to_rgb(base_color)
    background = base_rgb + (255,)  # Add alpha
    
    canvas = Image.new("RGBA", (width, height), background)
    return canvas


def _compose_images(images: List["Image.Image"], max_height: int = 240, padding: int = 16,
                    canvas_width: Optional[int] = None, canvas_height: Optional[int] = None,
                    table_skin: str = "classic"):
    if Image is None:
        return None
    target_w = max(img.width for img in images)
    normalized = []
    for img in images:
        card_canvas = Image.new("RGBA", (target_w, max_height), (0, 0, 0, 0))
        x = (target_w - img.width) // 2
        y = (max_height - img.height) // 2
        card_canvas.alpha_composite(img, (x, y))
        normalized.append(card_canvas)

    total_w = target_w * len(normalized) + padding * (len(normalized) - 1)
    out_w = canvas_width or total_w
    out_h = canvas_height or max_height
    canvas = _build_felt_canvas(out_w, out_h, table_skin)
    if canvas is None:
        return None

    x = 0 if canvas_width is None else max((out_w - total_w) // 2, 0)
    y_offset = 0 if canvas_height is None else max((out_h - max_height) // 2, 0)

    for img in normalized:
        canvas.alpha_composite(img, (x, y_offset))
        x += target_w + padding

    return canvas


def build_cards_image_bytes_from_paths(paths: List[Path], max_height: int = 240, padding: int = 16,
                                       card_scale: float = 0.84,
                                       canvas_width: Optional[int] = None,
                                       canvas_height: Optional[int] = None) -> Optional[BytesIO]:
    if Image is None or not paths:
        return None
    resample = Image.LANCZOS if hasattr(Image, "LANCZOS") else Image.Resampling.LANCZOS
    images = []
    for path in paths:
        if not path.exists():
            return None
        img = Image.open(path).convert("RGBA")
        target_h = int(max_height * card_scale)
        scale = target_h / img.height
        new_w = max(1, int(img.width * scale))
        img = img.resize((new_w, target_h), resample)
        images.append(img)
    image = _compose_images(
        images,
        max_height=max_height,
        padding=padding,
        canvas_width=canvas_width,
        canvas_height=canvas_height
    )
    if image is None:
        return None
    buf = BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    buf.name = "cards.png"
    return buf


def build_cards_image_bytes(cards: List[Card], skin_id: str, max_height: int = 240, padding: int = 16,
                            card_scale: float = 0.84, face_scale: Optional[float] = None,
                            canvas_width: Optional[int] = None, canvas_height: Optional[int] = None,
                            table_skin: str = "classic") -> Optional[BytesIO]:
    image = _build_cards_image(
        cards,
        skin_id,
        max_height=max_height,
        padding=padding,
        card_scale=card_scale,
        face_scale=face_scale,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        table_skin=table_skin
    )
    if image is None:
        return None
    buf = BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    buf.name = "cards.png"
    return buf


async def send_cards_photo(bot, chat_id: int, cards: List[Card], skin_id: str = DEFAULT_SKIN,
                           caption: Optional[str] = None, parse_mode: Optional[str] = None,
                           max_height: int = 240, padding: int = 16,
                           card_scale: float = 0.84, face_scale: Optional[float] = None,
                           canvas_width: Optional[int] = None, canvas_height: Optional[int] = None,
                           table_skin: str = "classic"):
    img = build_cards_image_bytes(
        cards,
        skin_id,
        max_height=max_height,
        padding=padding,
        card_scale=card_scale,
        face_scale=face_scale,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        table_skin=table_skin
    )
    if img is None:
        return None
    while True:
        try:
            img.seek(0)
            return await bot.send_photo(chat_id, photo=img, caption=caption, parse_mode=parse_mode)
        except Exception as e:
            if RetryAfter is not None and isinstance(e, RetryAfter):
                await asyncio.sleep(e.retry_after)
                continue
            raise


async def send_cards_photo_from_paths(bot, chat_id: int, paths: List[Path],
                                      caption: Optional[str] = None, parse_mode: Optional[str] = None,
                                      max_height: int = 240, padding: int = 16,
                                      card_scale: float = 0.84,
                                      canvas_width: Optional[int] = None, canvas_height: Optional[int] = None):
    img = build_cards_image_bytes_from_paths(
        paths,
        max_height=max_height,
        padding=padding,
        card_scale=card_scale,
        canvas_width=canvas_width,
        canvas_height=canvas_height
    )
    if img is None:
        return None
    while True:
        try:
            img.seek(0)
            return await bot.send_photo(chat_id, photo=img, caption=caption, parse_mode=parse_mode)
        except Exception as e:
            if RetryAfter is not None and isinstance(e, RetryAfter):
                await asyncio.sleep(e.retry_after)
                continue
            raise


def build_showdown_table_image_bytes(
    left_cards: List[Path],
    right_cards: List[Path],
    board_cards: List[Path],
    text: str = "PokerHubs"
) -> Optional[BytesIO]:
    if Image is None:
        return None
    w, h = 1600, 900
    background = (24, 96, 62, 255)
    canvas = Image.new("RGBA", (w, h), background)

    def load_cards(paths, max_height):
        resample = Image.LANCZOS if hasattr(Image, "LANCZOS") else Image.Resampling.LANCZOS
        imgs = []
        for p in paths:
            if not p.exists():
                continue
            im = Image.open(p).convert("RGBA")
            scale = max_height / im.height
            new_w = max(1, int(im.width * scale))
            im = im.resize((new_w, max_height), resample)
            imgs.append(im)
        return imgs

    left_imgs = load_cards(left_cards, 300)
    right_imgs = load_cards(right_cards, 300)
    board_imgs = load_cards(board_cards, 240)

    def paste_row(imgs, center_x, y, padding=24):
        if not imgs:
            return
        total_w = sum(i.width for i in imgs) + padding * (len(imgs) - 1)
        x = center_x - total_w // 2
        for im in imgs:
            canvas.alpha_composite(im, (x, y))
            x += im.width + padding

    paste_row(left_imgs, w // 4, int(h * 0.54), padding=18)
    paste_row(right_imgs, (w * 3) // 4, int(h * 0.54), padding=18)
    paste_row(board_imgs, w // 2, int(h * 0.25), padding=18)

    # text
    try:
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(canvas)
        font_path = None
        for p in [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Helvetica.ttf",
            "/Library/Fonts/Arial.ttf",
        ]:
            if os.path.exists(p):
                font_path = p
                break
        font = ImageFont.truetype(font_path, 48) if font_path else ImageFont.load_default()
        box = draw.textbbox((0, 0), text, font=font)
        tw = box[2] - box[0]
        th = box[3] - box[1]
        draw.text(((w - tw) // 2, h - th - 24), text, font=font, fill=(240, 240, 240, 220))
    except Exception:
        pass

    buf = BytesIO()
    canvas.save(buf, format="PNG")
    buf.seek(0)
    buf.name = "showdown.png"
    return buf


def _load_card_images_from_paths(paths: List[Path], max_height: int):
    if Image is None:
        return []
    resample = Image.LANCZOS if hasattr(Image, "LANCZOS") else Image.Resampling.LANCZOS
    imgs = []
    for path in paths:
        if not path or not path.exists():
            w = int(max_height * 0.7)
            imgs.append(Image.new("RGBA", (w, max_height), (0,0,0,0)))
            continue
        img = Image.open(path).convert("RGBA")
        scale = max_height / img.height
        new_w = max(1, int(img.width * scale))
        img = img.resize((new_w, max_height), resample)
        imgs.append(img)
    return imgs


def _seat_positions(count: int, w: int, h: int):
    if count < 2:
        count = 2
    if count > 9:
        count = 9
    layouts = {
        2: [(w // 2, int(h * 0.78)), (w // 2, int(h * 0.18))],
        3: [(w // 2, int(h * 0.78)), (int(w * 0.27), int(h * 0.20)), (int(w * 0.73), int(h * 0.20))],
        4: [(w // 2, int(h * 0.78)), (int(w * 0.17), int(h * 0.48)), (w // 2, int(h * 0.18)), (int(w * 0.83), int(h * 0.48))],
        5: [(w // 2, int(h * 0.78)), (int(w * 0.22), int(h * 0.65)), (int(w * 0.26), int(h * 0.22)), (int(w * 0.74), int(h * 0.22)), (int(w * 0.78), int(h * 0.65))],
        6: [(w // 2, int(h * 0.78)), (int(w * 0.17), int(h * 0.63)), (int(w * 0.22), int(h * 0.24)), (w // 2, int(h * 0.16)), (int(w * 0.78), int(h * 0.24)), (int(w * 0.83), int(h * 0.63))],
        7: [(w // 2, int(h * 0.78)), (int(w * 0.15), int(h * 0.67)), (int(w * 0.14), int(h * 0.42)), (int(w * 0.30), int(h * 0.20)), (int(w * 0.70), int(h * 0.20)), (int(w * 0.86), int(h * 0.42)), (int(w * 0.85), int(h * 0.67))],
        8: [(w // 2, int(h * 0.78)), (int(w * 0.18), int(h * 0.70)), (int(w * 0.13), int(h * 0.49)), (int(w * 0.21), int(h * 0.23)), (w // 2, int(h * 0.16)), (int(w * 0.79), int(h * 0.23)), (int(w * 0.87), int(h * 0.49)), (int(w * 0.82), int(h * 0.70))],
        9: [(w // 2, int(h * 0.78)), (int(w * 0.23), int(h * 0.74)), (int(w * 0.13), int(h * 0.56)), (int(w * 0.14), int(h * 0.31)), (int(w * 0.33), int(h * 0.18)), (int(w * 0.67), int(h * 0.18)), (int(w * 0.86), int(h * 0.31)), (int(w * 0.87), int(h * 0.56)), (int(w * 0.77), int(h * 0.74))],
    }
    return layouts.get(count, layouts[2])


def _font_for_size(size: int):
    try:
        from PIL import ImageFont
        for path in [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
        ]:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        return ImageFont.load_default()
    except Exception:
        return None


def build_poker_table_image_bytes(
    seats: List[dict],
    board_paths: List[Path],
    text: str = "PokerHubs",
    table_skin: str = "classic"
) -> Optional[BytesIO]:
    if Image is None:
        return None
    try:
        from PIL import ImageDraw
    except Exception:
        return None

    # Get table skin colors
    from skins import get_table_skin_info
    skin_info = get_table_skin_info(table_skin)
    base_color = skin_info.get("color", "#2d5a27")
    
    # Parse hex color to RGB
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    base_rgb = hex_to_rgb(base_color)
    
    # Calculate derived colors based on skin
    felt_dark = (max(0, base_rgb[0] - 20), max(0, base_rgb[1] - 20), max(0, base_rgb[2] - 20))
    felt_light = (min(255, base_rgb[0] + 15), min(255, base_rgb[1] + 15), min(255, base_rgb[2] + 15))
    felt_mid = base_rgb
    
    # Border colors based on skin style
    border_style = skin_info.get("border_style", "wood")
    if border_style == "gold":
        border_color = (184, 134, 11, 255)  # Gold
        outer_color = (139, 69, 19, 255)    # Brown
    elif border_style == "platinum":
        border_color = (192, 192, 192, 255)  # Silver
        outer_color = (64, 64, 64, 255)     # Dark gray
    elif border_style == "rustic":
        border_color = (139, 90, 43, 255)    # Brown
        outer_color = (101, 67, 33, 255)    # Dark brown
    elif border_style == "metal":
        border_color = (80, 80, 80, 255)     # Gray
        outer_color = (40, 40, 40, 255)     # Dark
    else:  # wood default
        border_color = (53, 49, 50, 255)   # Dark wood
        outer_color = (24, 22, 23, 255)    # Darker

    w, h = 1600, 900
    canvas = Image.new("RGBA", (w, h), (33, 35, 38, 255))
    draw = ImageDraw.Draw(canvas)

    # outer pattern
    pattern_color = (255, 255, 255, 14)
    size = 88
    for y in range(-size, h + size, size):
        offset = 0 if (y // size) % 2 == 0 else size // 2
        for x in range(-size, w + size, size):
            cx = x + offset + size // 2
            cy = y + size // 2
            draw.polygon(
                [(cx, cy - 18), (cx + 18, cy), (cx, cy + 18), (cx - 18, cy)],
                outline=pattern_color
            )

    # table rail and felt with skin colors
    draw.rounded_rectangle((95, 70, w - 95, h - 70), radius=230, fill=outer_color)
    draw.rounded_rectangle((112, 86, w - 112, h - 86), radius=215, fill=border_color)
    draw.rounded_rectangle((152, 126, w - 152, h - 126), radius=185, fill=felt_dark + (255,))
    draw.rounded_rectangle((170, 144, w - 170, h - 144), radius=170, fill=felt_mid + (255,))

    # watermark
    title_font = _font_for_size(62)
    if title_font:
        box = draw.textbbox((0, 0), text, font=title_font)
        tw = box[2] - box[0]
        draw.text(((w - tw) // 2, int(h * 0.60)), text, font=title_font, fill=(12, 74, 39, 150))

    # board slots
    board_centers = [int(w * 0.34), int(w * 0.42), int(w * 0.50), int(w * 0.58), int(w * 0.66)]
    slot_y = int(h * 0.46)
    for cx in board_centers:
        draw.rounded_rectangle((cx - 56, slot_y - 82, cx + 56, slot_y + 82), radius=12, outline=(235, 205, 140, 90), width=4)

    board_imgs = _load_card_images_from_paths(board_paths[:5], 160)
    for i, img in enumerate(board_imgs[:5]):
        x = board_centers[i] - img.width // 2
        y = slot_y - img.height // 2
        canvas.alpha_composite(img, (x, y))

    # seats
    seat_points = _seat_positions(len(seats), w, h)
    name_font = _font_for_size(24)
    initial_font = _font_for_size(26)
    for seat, (cx, cy) in zip(seats, seat_points):
        card_imgs = _load_card_images_from_paths(seat.get("cards", [])[:2], 118)
        total_w = sum(img.width for img in card_imgs) + (14 if len(card_imgs) == 2 else 0)
        x = cx - total_w // 2
        y = cy - 59
        for idx, img in enumerate(card_imgs):
            canvas.alpha_composite(img, (x, y))
            x += img.width + (14 if idx == 0 else 0)

        name = (seat.get("name") or "Player")[:10]
        plate_w, plate_h = 180, 56
        if cy > h * 0.65:
            px, py = cx - plate_w // 2, y + 138
        elif cy < h * 0.30:
            px, py = cx - plate_w // 2, y - 76
        elif cx < w // 2:
            px, py = x - total_w - 110, cy - plate_h // 2
        else:
            px, py = x + 18, cy - plate_h // 2

        draw.rounded_rectangle((px, py, px + plate_w, py + plate_h), radius=28, fill=(224, 188, 119, 255), outline=(248, 226, 175, 180), width=3)
        draw.ellipse((px + 10, py + 8, px + 50, py + 48), fill=(245, 237, 222, 255))
        initials = "".join(part[:1] for part in name.split()[:2]).upper() or name[:1].upper()
        if initial_font:
            ibox = draw.textbbox((0, 0), initials, font=initial_font)
            iw = ibox[2] - ibox[0]
            ih = ibox[3] - ibox[1]
            draw.text((px + 30 - iw // 2, py + 28 - ih // 2 - 2), initials, font=initial_font, fill=(125, 108, 78, 255))
        if name_font:
            draw.text((px + 62, py + 15), name, font=name_font, fill=(70, 54, 30, 255))

    buf = BytesIO()
    canvas.save(buf, format="PNG")
    buf.seek(0)
    buf.name = "table.png"
    return buf


async def send_buffered_photo(bot, chat_id: int, img: BytesIO,
                              caption: Optional[str] = None, parse_mode: Optional[str] = None):
    if img is None:
        return None
    while True:
        try:
            img.seek(0)
            return await bot.send_photo(chat_id, photo=img, caption=caption, parse_mode=parse_mode)
        except Exception as e:
            if RetryAfter is not None and isinstance(e, RetryAfter):
                await asyncio.sleep(e.retry_after)
                continue
            raise
