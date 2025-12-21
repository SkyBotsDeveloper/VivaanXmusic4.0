import os
import re
import aiofiles
import aiohttp
from PIL import Image, ImageDraw, ImageFont
from youtubesearchpython.__future__ import VideosSearch
from config import YOUTUBE_IMG_URL
from VIVAANXMUSIC.core.dir import CACHE_DIR 

PANEL_W, PANEL_H = 450, 550
PANEL_X = (1280 - PANEL_W) // 2
PANEL_Y = (720 - PANEL_H) // 2
TRANSPARENCY = 200  # Slightly more opaque for a cleaner frosted look
INNER_OFFSET = 20
PANEL_RADIUS = 30  # Rounded corners for the main panel

THUMB_W, THUMB_H = 410, 230
THUMB_X = PANEL_X + INNER_OFFSET
THUMB_Y = PANEL_Y + INNER_OFFSET
THUMB_RADIUS = 15

TITLE_X = PANEL_X + INNER_OFFSET
TITLE_Y = THUMB_Y + THUMB_H + 25
MAX_TITLE_WIDTH = PANEL_W - 2 * INNER_OFFSET

# Vertical icons on the left
ICON_FONT_SIZE = 28
ICON_X = PANEL_X + 15
HEART_Y = THUMB_Y + 15
ADD_Y = HEART_Y + 50
SHARE_Y = ADD_Y + 50

# Progress bar
BAR_X = PANEL_X + INNER_OFFSET
BAR_Y = TITLE_Y + 80
BAR_RED_LEN = 150  # Placeholder progress; can be dynamic if needed
BAR_TOTAL_LEN = PANEL_W - 2 * INNER_OFFSET
BAR_HEIGHT = 4
DOT_RADIUS = 4
PLAY_BUTTON_SIZE = 30
PLAY_X = BAR_X + 60  # Positioned slightly after the start for visual balance
PLAY_Y = BAR_Y

# Time texts offset
TIME_OFFSET_Y = 25

def trim_to_width(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> str:
    ellipsis = "…"
    if hasattr(font, 'getlength') and font.getlength(text) <= max_w:
        return text
    # Fallback for older PIL versions
    bbox = font.getbbox(text)
    text_width = bbox[2] - bbox[0]
    if text_width <= max_w:
        return text
    for i in range(len(text) - 1, 0, -1):
        trimmed = text[:i] + ellipsis
        bbox_trim = font.getbbox(trimmed)
        trim_width = bbox_trim[2] - bbox_trim[0]
        if trim_width <= max_w:
            return trimmed
    return ellipsis

def draw_rounded_rectangle(draw: ImageDraw.ImageDraw, xy, radius: int, fill=None, outline=None, width=1):
    """Helper to draw rounded rectangle, compatible with older PIL."""
    x1, y1, x2, y2 = xy
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill, outline=outline, width=width)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill, outline=outline, width=width)
    draw.pieslice([x1 + radius, y1 + radius, x1 + 2 * radius, y1 + 2 * radius], 180, 270, fill=fill, outline=outline, width=width)
    draw.pieslice([x2 - 2 * radius, y1 + radius, x2 - radius, y1 + 2 * radius], 270, 360, fill=fill, outline=outline, width=width)
    draw.pieslice([x1 + radius, y2 - 2 * radius, x1 + 2 * radius, y2 - radius], 90, 180, fill=fill, outline=outline, width=width)
    draw.pieslice([x2 - 2 * radius, y2 - 2 * radius, x2 - radius, y2 - radius], 0, 90, fill=fill, outline=outline, width=width)

async def get_thumb(videoid: str) -> str:
    cache_path = os.path.join(CACHE_DIR, f"{videoid}_v5.png")  # Updated version for new style
    if os.path.exists(cache_path):
        return cache_path

    # YouTube video data fetch (unchanged for compatibility)
    results = VideosSearch(f"https://www.youtube.com/watch?v={videoid}", limit=1)
    try:
        results_data = await results.next()
        result_items = results_data.get("result", [])
        if not result_items:
            raise ValueError("No results found.")
        data = result_items[0]
        title = re.sub(r"\W+", " ", data.get("title", "Unsupported Title")).title()
        thumbnail = data.get("thumbnails", [{}])[0].get("url", YOUTUBE_IMG_URL)
        duration = data.get("duration")
        # Views not used in new design
    except Exception:
        title, thumbnail, duration = "Unsupported Title", YOUTUBE_IMG_URL, None

    is_live = not duration or str(duration).strip().lower() in {"", "live", "live now"}
    duration_text = "Live" if is_live else duration or "Unknown Mins"

    # Download thumbnail (unchanged)
    thumb_path = os.path.join(CACHE_DIR, f"thumb{videoid}.png")
    thumb_downloaded = False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail) as resp:
                if resp.status == 200:
                    async with aiofiles.open(thumb_path, "wb") as f:
                        await f.write(await resp.read())
                    thumb_downloaded = True
    except Exception:
        pass

    if not thumb_downloaded:
        # Fallback to default image handling
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(YOUTUBE_IMG_URL) as resp:
                    if resp.status == 200:
                        async with aiofiles.open(thumb_path, "wb") as f:
                            await f.write(await resp.read())
        except Exception:
            # If all fails, use a solid color or skip; but for now, proceed with error image
            pass

    # Create base image (enhanced blur for modern frosted effect)
    try:
        base = Image.open(thumb_path).resize((1280, 720)).convert("RGBA")
    except Exception:
        base = Image.new("RGBA", (1280, 720), (100, 149, 237, 255))  # Cornflower blue fallback
    # Stronger blur and lower brightness for a more subdued background
    bg = ImageEnhance.Brightness(base.filter(ImageFilter.BoxBlur(15))).enhance(0.4)

    # Frosted glass panel (updated radius and transparency)
    panel_area = bg.crop((PANEL_X, PANEL_Y, PANEL_X + PANEL_W, PANEL_Y + PANEL_H))
    overlay = Image.new("RGBA", (PANEL_W, PANEL_H), (255, 255, 255, TRANSPARENCY))
    frosted = Image.alpha_composite(panel_area, overlay)
    # Rounded mask for panel
    mask = Image.new("L", (PANEL_W, PANEL_H), 0)
    mask_draw = ImageDraw.Draw(mask)
    draw_rounded_rectangle(mask_draw, (0, 0, PANEL_W, PANEL_H), PANEL_RADIUS, fill=255)
    frosted.putalpha(mask)
    bg.paste(frosted, (PANEL_X, PANEL_Y), frosted)

    # Draw details
    draw = ImageDraw.Draw(bg)
    try:
        title_font = ImageFont.truetype("VIVAANXMUSIC/assets/thumb/font2.ttf", 28)  # Slightly smaller for better fit
        regular_font = ImageFont.truetype("VIVAANXMUSIC/assets/thumb/font.ttf", 18)
        icon_font = ImageFont.truetype("VIVAANXMUSIC/assets/thumb/font.ttf", ICON_FONT_SIZE)  # For icons
    except OSError:
        title_font = regular_font = icon_font = ImageFont.load_default()

    # Thumbnail paste with rounded corners
    thumb = base.resize((THUMB_W, THUMB_H))
    tmask = Image.new("L", thumb.size, 255)  # Full alpha initially
    tdraw = ImageDraw.Draw(tmask)
    draw_rounded_rectangle(tdraw, (0, 0, THUMB_W, THUMB_H), THUMB_RADIUS, fill=255)
    thumb.putalpha(tmask)
    bg.paste(thumb, (THUMB_X, THUMB_Y), thumb)

    # Title (trimmed)
    trimmed_title = trim_to_width(title, title_font, MAX_TITLE_WIDTH)
    draw.text((TITLE_X, TITLE_Y), trimmed_title, fill="black", font=title_font)

    # Vertical icons (using Unicode for simplicity; assumes font support; can replace with images if assets available)
    draw.text((ICON_X, HEART_Y), "♥", fill="black", font=icon_font)  # Heart
    draw.text((ICON_X, ADD_Y), "+", fill="black", font=icon_font)  # Add
    draw.text((ICON_X, SHARE_Y), "↗", fill="black", font=icon_font)  # Share/Up

    # Progress bar (thinner, more modern)
    bar_y_center = BAR_Y + BAR_HEIGHT // 2
    # Total bar (gray)
    draw.line([(BAR_X, bar_y_center), (BAR_X + BAR_TOTAL_LEN, bar_y_center)], fill="lightgray", width=BAR_HEIGHT)
    # Progress fill (red)
    draw.line([(BAR_X, bar_y_center), (BAR_X + BAR_RED_LEN, bar_y_center)], fill="#FF0000", width=BAR_HEIGHT)
    # Scrubber dot
    dot_x = BAR_X + BAR_RED_LEN
    dot_y = bar_y_center
    draw.ellipse([(dot_x - DOT_RADIUS, dot_y - DOT_RADIUS), (dot_x + DOT_RADIUS, dot_y + DOT_RADIUS)], fill="#FF0000")

    # Play button (circle with triangle)
    play_left = PLAY_X - PLAY_BUTTON_SIZE // 2
    play_top = PLAY_Y - PLAY_BUTTON_SIZE // 2
    play_right = PLAY_X + PLAY_BUTTON_SIZE // 2
    play_bottom = PLAY_Y + PLAY_BUTTON_SIZE // 2
    # Circle
    draw.ellipse([(play_left, play_top), (play_right, play_bottom)], fill="white", outline="black", width=2)
    # Play triangle (pointing right)
    tri_points = [
        (PLAY_X - 4, PLAY_Y - 6),
        (PLAY_X + 8, PLAY_Y),
        (PLAY_X - 4, PLAY_Y + 6)
    ]
    draw.polygon(tri_points, fill="black")

    # Time labels
    draw.text((BAR_X, BAR_Y + TIME_OFFSET_Y), "00:00", fill="black", font=regular_font)
    end_text_width = regular_font.getbbox(duration_text)[2] if hasattr(regular_font, 'getbbox') else 60
    end_text_x = BAR_X + BAR_TOTAL_LEN - end_text_width
    end_color = "#FF0000" if is_live else "black"
    draw.text((end_text_x, BAR_Y + TIME_OFFSET_Y), duration_text, fill=end_color, font=regular_font)

    # Cleanup
    try:
        os.remove(thumb_path)
    except OSError:
        pass

    # Save with high quality
    bg.convert("RGB").save(cache_path, "PNG", quality=95)
    return cache_path
