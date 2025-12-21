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

# Left card (YouTube thumbnail card)
LEFT_CARD_X = 50
LEFT_CARD_Y = 120
LEFT_CARD_W, LEFT_CARD_H = 550, 480
LEFT_CARD_RADIUS = 20

# Right card (Player card)
RIGHT_CARD_X = 640
RIGHT_CARD_Y = 120
RIGHT_CARD_W, RIGHT_CARD_H = 590, 480
RIGHT_CARD_RADIUS = 20
RIGHT_CARD_COLOR = (255, 255, 255)

# Thumbnail circles
YOUTUBE_THUMB_RADIUS = 140
YOUTUBE_THUMB_X = LEFT_CARD_X + 50
YOUTUBE_THUMB_Y = LEFT_CARD_Y + 80

USER_DP_RADIUS = 85
USER_DP_X = RIGHT_CARD_X + 35
USER_DP_Y = RIGHT_CARD_Y + 60

# Text positioning (right card)
TITLE_X = RIGHT_CARD_X + 250
TITLE_Y = RIGHT_CARD_Y + 40

META_START_X = RIGHT_CARD_X + 250
CHANNEL_Y = RIGHT_CARD_Y + 100
VIEWS_Y = RIGHT_CARD_Y + 135
DURATION_Y = RIGHT_CARD_Y + 170

# Progress bar
PROGRESS_X = RIGHT_CARD_X + 250
PROGRESS_Y = RIGHT_CARD_Y + 220
PROGRESS_W = 310
PROGRESS_H = 4

# Time indicators
TIME_X_START = RIGHT_CARD_X + 250
TIME_X_END = RIGHT_CARD_X + 520
TIME_Y = RIGHT_CARD_Y + 245

# Control buttons
BUTTON_Y = RIGHT_CARD_Y + 310
BUTTON_SPACING = 65
BUTTONS = [
    {"label": "🔀", "x": RIGHT_CARD_X + 60},
    {"label": "⏮", "x": RIGHT_CARD_X + 125},
    {"label": "▶", "x": RIGHT_CARD_X + 190, "is_play": True},
    {"label": "⏭", "x": RIGHT_CARD_X + 320},
    {"label": "🔁", "x": RIGHT_CARD_X + 385},
]

# Volume bars
VOLUME_BAR_START_X = RIGHT_CARD_X + 50
VOLUME_BAR_Y = RIGHT_CARD_Y + 410
VOLUME_BARS_COUNT = 7

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

def extract_dominant_color(image: Image.Image) -> tuple:
    """Extract dominant color from image."""
    img = image.resize((10, 10))
    pixels = img.getdata()
    r = sum(p[0] if isinstance(p, tuple) else p for p in pixels) // len(pixels)
    g = sum(p[1] if isinstance(p, tuple) else p for p in pixels) // len(pixels)
    b = sum(p[2] if isinstance(p, tuple) else p for p in pixels) // len(pixels)
    return (r, g, b)

async def get_thumb(videoid: str, user_id: int = None) -> str:
    """
    Generate a professional music player thumbnail.
    
    Args:
        videoid: YouTube video ID
        user_id: Telegram user ID (optional, uses bot DP as fallback)
    
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
        views = data.get("viewCount", {}).get("short", "Unknown")
        channel = data.get("channel", {}).get("name", "YouTube")
    
    except Exception as e:
        return YOUTUBE_IMG_URL

    is_live = not duration or str(duration).strip().lower() in {"", "live", "live now"}
    duration_text = "Live" if is_live else duration

    # === DOWNLOAD IMAGES ===
    thumb_path = os.path.join(CACHE_DIR, f"thumb_{videoid}.png")
    user_dp_path = os.path.join(CACHE_DIR, f"dp_{user_id}.png")
    
    # Download YouTube thumbnail
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    async with aiofiles.open(thumb_path, "wb") as f:
                        await f.write(await resp.read())
    except Exception:
        return YOUTUBE_IMG_URL

    # Download user DP (if provided)
    try:
        from pyrogram import Client
        from VIVAANXMUSIC import app
        
        if user_id:
            user = await app.get_users(user_id)
            photo = await app.download_media(user.photo.file_id, file_name=user_dp_path)
        else:
            photo = None
    except Exception:
        photo = None

    # === CREATE BASE IMAGE ===
    try:
        youtube_thumb = Image.open(thumb_path).convert("RGB")
    except Exception:
        return YOUTUBE_IMG_URL

    # Blur and darken background
    blurred = youtube_thumb.resize((CANVAS_W, CANVAS_H)).filter(ImageFilter.GaussianBlur(15))
    darkened = ImageEnhance.Brightness(blurred).enhance(0.4)
    
    # Create white background
    bg = Image.new("RGB", (CANVAS_W, CANVAS_H), (20, 20, 25))
    bg.paste(darkened, (0, 0))

    # === DRAW RIGHT CARD (Player) ===
    draw = ImageDraw.Draw(bg)
    
    # Right card background (white rounded rectangle)
    draw.rounded_rectangle(
        [(RIGHT_CARD_X, RIGHT_CARD_Y), (RIGHT_CARD_X + RIGHT_CARD_W, RIGHT_CARD_Y + RIGHT_CARD_H)],
        radius=RIGHT_CARD_RADIUS,
        fill=RIGHT_CARD_COLOR
    )

    # === LOAD FONTS ===
    title_font = load_font(TITLE_FONT_PATH, 28)
    meta_font = load_font(META_FONT_PATH, 16)
    button_font = load_font(TITLE_FONT_PATH, 24)
    time_font = load_font(META_FONT_PATH, 14)

    # === DRAW CIRCLES ===
    # YouTube thumbnail circle (left side)
    youtube_circle_size = YOUTUBE_THUMB_RADIUS * 2
    youtube_circle = Image.new("RGBA", (youtube_circle_size, youtube_circle_size), (0, 0, 0, 0))
    
    # Draw white border
    circle_draw = ImageDraw.Draw(youtube_circle)
    circle_draw.ellipse((0, 0, youtube_circle_size - 1, youtube_circle_size - 1), fill=(255, 255, 255))
    
    # Paste thumbnail inside circle
    try:
        yt_img = Image.open(thumb_path).resize((youtube_circle_size - 8, youtube_circle_size - 8)).convert("RGB")
        yt_mask = create_circular_mask(youtube_circle_size - 8)
        youtube_circle.paste(yt_img, (4, 4), yt_mask)
    except Exception:
        pass
    
    bg.paste(youtube_circle, (YOUTUBE_THUMB_X - YOUTUBE_THUMB_RADIUS, YOUTUBE_THUMB_Y - YOUTUBE_THUMB_RADIUS), youtube_circle)

    # User DP circle (right side of card)
    user_circle_size = USER_DP_RADIUS * 2
    user_circle = Image.new("RGBA", (user_circle_size, user_circle_size), (0, 0, 0, 0))
    
    # Draw border
    user_draw = ImageDraw.Draw(user_circle)
    user_draw.ellipse((0, 0, user_circle_size - 1, user_circle_size - 1), fill=(100, 180, 220))
    
    # Paste user DP inside circle
    if photo and os.path.exists(photo):
        try:
            user_img = Image.open(photo).resize((user_circle_size - 6, user_circle_size - 6)).convert("RGB")
            user_mask = create_circular_mask(user_circle_size - 6)
            user_circle.paste(user_img, (3, 3), user_mask)
        except Exception:
            pass
    
    bg.paste(user_circle, (USER_DP_X - USER_DP_RADIUS, USER_DP_Y - USER_DP_RADIUS), user_circle)

    # === DRAW TEXT (Right Card) ===
    # Title
    title_trimmed = trim_text(title, title_font, 280)
    draw.text((TITLE_X, TITLE_Y), title_trimmed, fill=(0, 0, 0), font=title_font)

    # Metadata
    draw.text((META_START_X, CHANNEL_Y), f"Channel: {channel[:25]}", fill=(80, 80, 80), font=meta_font)
    draw.text((META_START_X, VIEWS_Y), f"Views: {views}", fill=(80, 80, 80), font=meta_font)
    draw.text((META_START_X, DURATION_Y), f"Duration: {duration_text}", fill=(80, 80, 80), font=meta_font)

    # === PROGRESS BAR ===
    # Gray background bar
    draw.rectangle(
        [(PROGRESS_X, PROGRESS_Y), (PROGRESS_X + PROGRESS_W, PROGRESS_Y + PROGRESS_H)],
        fill=(220, 220, 220)
    )
    
    # Red progress (60%)
    progress_amount = int(PROGRESS_W * 0.6)
    draw.rectangle(
        [(PROGRESS_X, PROGRESS_Y), (PROGRESS_X + progress_amount, PROGRESS_Y + PROGRESS_H)],
        fill=(255, 80, 80)
    )
    
    # Progress indicator circle
    circle_x = PROGRESS_X + progress_amount
    draw.ellipse(
        [(circle_x - 6, PROGRESS_Y - 4), (circle_x + 6, PROGRESS_Y + PROGRESS_H + 4)],
        fill=(255, 80, 80)
    )

    # === TIME INDICATORS ===
    draw.text((TIME_X_START, TIME_Y), "00:00", fill=(80, 80, 80), font=time_font)
    draw.text((TIME_X_END - 30, TIME_Y), duration_text, fill=(255, 80, 80), font=time_font)

    # === CONTROL BUTTONS ===
    for button in BUTTONS:
        x = button["x"]
        is_play = button.get("is_play", False)
        
        # Button background circle
        button_radius = 28 if is_play else 20
        button_color = (100, 180, 220) if is_play else (240, 240, 240)
        
        draw.ellipse(
            [(x - button_radius, BUTTON_Y - button_radius), (x + button_radius, BUTTON_Y + button_radius)],
            fill=button_color
        )
        
        # Button text
        text_color = (255, 255, 255) if is_play else (0, 0, 0)
        btn_font = load_font(TITLE_FONT_PATH, 26 if is_play else 20)
        
        # Center text in button
        bbox = draw.textbbox((0, 0), button["label"], font=btn_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        text_x = x - text_w // 2
        text_y = BUTTON_Y - text_h // 2
        
        draw.text((text_x, text_y), button["label"], fill=text_color, font=btn_font)

    # === VOLUME BARS ===
    bar_heights = [25, 35, 50, 65, 50, 35, 25]  # Waveform pattern
    for i, height in enumerate(bar_heights):
        bar_x = VOLUME_BAR_START_X + (i * 18)
        bar_y_top = VOLUME_BAR_Y - (height // 2)
        bar_y_bottom = VOLUME_BAR_Y + (height // 2)
        
        draw.rectangle(
            [(bar_x, bar_y_top), (bar_x + 10, bar_y_bottom)],
            fill=(100, 180, 220)
        )

    # === BRANDING ===
    branding_font = load_font(TITLE_FONT_PATH, 16)
    draw.text((LEFT_CARD_X + 20, 20), "Elite Musics", fill=(255, 255, 255), font=branding_font)

    # === CLEANUP & SAVE ===
    try:
        os.remove(thumb_path)
    except OSError:
        pass
    
    try:
        if photo and os.path.exists(photo):
            os.remove(photo)
    except OSError:
        pass

    bg.save(cache_path, "PNG")
    return cache_path
