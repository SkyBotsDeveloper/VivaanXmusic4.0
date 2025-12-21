import os
import re
import aiofiles
import aiohttp
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from youtubesearchpython.__future__ import VideosSearch
from config import YOUTUBE_IMG_URL
from VIVAANXMUSIC.core.dir import CACHE_DIR

# === FONT PATHS ===
TITLE_FONT_PATH = "VIVAANXMUSIC/assets/thumb/font2.ttf"
META_FONT_PATH = "VIVAANXMUSIC/assets/thumb/font.ttf"

# === DESIGN CONSTANTS ===
CANVAS_W, CANVAS_H = 1280, 720

# Left sidebar panel (white)
LEFT_PANEL_X = 30
LEFT_PANEL_Y = 150
LEFT_PANEL_W, LEFT_PANEL_H = 90, 420
LEFT_PANEL_RADIUS = 15
LEFT_PANEL_COLOR = (255, 255, 255)

# Center thumbnail card (black background)
CENTER_CARD_X = 160
CENTER_CARD_Y = 100
CENTER_CARD_W, CENTER_CARD_H = 500, 520
CENTER_CARD_RADIUS = 25
CENTER_CARD_COLOR = (0, 0, 0)

# Right sidebar panel (white)
RIGHT_PANEL_X = 1160
RIGHT_PANEL_Y = 150
RIGHT_PANEL_W, RIGHT_PANEL_H = 90, 420
RIGHT_PANEL_RADIUS = 15
RIGHT_PANEL_COLOR = (255, 255, 255)

# Left panel icon positions (vertical)
ICON_X = LEFT_PANEL_X + 30
HEART_Y = LEFT_PANEL_Y + 40
PLUS_Y = LEFT_PANEL_Y + 190
SHARE_Y = LEFT_PANEL_Y + 340

# Right panel positions
TITLE_X = RIGHT_PANEL_X + 10
TITLE_Y = RIGHT_PANEL_Y + 25
ARTIST_X = RIGHT_PANEL_X + 10
ARTIST_Y = RIGHT_PANEL_Y + 65

# Progress bar
PROGRESS_X = RIGHT_PANEL_X + 5
PROGRESS_Y = RIGHT_PANEL_Y + 120
PROGRESS_W = 80
PROGRESS_H = 3

# Control buttons (bottom right)
BUTTON_Y = RIGHT_PANEL_Y + 170
BUTTON_SPACING = 22

def load_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    """Load font with fallback."""
    try:
        return ImageFont.truetype(font_path, size)
    except OSError:
        return ImageFont.load_default()

def trim_text(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> str:
    """Trim text to fit width."""
    ellipsis = "…"
    if font.getlength(text) <= max_w:
        return text
    for i in range(len(text) - 1, 0, -1):
        if font.getlength(text[:i] + ellipsis) <= max_w:
            return text[:i] + ellipsis
    return ellipsis

async def get_thumb(videoid: str, user_id: int = None) -> str:
    """
    Generate thumbnail - Meharbaan style with sidebars.
    
    Args:
        videoid: YouTube video ID
        user_id: Telegram user ID (optional)
    
    Returns:
        Path to generated thumbnail
    """
    cache_path = os.path.join(CACHE_DIR, f"{videoid}_{user_id}_elite.png")
    if os.path.exists(cache_path):
        return cache_path

    # === FETCH VIDEO DATA ===
    try:
        results = VideosSearch(f"https://www.youtube.com/watch?v={videoid}", limit=1)
        results_data = await results.next()
        result_items = results_data.get("result", [])
        
        if not result_items:
            raise ValueError("No results")
        
        data = result_items[0]
        title = re.sub(r"\W+", " ", data.get("title", "Unsupported Title")).strip()
        thumbnail_url = data.get("thumbnails", [{}])[0].get("url", YOUTUBE_IMG_URL)
        channel = data.get("channel", {}).get("name", "YouTube")
    
    except Exception:
        return YOUTUBE_IMG_URL

    # === DOWNLOAD THUMBNAIL ===
    thumb_path = os.path.join(CACHE_DIR, f"thumb_{videoid}.png")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    async with aiofiles.open(thumb_path, "wb") as f:
                        await f.write(await resp.read())
    except Exception:
        return YOUTUBE_IMG_URL

    # === CREATE BASE IMAGE ===
    try:
        youtube_thumb = Image.open(thumb_path).convert("RGB")
    except Exception:
        return YOUTUBE_IMG_URL

    # Blur and darken background
    blurred = youtube_thumb.resize((CANVAS_W, CANVAS_H)).filter(ImageFilter.GaussianBlur(25))
    darkened = ImageEnhance.Brightness(blurred).enhance(0.35)
    
    # Create dark background
    bg = Image.new("RGB", (CANVAS_W, CANVAS_H), (50, 50, 55))
    bg.paste(darkened, (0, 0))

    draw = ImageDraw.Draw(bg)

    # === DRAW LEFT SIDEBAR PANEL ===
    draw.rounded_rectangle(
        [(LEFT_PANEL_X, LEFT_PANEL_Y), (LEFT_PANEL_X + LEFT_PANEL_W, LEFT_PANEL_Y + LEFT_PANEL_H)],
        radius=LEFT_PANEL_RADIUS,
        fill=LEFT_PANEL_COLOR
    )

    # === DRAW CENTER BLACK CARD ===
    draw.rounded_rectangle(
        [(CENTER_CARD_X, CENTER_CARD_Y), (CENTER_CARD_X + CENTER_CARD_W, CENTER_CARD_Y + CENTER_CARD_H)],
        radius=CENTER_CARD_RADIUS,
        fill=CENTER_CARD_COLOR
    )

    # Add YouTube thumbnail inside center card with padding
    try:
        thumb_inner_w, thumb_inner_h = 380, 250
        thumb_inner_x = CENTER_CARD_X + (CENTER_CARD_W - thumb_inner_w) // 2
        thumb_inner_y = CENTER_CARD_Y + 50
        
        yt_img = youtube_thumb.resize((thumb_inner_w, thumb_inner_h))
        bg.paste(yt_img, (thumb_inner_x, thumb_inner_y))
    except Exception:
        pass

    # === DRAW RIGHT SIDEBAR PANEL ===
    draw.rounded_rectangle(
        [(RIGHT_PANEL_X, RIGHT_PANEL_Y), (RIGHT_PANEL_X + RIGHT_PANEL_W, RIGHT_PANEL_Y + RIGHT_PANEL_H)],
        radius=RIGHT_PANEL_RADIUS,
        fill=RIGHT_PANEL_COLOR
    )

    # === LOAD FONTS ===
    title_font = load_font(TITLE_FONT_PATH, 13)
    artist_font = load_font(META_FONT_PATH, 11)
    control_font = load_font(TITLE_FONT_PATH, 11)

    # === LEFT PANEL ICONS ===
    # Heart
    draw.text((ICON_X - 6, HEART_Y), "♥", fill=(200, 80, 80), font=control_font)
    
    # Plus
    draw.text((ICON_X - 5, PLUS_Y), "+", fill=(100, 100, 100), font=control_font)
    
    # Share/Upload
    draw.text((ICON_X - 6, SHARE_Y), "⬆", fill=(100, 100, 100), font=control_font)

    # === RIGHT PANEL INFO ===
    # Title
    title_trimmed = trim_text(title, title_font, 75)
    draw.text((TITLE_X, TITLE_Y), title_trimmed, fill=(0, 0, 0), font=title_font)

    # Artist/Channel
    artist_trimmed = trim_text(channel, artist_font, 75)
    draw.text((ARTIST_X, ARTIST_Y), artist_trimmed, fill=(120, 120, 120), font=artist_font)

    # === PROGRESS BAR ===
    # Gray background
    draw.rectangle(
        [(PROGRESS_X, PROGRESS_Y), (PROGRESS_X + PROGRESS_W, PROGRESS_Y + PROGRESS_H)],
        fill=(200, 200, 200)
    )
    
    # Black progress (35%)
    progress_amt = int(PROGRESS_W * 0.35)
    draw.rectangle(
        [(PROGRESS_X, PROGRESS_Y), (PROGRESS_X + progress_amt, PROGRESS_Y + PROGRESS_H)],
        fill=(0, 0, 0)
    )

    # === CONTROL BUTTONS (RIGHT PANEL) ===
    buttons = [
        {"label": "⏮", "x": RIGHT_PANEL_X + 15},
        {"label": "⏸", "x": RIGHT_PANEL_X + 37},
        {"label": "⏭", "x": RIGHT_PANEL_X + 59},
    ]
    
    for btn in buttons:
        draw.text((btn["x"] - 5, BUTTON_Y), btn["label"], fill=(100, 100, 100), font=control_font)

    # === CLEANUP ===
    try:
        os.remove(thumb_path)
    except OSError:
        pass

    bg.save(cache_path, "PNG")
    return cache_path
