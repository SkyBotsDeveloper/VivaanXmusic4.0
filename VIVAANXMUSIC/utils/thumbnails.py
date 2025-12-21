import os
import re
import aiofiles
import aiohttp
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from youtubesearchpython.__future__ import VideosSearch
from config import YOUTUBE_IMG_URL
from VIVAANXMUSIC.core.dir import CACHE_DIR

# ============================================================================
#                          FONT PATHS (CONSTANTS)
# ============================================================================
TITLE_FONT_PATH = "VIVAANXMUSIC/assets/thumb/font2.ttf"
META_FONT_PATH = "VIVAANXMUSIC/assets/thumb/font.ttf"

# ============================================================================
#                    DESIGN SYSTEM - GRID & LAYOUT (720p)
# ============================================================================
# Canvas dimensions (standard YouTube thumbnail aspect ratio friendly)
CANVAS_W, CANVAS_H = 1280, 720

# ============================================================================
#                        LEFT SIDEBAR PANEL (WHITE)
# ============================================================================
LEFT_PANEL_X = 30
LEFT_PANEL_Y = 150
LEFT_PANEL_W = 90
LEFT_PANEL_H = 420
LEFT_PANEL_RADIUS = 15
LEFT_PANEL_COLOR = (255, 255, 255)

# Left panel icon positions (vertical centering: 420 / 4 = 105px spacing)
ICON_CENTER_X = LEFT_PANEL_X + (LEFT_PANEL_W // 2)
HEART_ICON_Y = LEFT_PANEL_Y + 50          # First icon
PLUS_ICON_Y = LEFT_PANEL_Y + 190          # Second icon (offset)
SHARE_ICON_Y = LEFT_PANEL_Y + 330         # Third icon (offset)

# ============================================================================
#                   CENTER THUMBNAIL CARD (BLACK FRAME)
# ============================================================================
CENTER_CARD_X = 280
CENTER_CARD_Y = 100
CENTER_CARD_W = 420
CENTER_CARD_H = 520
CENTER_CARD_RADIUS = 30
CENTER_CARD_COLOR = (0, 0, 0)

# YouTube thumbnail inside center card (with padding)
THUMB_INNER_W = 350
THUMB_INNER_H = 220
THUMB_INNER_X = CENTER_CARD_X + (CENTER_CARD_W - THUMB_INNER_W) // 2  # Centered
THUMB_INNER_Y = CENTER_CARD_Y + 70                                     # Positioned from top

# ============================================================================
#                       RIGHT SIDEBAR PANEL (WHITE)
# ============================================================================
RIGHT_PANEL_X = 1160
RIGHT_PANEL_Y = 150
RIGHT_PANEL_W = 90
RIGHT_PANEL_H = 420
RIGHT_PANEL_RADIUS = 15
RIGHT_PANEL_COLOR = (255, 255, 255)

# Right panel content positioning
TITLE_X = RIGHT_PANEL_X + 10
TITLE_Y = RIGHT_PANEL_Y + 20
ARTIST_X = RIGHT_PANEL_X + 10
ARTIST_Y = RIGHT_PANEL_Y + 65

# Progress bar (horizontal line inside right panel)
PROGRESS_X = RIGHT_PANEL_X + 8
PROGRESS_Y = RIGHT_PANEL_Y + 120
PROGRESS_W = 74
PROGRESS_H = 2

# Control buttons (bottom of right panel)
BUTTON_Y = RIGHT_PANEL_Y + 175
BUTTON_X_1 = RIGHT_PANEL_X + 15      # Previous button
BUTTON_X_2 = RIGHT_PANEL_X + 40      # Play button
BUTTON_X_3 = RIGHT_PANEL_X + 65      # Next button

# ============================================================================
#                            UTILITY FUNCTIONS
# ============================================================================

def load_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    """
    Load TrueType font with fallback to default if path not found.
    
    Args:
        font_path: Path to .ttf file
        size: Font size in pixels
    
    Returns:
        ImageFont.FreeTypeFont or ImageFont.FreeTypeFont (default)
    """
    try:
        return ImageFont.truetype(font_path, size)
    except (OSError, IOError):
        return ImageFont.load_default()

def trim_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    """
    Trim text to fit within max_width using ellipsis.
    
    Args:
        text: Text to trim
        font: ImageFont object for measurement
        max_width: Maximum pixel width
    
    Returns:
        Trimmed text with ellipsis if needed
    """
    ellipsis = "…"
    
    # If text fits, return as-is
    if font.getlength(text) <= max_width:
        return text
    
    # Binary trim from end until it fits
    for i in range(len(text) - 1, 0, -1):
        candidate = text[:i] + ellipsis
        if font.getlength(candidate) <= max_width:
            return candidate
    
    return ellipsis

def draw_text_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    fill: tuple = (0, 0, 0),
    anchor: str = "lm"
) -> None:
    """
    Draw text with optional centering.
    
    Args:
        draw: ImageDraw object
        text: Text to draw
        x, y: Position
        font: ImageFont object
        fill: RGB color tuple
        anchor: Alignment anchor ('lm' = left-middle, 'mm' = center-middle)
    """
    draw.text((x, y), text, font=font, fill=fill, anchor=anchor)

async def get_thumb(videoid: str, user_id: int = None) -> str:
    """
    Generate professional music player thumbnail - Meharbaan style.
    
    Layout:
    - Dark blurred background (YouTube thumbnail)
    - Left white panel with heart, plus, share icons
    - Center black card with YouTube thumbnail inside
    - Right white panel with title, artist, progress, controls
    
    Args:
        videoid: YouTube video ID (e.g., 'dQw4w9WgXcQ')
        user_id: Telegram user ID for potential future use
    
    Returns:
        Path to saved thumbnail PNG file
    """
    
    # === CACHE CHECK ===
    cache_path = os.path.join(CACHE_DIR, f"{videoid}_{user_id}_elite.png")
    if os.path.exists(cache_path):
        return cache_path

    # =========================================================================
    #                      FETCH VIDEO METADATA FROM YOUTUBE
    # =========================================================================
    try:
        results = VideosSearch(f"https://www.youtube.com/watch?v={videoid}", limit=1)
        results_data = await results.next()
        result_items = results_data.get("result", [])
        
        if not result_items:
            raise ValueError("No YouTube video found")
        
        data = result_items[0]
        
        # Extract metadata with fallbacks
        title = re.sub(r"\W+", " ", data.get("title", "Unsupported Title")).strip()
        thumbnail_url = data.get("thumbnails", [{}])[0].get("url", YOUTUBE_IMG_URL)
        channel = data.get("channel", {}).get("name", "YouTube")
        duration = data.get("duration", "Unknown")
        
    except Exception:
        # If YouTube fetch fails, return default image
        return YOUTUBE_IMG_URL

    # =========================================================================
    #                    DOWNLOAD YOUTUBE THUMBNAIL IMAGE
    # =========================================================================
    thumb_path = os.path.join(CACHE_DIR, f"thumb_{videoid}.png")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                thumbnail_url, 
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    async with aiofiles.open(thumb_path, "wb") as f:
                        await f.write(await resp.read())
                else:
                    return YOUTUBE_IMG_URL
    except Exception:
        return YOUTUBE_IMG_URL

    # =========================================================================
    #                        CREATE BASE IMAGE WITH BG
    # =========================================================================
    try:
        youtube_thumb = Image.open(thumb_path).convert("RGB")
    except Exception:
        return YOUTUBE_IMG_URL

    # Blur and darken YouTube thumbnail for background depth
    blurred = youtube_thumb.resize((CANVAS_W, CANVAS_H)).filter(
        ImageFilter.GaussianBlur(25)
    )
    darkened = ImageEnhance.Brightness(blurred).enhance(0.30)
    
    # Start with dark base, then overlay darkened thumbnail
    bg = Image.new("RGB", (CANVAS_W, CANVAS_H), (45, 45, 50))
    bg.paste(darkened, (0, 0))
    
    draw = ImageDraw.Draw(bg)

    # =========================================================================
    #                   DRAW LEFT SIDEBAR PANEL (WHITE)
    # =========================================================================
    draw.rounded_rectangle(
        xy=[
            (LEFT_PANEL_X, LEFT_PANEL_Y),
            (LEFT_PANEL_X + LEFT_PANEL_W, LEFT_PANEL_Y + LEFT_PANEL_H)
        ],
        radius=LEFT_PANEL_RADIUS,
        fill=LEFT_PANEL_COLOR,
        width=0
    )

    # =========================================================================
    #                  DRAW CENTER THUMBNAIL CARD (BLACK)
    # =========================================================================
    draw.rounded_rectangle(
        xy=[
            (CENTER_CARD_X, CENTER_CARD_Y),
            (CENTER_CARD_X + CENTER_CARD_W, CENTER_CARD_Y + CENTER_CARD_H)
        ],
        radius=CENTER_CARD_RADIUS,
        fill=CENTER_CARD_COLOR,
        width=0
    )

    # Paste YouTube thumbnail inside center card
    try:
        yt_img = youtube_thumb.resize((THUMB_INNER_W, THUMB_INNER_H))
        bg.paste(yt_img, (THUMB_INNER_X, THUMB_INNER_Y))
    except Exception:
        pass

    # =========================================================================
    #                   DRAW RIGHT SIDEBAR PANEL (WHITE)
    # =========================================================================
    draw.rounded_rectangle(
        xy=[
            (RIGHT_PANEL_X, RIGHT_PANEL_Y),
            (RIGHT_PANEL_X + RIGHT_PANEL_W, RIGHT_PANEL_Y + RIGHT_PANEL_H)
        ],
        radius=RIGHT_PANEL_RADIUS,
        fill=RIGHT_PANEL_COLOR,
        width=0
    )

    # =========================================================================
    #                         LOAD FONTS & SIZES
    # =========================================================================
    title_font = load_font(TITLE_FONT_PATH, 12)       # Song title font
    artist_font = load_font(META_FONT_PATH, 10)       # Artist name font
    icon_font = load_font(TITLE_FONT_PATH, 14)        # Icon font
    control_font = load_font(TITLE_FONT_PATH, 11)     # Button font

    # =========================================================================
    #               DRAW LEFT PANEL ICONS (HEART, PLUS, SHARE)
    # =========================================================================
    
    # Heart icon (red/pink color)
    draw.text(
        xy=(ICON_CENTER_X - 5, HEART_ICON_Y),
        text="♥",
        font=icon_font,
        fill=(220, 80, 100),
        anchor="mm"
    )
    
    # Plus icon (gray)
    draw.text(
        xy=(ICON_CENTER_X - 4, PLUS_ICON_Y),
        text="+",
        font=icon_font,
        fill=(120, 120, 120),
        anchor="mm"
    )
    
    # Share/Upload icon (gray)
    draw.text(
        xy=(ICON_CENTER_X - 5, SHARE_ICON_Y),
        text="⬆",
        font=icon_font,
        fill=(120, 120, 120),
        anchor="mm"
    )

    # =========================================================================
    #            DRAW RIGHT PANEL CONTENT (TEXT & PROGRESS & BUTTONS)
    # =========================================================================
    
    # Song Title
    title_trimmed = trim_text(title, title_font, 70)
    draw.text(
        xy=(TITLE_X, TITLE_Y),
        text=title_trimmed,
        font=title_font,
        fill=(0, 0, 0)
    )
    
    # Artist/Channel name
    artist_trimmed = trim_text(channel, artist_font, 70)
    draw.text(
        xy=(ARTIST_X, ARTIST_Y),
        text=artist_trimmed,
        font=artist_font,
        fill=(140, 140, 140)
    )

    # =========================================================================
    #                    PROGRESS BAR (BLACK LINE)
    # =========================================================================
    
    # Gray background bar
    draw.rectangle(
        xy=[
            (PROGRESS_X, PROGRESS_Y),
            (PROGRESS_X + PROGRESS_W, PROGRESS_Y + PROGRESS_H)
        ],
        fill=(200, 200, 200),
        width=0
    )
    
    # Black filled progress (35% filled)
    progress_fill = int(PROGRESS_W * 0.35)
    draw.rectangle(
        xy=[
            (PROGRESS_X, PROGRESS_Y),
            (PROGRESS_X + progress_fill, PROGRESS_Y + PROGRESS_H)
        ],
        fill=(0, 0, 0),
        width=0
    )

    # =========================================================================
    #              CONTROL BUTTONS (PREVIOUS, PLAY, NEXT)
    # =========================================================================
    
    buttons = [
        {"symbol": "⏮", "x": BUTTON_X_1},   # Previous
        {"symbol": "⏸", "x": BUTTON_X_2},   # Play/Pause
        {"symbol": "⏭", "x": BUTTON_X_3},   # Next
    ]
    
    for btn in buttons:
        draw.text(
            xy=(btn["x"] - 3, BUTTON_Y),
            text=btn["symbol"],
            font=control_font,
            fill=(110, 110, 110),
            anchor="mm"
        )

    # =========================================================================
    #                        CLEANUP & SAVE THUMBNAIL
    # =========================================================================
    
    # Remove temporary YouTube thumbnail file
    try:
        os.remove(thumb_path)
    except OSError:
        pass

    # Save final thumbnail as PNG
    bg.save(cache_path, "PNG", quality=95)
    
    return cache_path
