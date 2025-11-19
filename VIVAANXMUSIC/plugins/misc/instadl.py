"""
Instagram/Reels Downloader
Download Instagram videos and photos using Social Media Downloader API
Part of VivaanXMusic Bot
"""

import httpx
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import MessageNotModified
from VIVAANXMUSIC import app

# API Configuration
API_BASE_URL = "https://socialdown.itz-ashlynn.workers.dev"
API_INSTA = f"{API_BASE_URL}/insta"

# Headers for API
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json"
}


@app.on_message(filters.command(["ig", "insta", "instagram", "reels"]))
async def insta_download(client: Client, message: Message):
    """Download Instagram videos and photos"""
    
    # Check if URL provided
    if len(message.command) < 2:
        return await message.reply_text(
            "❌ **Usage Error**\n\n"
            "`/insta [Instagram URL]`\n\n"
            "**Examples:**\n"
            "• `/insta https://www.instagram.com/p/ABC123/`\n"
            "• `/insta https://www.instagram.com/reel/ABC123/`\n"
            "• `/insta https://instagram.com/p/ABC123/`"
        )

    # Send processing message
    processing_msg = await message.reply_text("🔄 **Processing your Instagram link...**")

    try:
        instagram_url = message.command[1]
        
        # Validate URL
        if "instagram.com" not in instagram_url:
            return await processing_msg.edit("❌ **Invalid URL!** Please provide a valid Instagram link.")

        # Call API with GET method
        async with httpx.AsyncClient(timeout=20.0, headers=HEADERS) as client_http:
            response = await client_http.get(API_INSTA, params={"url": instagram_url})
            response.raise_for_status()
            data = response.json()

        # Check if successful
        if not data.get("success"):
            error_msg = data.get("error", "Unknown error occurred")
            return await processing_msg.edit(f"❌ **API Error:** {error_msg}")

        # Get URLs from response
        urls = data.get("urls", [])
        
        if not urls:
            return await processing_msg.edit("⚠️ **No media found!** The link may be invalid or the video may be unavailable.")

        # Send media files
        await processing_msg.edit("📤 **Uploading media...**")
        
        for idx, media_url in enumerate(urls):
            try:
                # Prepare caption without markdown parse mode issues
                caption = f"📱 Instagram Media ({idx + 1}/{len(urls)})"
                
                # Determine media type from URL
                if media_url.endswith(".mp4") or "video" in media_url.lower():
                    # Send as video
                    await message.reply_video(
                        video=media_url,
                        caption=caption
                    )
                elif any(media_url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                    # Send as photo
                    await message.reply_photo(
                        photo=media_url,
                        caption=caption
                    )
                else:
                    # Unknown format - send as document
                    await message.reply_document(
                        document=media_url,
                        caption=caption
                    )
                    
            except Exception as media_error:
                await message.reply_text(
                    f"❌ Error uploading media {idx + 1}/{len(urls)}: {str(media_error)[:100]}"
                )
                continue

        # Delete processing message
        await processing_msg.delete()

    except httpx.TimeoutException:
        await processing_msg.edit("❌ **Timeout Error!** The API took too long to respond. Try again later.")
    
    except httpx.HTTPStatusError as e:
        await processing_msg.edit(f"❌ **HTTP Error {e.response.status_code}!** The API returned an error.")
    
    except ValueError as e:
        await processing_msg.edit(f"❌ **JSON Parse Error!** Invalid response from API.")
    
    except MessageNotModified:
        # Message was already deleted
        pass
    
    except Exception as e:
        error_msg = str(e)[:200]
        try:
            await processing_msg.edit(f"❌ **Unexpected Error:** {error_msg}")
        except:
            await message.reply_text(f"❌ **Error:** {error_msg}")


@app.on_message(filters.command(["ighelp", "instahelp"]))
async def insta_help(client: Client, message: Message):
    """Show Instagram downloader help"""
    help_text = """
🎬 **Instagram Downloader Help**

**Commands:**
• `/insta [URL]` - Download Instagram video/photo
• `/ig [URL]` - Short alias for /insta
• `/instagram [URL]` - Alternative command
• `/reels [URL]` - Download Instagram Reels

**Supported Links:**
✅ Posts: `https://www.instagram.com/p/ABC123/`
✅ Reels: `https://www.instagram.com/reel/ABC123/`
✅ Stories: `https://www.instagram.com/stories/username/ABC123/`
✅ Short URLs: `https://instagram.com/p/ABC123/`

**Example Usage:**
`/insta https://www.instagram.com/p/ABC123/`

**Features:**
• Automatic video/photo detection
• Support for multi-media posts
• Direct Telegram upload
• Fast processing

**Note:**
⚠️ This bot respects Instagram ToS
⚠️ Only download content you have permission to download
⚠️ Don't use for commercial purposes without permission

Need help? Contact support.
"""
    await message.reply_text(help_text)
