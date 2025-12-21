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
# Canvas dimensions
CANVAS_W, CANVAS_H = 1280, 720

# Left sidebar panel (white with icons)
LEFT_PANEL_X = 20
LEFT_PANEL_Y = 130
LEFT_PANEL_W, LEFT_PANEL_H = 100, 460
LEFT_PANEL_RADIUS = 20
LEFT_PANEL_COLOR = (255, 255, 255)

# Center thumbnail card (YouTube video)
CENTER_CARD_X = 140
CENTER_CARD_Y = 80
CENTER_CARD_W, CENTER_CARD_H = 500, 560
CENTER_CARD_RADIUS = 30
CENTER_CARD_COLOR = (0, 0, 0)

# Right sidebar panel (white with song info)
RIGHT_PANEL_X = 1160
RIGHT_PANEL_Y = 130
RIGHT_PANEL_W, RIGHT_PANEL_H = 100, 460
RIGHT_PANEL_RADIUS = 20
RIGHT_PANEL_COLOR = (255, 255, 255)

# Left panel icon positions
ICON_X = LEFT_PANEL_X + 35
HEART_ICON_Y = LEFT_PANEL_Y + 50
PLUS_ICON_Y = LEFT_PANEL_Y + 200
SHARE_ICON_Y = LEFT_PANEL_Y + 350

# Right panel text positioning
TITLE_X = RIGHT_PANEL_X + 10
TITLE_Y = RIGHT_PANEL_Y + 30
ARTIST_X = RIGHT_PANEL_X + 10
ARTIST_Y = RIGHT_PANEL_Y + 80

# Progress bar (right panel)
PROGRESS_X = RIGHT_PANEL_X + 5
PROGRESS_Y = RIGHT_PANEL_Y + 130
PROGRESS_W = 90
PROGRESS_H = 3

# Control buttons (right panel)
BUTTON_Y = RIGHT_PANEL_Y + 180
BUTTON_SIZE = 18

def load_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    """Load font with fallback to default."""
    try:
        return ImageFont.truetype(font_path, size)
    except OSError:
        return ImageFont.load_default()

def trim_text(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> str:
    """Trim text to fit within max width."""
    ellipsis = "…"
    if font.getlength(text) <= max_w:
        return text
    for i in range(len(text) - 1, 0, -1):
        if font.getlength(text[:i] + ellipsis) <= max_w:
            return text[:i] + ellipsis
    return ellipsis

def create_circular_mask(size: int) -> Image.Image:
    """Create a circular mask for images."""
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)
    return mask

async def get_thumb(videoid: str, user_id: int = None) -> str:
    """
    Generate a professional music player thumbnail - Spotify style.
    
    Args:
        videoid: YouTube video ID
        user_id: Telegram user ID (optional)
    
    Returns:
        Path to the generated thumbnail
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
            raise ValueError("No results found")
        
        data = result_items[0]
        title = re.sub(r"\W+", " ", data.get("title", "Unsupported Title")).strip()
        thumbnail_url = data.get("thumbnails", [{}])[0].get("url", YOUTUBE_IMG_URL)
        duration = data.get("duration", "00:00")
        channel = data.get("channel", {}).get("name", "YouTube")
    
    except Exception:
        return YOUTUBE_IMG_URL

    # === DOWNLOAD IMAGES ===
    thumb_path = os.path.join(CACHE_DIR, f"thumb_{videoid}.png")
    
    # Download YouTube thumbnail
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
    blurred = youtube_thumb.resize((CANVAS_W, CANVAS_H)).filter(ImageFilter.GaussianBlur(20))
    darkened = ImageEnhance.Brightness(blurred).enhance(0.3)
    
    # Create base with dark background
    bg = Image.new("RGB", (CANVAS_W, CANVAS_H), (40, 40, 45))
    bg.paste(darkened, (0, 0))

    draw = ImageDraw.Draw(bg)

    # === DRAW LEFT SIDEBAR PANEL ===
    draw.rounded_rectangle(
        [(LEFT_PANEL_X, LEFT_PANEL_Y), (LEFT_PANEL_X + LEFT_PANEL_W, LEFT_PANEL_Y + LEFT_PANEL_H)],
        radius=LEFT_PANEL_RADIUS,
        fill=LEFT_PANEL_COLOR
    )

    # === DRAW CENTER THUMBNAIL CARD ===
    # Black border/frame
    draw.rounded_rectangle(
        [(CENTER_CARD_X, CENTER_CARD_Y), (CENTER_CARD_X + CENTER_CARD_W, CENTER_CARD_Y + CENTER_CARD_H)],
        radius=CENTER_CARD_RADIUS,
        fill=CENTER_CARD_COLOR
    )

    # Add YouTube thumbnail inside the card
    try:
        # Load and resize thumbnail to fit inside card with padding
        thumb_inner_w, thumb_inner_h = 460, 290
        thumb_inner_x = CENTER_CARD_X + (CENTER_CARD_W - thumb_inner_w) // 2
        thumb_inner_y = CENTER_CARD_Y + 60
        
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
    title_font = load_font(TITLE_FONT_PATH, 14)
    artist_font = load_font(META_FONT_PATH, 12)
    control_font = load_font(TITLE_FONT_PATH, 12)

    # === DRAW LEFT PANEL ICONS ===
    # Heart icon
    draw.text((ICON_X - 8, HEART_ICON_Y), "♥", fill=(200, 100, 100), font=control_font)
    
    # Plus icon
    draw.text((ICON_X - 6, PLUS_ICON_Y), "+", fill=(100, 100, 100), font=control_font)
    
    # Share icon
    draw.text((ICON_X - 6, SHARE_ICON_Y), "⬆", fill=(100, 100, 100), font=control_font)

    # === DRAW RIGHT PANEL INFO ===
    # Title
    title_trimmed = trim_text(title, title_font, 80)
    draw.text((TITLE_X, TITLE_Y), title_trimmed, fill=(0, 0, 0), font=title_font)

    # Artist/Channel
    artist_trimmed = trim_text(channel, artist_font, 80)
    draw.text((ARTIST_X, ARTIST_Y), artist_trimmed, fill=(100, 100, 100), font=artist_font)

    # === PROGRESS BAR (RIGHT PANEL) ===
    # Gray background
    draw.rectangle(
        [(PROGRESS_X, PROGRESS_Y), (PROGRESS_X + PROGRESS_W, PROGRESS_Y + PROGRESS_H)],
        fill=(220, 220, 220)
    )
    
    # Black progress (30%)
    progress_amount = int(PROGRESS_W * 0.3)
    draw.rectangle(
        [(PROGRESS_X, PROGRESS_Y), (PROGRESS_X + progress_amount, PROGRESS_Y + PROGRESS_H)],
        fill=(0, 0, 0)
    )

    # === CONTROL BUTTONS (RIGHT PANEL) ===
    buttons_info = [
        {"label": "⏮", "x": RIGHT_PANEL_X + 20},
        {"label": "⏸", "x": RIGHT_PANEL_X + 50},
        {"label": "⏭", "x": RIGHT_PANEL_X + 80},
    ]
    
    for button in buttons_info:
        draw.text((button["x"] - 6, BUTTON_Y), button["label"], fill=(100, 100, 100), font=control_font)

    # === CLEANUP & SAVE ===
    try:
        os.remove(thumb_path)
    except OSError:
        pass

    bg.save(cache_path, "PNG")
    return cache_path
