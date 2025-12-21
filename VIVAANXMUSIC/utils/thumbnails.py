import os
import re
import aiofiles
import aiohttp
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from youtubesearchpython.__future__ import VideosSearch
from config import YOUTUBE_IMG_URL
from VIVAANXMUSIC.core.dir import CACHE_DIR 

# Dimensions adjusted to match the compact, vertical-ish design
PANEL_W, PANEL_H = 380, 520  # Narrower and taller for the example
PANEL_X = (1280 - PANEL_W) // 2 + 100  # Slightly offset to left for asymmetry
PANEL_Y = (720 - PANEL_H) // 2
TRANSPARENCY = 180  # Fine-tuned for frosted white panel
INNER_OFFSET = 20
PANEL_RADIUS = 25  # Softer rounded corners

THUMB_W, THUMB_H = 340, 340  # Square thumbnail to match
THUMB_X = PANEL_X + INNER_OFFSET
THUMB_Y = PANEL_Y + INNER_OFFSET + 40  # Slightly lower to fit title space above
THUMB_RADIUS = 20

# Title overlay on thumbnail
TITLE_OVERLAY_Y = THUMB_Y - 30  # Position for large song title on thumb
ARTIST_OVERLAY_Y = TITLE_OVERLAY_Y + 50  # Artist below title on thumb

# Panel content
CHANNEL_Y = PANEL_Y + INNER_OFFSET + 10  # Channel at top
ARTIST_PANEL_Y = THUMB_Y + THUMB_H + 20  # Artist repeat? But in example, artist is on thumb and panel
SONG_PANEL_Y = ARTIST_PANEL_Y + 25  # Song title in panel below thumb? Wait, example has artist in panel

# From example: Panel has "Darshan Raval ---" and "Haara" below? No, looking: Artist full, then song.
# Adjust: Channel top, then artist below thumb, song below artist? But example shows artist prominent.

# Vertical icons (left of panel, but in example right of thumb? Wait, left side)
ICON_FONT_SIZE = 24
ICON_X = PANEL_X - 40  # To the left of panel
HEART_Y = THUMB_Y + 20
ADD_Y = HEART_Y + 50
UP_Y = ADD_Y + 50

# Progress bar below song
BAR_X = PANEL_X + INNER_OFFSET
BAR_Y = SONG_PANEL_Y + 60
BAR_RED_LEN = 180  # Adjusted for progress
BAR_TOTAL_LEN = PANEL_W - 2 * INNER_OFFSET
BAR_HEIGHT = 4
DOT_RADIUS = 6
PLAY_X = BAR_X + 40
PLAY_Y = BAR_Y + BAR_HEIGHT // 2

# Time offset
TIME_OFFSET_Y = 25

# Red tint for thumbnail
RED_TINT = (255, 100, 100, 128)  # Semi-transparent red overlay for tint

def trim_to_width(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> str:
    ellipsis = "…"
    def get_text_width(t):
        if hasattr(font, 'getlength'):
            return font.getlength(t)
        else:
            bbox = font.getbbox(t)
            return bbox[2] - bbox[0]
    
    text_width = get_text_width(text)
    if text_width <= max_w:
        return text
    for i in range(len(text) - 1, 0, -1):
        trimmed = text[:i] + ellipsis
        trim_width = get_text_width(trimmed)
        if trim_width <= max_w:
            return trimmed
    return ellipsis

def draw_rounded_rectangle(draw: ImageDraw.ImageDraw, xy, radius: int, fill=None, outline=None, width=1):
    """Helper to draw rounded rectangle."""
    x1, y1, x2, y2 = xy
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill, outline=outline, width=width)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill, outline=outline, width=width)
    draw.pieslice([x1 + radius, y1 + radius, x1 + 2 * radius, y1 + 2 * radius], 180, 270, fill=fill, outline=outline, width=width)
    draw.pieslice([x2 - 2 * radius, y1 + radius, x2 - radius, y1 + 2 * radius], 270, 360, fill=fill, outline=outline, width=width)
    draw.pieslice([x1 + radius, y2 - 2 * radius, x1 + 2 * radius, y2 - radius], 90, 180, fill=fill, outline=outline, width=width)
    draw.pieslice([x2 - 2 * radius, y2 - 2 * radius, x2 - radius, y2 - radius], 0, 90, fill=fill, outline=outline, width=width)

async def get_thumb(videoid: str) -> str:
    cache_path = os.path.join(CACHE_DIR, f"{videoid}_v7.png")  # New version
    if os.path.exists(cache_path):
        return cache_path

    # Fetch data
    results = VideosSearch(f"https://www.youtube.com/watch?v={videoid}", limit=1)
    try:
        results_data = await results.next()
        result_items = results_data.get("result", [])
        if not result_items:
            raise ValueError("No results found.")
        data = result_items[0]
        title = data.get("title", "Unsupported Title")  # Song title
        thumbnail = data.get("thumbnails", [{}])[0].get("url", YOUTUBE_IMG_URL)
        duration = data.get("duration")
        channel = data.get("channel", {}).get("name", "Unknown Channel")
        # For song/artist split: simplistic - assume title is "Song - Artist" or use channel as artist
        if " - " in title:
            song_name, artist = title.split(" - ", 1)
        else:
            song_name = title
            artist = channel
    except Exception:
        song_name, artist, thumbnail, duration, channel = "Unsupported Title", "Unknown Artist", YOUTUBE_IMG_URL, None, "Unknown Channel"

    is_live = not duration or str(duration).strip().lower() in {"", "live", "live now"}
    duration_text = "Live" if is_live else duration or "Unknown Mins"

    # Download thumbnail
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
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(YOUTUBE_IMG_URL) as resp:
                    if resp.status == 200:
                        async with aiofiles.open(thumb_path, "wb") as f:
                            await f.write(await resp.read())
        except Exception:
            pass

    # Base image - dark background
    try:
        base = Image.open(thumb_path).resize((1280, 720)).convert("RGBA")
    except Exception:
        base = Image.new("RGBA", (1280, 720), (20, 20, 30, 255))  # Dark fallback
    # Darken and blur for background
    bg = ImageEnhance.Brightness(base.filter(ImageFilter.BoxBlur(10))).enhance(0.3)

    # Frosted panel
    panel_area = bg.crop((PANEL_X, PANEL_Y, PANEL_X + PANEL_W, PANEL_Y + PANEL_H))
    overlay = Image.new("RGBA", (PANEL_W, PANEL_H), (255, 255, 255, TRANSPARENCY))
    frosted = Image.alpha_composite(panel_area, overlay)
    mask = Image.new("L", (PANEL_W, PANEL_H), 0)
    mask_draw = ImageDraw.Draw(mask)
    draw_rounded_rectangle(mask_draw, (0, 0, PANEL_W, PANEL_H), PANEL_RADIUS, fill=255)
    frosted.putalpha(mask)
    bg.paste(frosted, (PANEL_X, PANEL_Y), frosted)

    # Fonts
    draw = ImageDraw.Draw(bg)
    try:
        title_font = ImageFont.truetype("VIVAANXMUSIC/assets/thumb/font2.ttf", 36)  # Large for overlay
        artist_font = ImageFont.truetype("VIVAANXMUSIC/assets/thumb/font2.ttf", 24)  # Medium for artist
        regular_font = ImageFont.truetype("VIVAANXMUSIC/assets/thumb/font.ttf", 16)
        channel_font = ImageFont.truetype("VIVAANXMUSIC/assets/thumb/font.ttf", 14)
        icon_font = ImageFont.truetype("VIVAANXMUSIC/assets/thumb/font.ttf", ICON_FONT_SIZE)
    except OSError:
        title_font = artist_font = regular_font = channel_font = icon_font = ImageFont.load_default()

    # Prepare thumbnail with red tint and overlays
    thumb = base.resize((THUMB_W, THUMB_H))
    # Apply red tint overlay
    tint_overlay = Image.new("RGBA", thumb.size, RED_TINT)
    thumb = Image.alpha_composite(thumb, tint_overlay)
    # Rounded mask for thumb
    tmask = Image.new("L", thumb.size, 255)
    tdraw = ImageDraw.Draw(tmask)
    draw_rounded_rectangle(tdraw, (0, 0, THUMB_W, THUMB_H), THUMB_RADIUS, fill=255)
    thumb.putalpha(tmask)

    # Overlay song title and artist on thumb (white, large)
    thumb_draw = ImageDraw.Draw(thumb)
    # Center title
    title_w = title_font.getlength(song_name) if hasattr(title_font, 'getlength') else title_font.getbbox(song_name)[2]
    thumb_draw.text(((THUMB_W - title_w) / 2, TITLE_OVERLAY_Y - THUMB_Y), song_name, fill="white", font=title_font)
    # Center artist below
    artist_w = artist_font.getlength(artist) if hasattr(artist_font, 'getlength') else artist_font.getbbox(artist)[2]
    thumb_draw.text(((THUMB_W - artist_w) / 2, ARTIST_OVERLAY_Y - THUMB_Y), artist, fill="white", font=artist_font)

    # Paste thumb to bg
    bg.paste(thumb, (THUMB_X, THUMB_Y), thumb)

    # Panel texts
    # Channel at top right
    channel_trim = trim_to_width(channel, channel_font, PANEL_W - 40)
    channel_x = PANEL_X + PANEL_W - (channel_font.getlength(channel_trim) if hasattr(channel_font, 'getlength') else channel_font.getbbox(channel_trim)[2]) - 10
    draw.text((channel_x, CHANNEL_Y), channel_trim, fill="#888888", font=channel_font)

    # Artist in panel (repeat for prominence, with dots)
    artist_panel = f"{artist} ---"
    artist_trim = trim_to_width(artist_panel, regular_font, PANEL_W - 2 * INNER_OFFSET)
    draw.text((PANEL_X + INNER_OFFSET, THUMB_Y + THUMB_H + 10), artist_trim, fill="black", font=regular_font)

    # Song in panel? Example shows song on thumb, but perhaps small below
    # Skip or add if needed; example has song on thumb primarily

    # Vertical icons left
    draw.text((ICON_X, HEART_Y), "♥", fill="white", font=icon_font)  # White for visibility on dark
    draw.text((ICON_X, ADD_Y), "+", fill="white", font=icon_font)
    draw.text((ICON_X, UP_Y), "↗", fill="white", font=icon_font)

    # Progress bar
    bar_y_center = PLAY_Y
    draw.line([(BAR_X, bar_y_center), (BAR_X + BAR_TOTAL_LEN, bar_y_center)], fill="#E5E5E5", width=BAR_HEIGHT)
    draw.line([(BAR_X, bar_y_center), (BAR_X + BAR_RED_LEN, bar_y_center)], fill="#FF0000", width=BAR_HEIGHT)
    # Dot
    dot_x = BAR_X + BAR_RED_LEN
    draw.ellipse([(dot_x - DOT_RADIUS, bar_y_center - DOT_RADIUS), (dot_x + DOT_RADIUS, bar_y_center + DOT_RADIUS)], fill="#FF0000")

    # Play button (simple red triangle for play; example shows pause, but default play)
    tri_size = 7
    tri_points = [
        (PLAY_X - tri_size, PLAY_Y - tri_size // 2),
        (PLAY_X + tri_size, PLAY_Y),
        (PLAY_X - tri_size, PLAY_Y + tri_size // 2)
    ]
    draw.polygon(tri_points, fill="#FF0000")

    # Times
    def get_text_width(t, f):
        if hasattr(f, 'getlength'):
            return f.getlength(t)
        bbox = f.getbbox(t)
        return bbox[2] - bbox[0]

    draw.text((BAR_X + 5, BAR_Y + TIME_OFFSET_Y), "00:00", fill="black", font=regular_font)
    end_w = get_text_width(duration_text, regular_font)
    end_x = BAR_X + BAR_TOTAL_LEN - end_w - 5
    end_color = "#FF0000" if is_live else "black"
    draw.text((end_x, BAR_Y + TIME_OFFSET_Y), duration_text, fill=end_color, font=regular_font)

    # Cleanup
    try:
        os.remove(thumb_path)
    except OSError:
        pass

    bg.convert("RGB").save(cache_path, "PNG", quality=95)
    return cache_path
