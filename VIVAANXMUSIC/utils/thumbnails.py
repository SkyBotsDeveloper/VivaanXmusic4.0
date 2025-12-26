import os
import re
import textwrap
import numpy as np
import aiofiles
import aiohttp
from PIL import (
    Image,
    ImageDraw,
    ImageEnhance,
    ImageFilter,
    ImageFont,
)
from youtubesearchpython.__future__ import VideosSearch
from config import YOUTUBE_IMG_URL
 
 
def changeImageSize(maxWidth, maxHeight, image):
    widthRatio = maxWidth / image.size[0]
    heightRatio = maxHeight / image.size[1]
    ratio = min(widthRatio, heightRatio)
    newWidth = int(image.size[0] * ratio)
    newHeight = int(image.size[1] * ratio)
    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:
        resample = Image.ANTIALIAS
    return image.resize((newWidth, newHeight), resample)
 
 
def get_dominant_color(image):
    image = image.convert('RGB').resize((50, 50))
    pixels = np.array(image).reshape(-1, 3)
    avg_color = tuple(pixels.mean(axis=0).astype(int))
    if sum(avg_color) < 200:
        return tuple(min(255, int(c * 1.5)) for c in avg_color)
    return avg_color
 
 
def get_contrasting_color(bg_color):
    luminance = (0.299 * bg_color[0] + 0.587 * bg_color[1] + 0.114 * bg_color[2])
    return (255, 255, 255) if luminance < 128 else (50, 50, 50)
 
 
async def get_thumb(videoid):
    final_path = f"cache/{videoid}.png"
    if os.path.isfile(final_path):
        return final_path
 
    url = f"https://www.youtube.com/watch?v={videoid}"
    try:
        results = VideosSearch(url, limit=1)
        result_data = await results.next()
        if not result_data.get("result"):
            return YOUTUBE_IMG_URL
 
        result = result_data["result"][0]
        title = re.sub(r"\W+", " ", result.get("title", "Unknown Title")).title()
        duration = result.get("duration", "00:00")
        thumbnail_url = result["thumbnails"][0]["url"].split("?")[0]
        views = result.get("viewCount", {}).get("short", "0 views")
        channel = result.get("channel", {}).get("name", "Unknown Channel")
 
        os.makedirs("cache", exist_ok=True)
        thumb_path = f"cache/thumb{videoid}.png"
 
        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail_url) as resp:
                async with aiofiles.open(thumb_path, "wb") as f:
                    await f.write(await resp.read())
 
        try:
            youtube = Image.open(thumb_path)
        except:
            os.remove(thumb_path) if os.path.exists(thumb_path) else None
            return YOUTUBE_IMG_URL
 
        full_bg = changeImageSize(1280, 720, youtube.copy()).convert("RGBA")
        blurred_bg = full_bg.filter(ImageFilter.GaussianBlur(48))
        bar_color = get_dominant_color(blurred_bg)
        accent = tuple(min(255, int(c * 1.25) + 20) for c in bar_color)
        contrast_color = get_contrasting_color(bar_color)
 
        enhancer_b = ImageEnhance.Brightness(blurred_bg).enhance(0.6)
        enhancer_c = ImageEnhance.Color(enhancer_b).enhance(0.95)
        bg = enhancer_c
 
        color_overlay = Image.new("RGBA", bg.size, (accent[0], accent[1], accent[2], 140))
        bg = Image.alpha_composite(bg, color_overlay)
 
        subtle_frost = Image.new("RGBA", bg.size, (255, 255, 255, 12))
        bg = Image.alpha_composite(bg, subtle_frost)
 
        glass_layer = Image.new("RGBA", bg.size, (0, 0, 0, 0))
        glass_size = (int(bg.width * 0.78), int(bg.height * 0.62))
        glass = Image.new("RGBA", glass_size, (accent[0], accent[1], accent[2], 28))
        glass = glass.filter(ImageFilter.GaussianBlur(34))
        glass_pos = ((bg.width - glass.width) // 2, (bg.height - glass.height) // 2 - 10)
        glass_layer.paste(glass, glass_pos, glass)
        bg = Image.alpha_composite(bg, glass_layer)
 
        depth_tint = Image.new("RGBA", bg.size, (0, 0, 0, 28))
        bg = Image.alpha_composite(bg, depth_tint)
 
        center_thumb = changeImageSize(940, 420, youtube.copy()).convert("RGBA")
        thumb_pos = ((bg.width - center_thumb.width) // 2, 90)
 
        enhancer_brightness = ImageEnhance.Brightness(center_thumb).enhance(1.05)
        enhancer_contrast = ImageEnhance.Contrast(enhancer_brightness).enhance(1.18)
        center_thumb = enhancer_contrast
 
        glow_layer = Image.new("RGBA", bg.size, (0, 0, 0, 0))
        glow_size = (center_thumb.width + 140, center_thumb.height + 140)
        glow = Image.new("RGBA", glow_size, (bar_color[0], bar_color[1], bar_color[2], 80))
        glow = glow.filter(ImageFilter.GaussianBlur(54))
        glow_pos = (thumb_pos[0] - 70, thumb_pos[1] - 70)
        glow_layer.paste(glow, glow_pos, glow)
        bg = Image.alpha_composite(bg, glow_layer)
 
        mask = Image.new("L", center_thumb.size, 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.rounded_rectangle([0, 0, center_thumb.width, center_thumb.height], radius=40, fill=255)
        bg.paste(center_thumb, thumb_pos, mask)
 
        thirty = 30
        panel_box = (
            thumb_pos[0] - thirty,
            thumb_pos[1] - thirty,
            thumb_pos[0] + center_thumb.width + thirty,
            thumb_pos[1] + center_thumb.height + thirty,
        )
        left, top, right, bottom = panel_box
        left = max(0, left)
        top = max(0, top)
        right = min(bg.width, right)
        bottom = min(bg.height, bottom)
 
        cropped = bg.crop((left, top, right, bottom)).convert("RGBA")
        blurred_panel = cropped.filter(ImageFilter.GaussianBlur(22))
        white_overlay = Image.new("RGBA", blurred_panel.size, (255, 255, 255, 50))
        blended_panel = Image.alpha_composite(blurred_panel, white_overlay)
 
        panel_mask = Image.new("L", blended_panel.size, 0)
        pm_draw = ImageDraw.Draw(panel_mask)
        pm_draw.rounded_rectangle([0, 0, blended_panel.width, blended_panel.height], radius=40, fill=255)
 
        panel_canvas = Image.new("RGBA", bg.size, (0, 0, 0, 0))
        panel_canvas.paste(blended_panel, (left, top), panel_mask)
 
        border_draw = ImageDraw.Draw(panel_canvas)
        border_draw.rounded_rectangle([left, top, right, bottom], radius=40, outline=(255, 255, 255, 70), width=2)
 
        bg = Image.alpha_composite(bg, panel_canvas)
 
        mask = Image.new("L", center_thumb.size, 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.rounded_rectangle([0, 0, center_thumb.width, center_thumb.height], radius=40, fill=255)
        bg.paste(center_thumb, thumb_pos, mask)
 
        def safe_font(path, size):
            try:
                return ImageFont.truetype(path, size)
            except:
                return ImageFont.load_default()
 
        font_title = safe_font("VIVAANXMUSIC/assets/thumb/font2.ttf", 32)
        font_small = safe_font("VIVAANXMUSIC/assets/thumb/font.ttf", 28)
        font_brand = safe_font("VIVAANXMUSIC/assets/thumb/font.ttf", 40)
 
        draw = ImageDraw.Draw(bg)
 
        bar_width = 15
        bar_height = center_thumb.height
        bar_radius = 12
        bar_y = thumb_pos[1]
 
        duration_pos = (thumb_pos[0] - 160, bar_y - 40)
        draw.text(duration_pos, duration[:23], fill="white", font=font_small)
        dur_bbox = draw.textbbox(duration_pos, duration[:23], font=font_small)
        dur_center_x = (dur_bbox[0] + dur_bbox[2]) // 2
        bar_x = dur_center_x - (bar_width // 2)
 
        draw.rounded_rectangle(
            [bar_x, bar_y, bar_x + bar_width, bar_y + bar_height],
            radius=bar_radius,
            fill=(80, 80, 80, 150)
        )
 
        played_ratio = 0.25
        fill_height = int(bar_height * played_ratio)
        draw.rounded_rectangle(
            [bar_x, bar_y + bar_height - fill_height, bar_x + bar_width, bar_y + bar_height],
            radius=bar_radius,
            fill=(bar_color[0], bar_color[1], bar_color[2], 255)
        )
 
        draw.text((bar_x - 50, bar_y + bar_height + 10), "00:25", fill="white", font=font_small)
 
        text_left = thumb_pos[0]
        text_top = thumb_pos[1] + center_thumb.height + 33
        title_short = textwrap.shorten(title, width=50, placeholder="...")
        draw.text((text_left, text_top), title_short, fill="white", font=font_title, stroke_width=1, stroke_fill="black")
        draw.text((text_left, text_top + 44), f"{channel} | {views[:23]}", fill="white", font=font_small, stroke_width=1, stroke_fill="black")
 
        rec_text = "Elite"
        rec_bbox = draw.textbbox((0, 0), rec_text, font=font_brand)
        rec_w = rec_bbox[2] - rec_bbox[0]
        rec_h = rec_bbox[3] - rec_bbox[1]
        rec_x = thumb_pos[0] + center_thumb.width + 35
        rec_y = thumb_pos[1] + (center_thumb.height // 2) - (rec_h // 2)
        draw.text((rec_x, rec_y), rec_text, fill="white", font=font_brand)
 
        try:
            os.remove(thumb_path)
        except:
            pass
 
        bg.save(final_path, format="PNG")
        return final_path
 
    except Exception as e:
        print("Thumb error:", e)
        return YOUTUBE_IMG_URL
