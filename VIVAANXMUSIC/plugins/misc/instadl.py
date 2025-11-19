"""
Instagram/Reels Downloader
Download Instagram videos and photos using Social Media Downloader API
Part of VivaanXMusic Bot
"""

import os
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
        async with httpx.AsyncClient(timeout=30.0, headers=HEADERS, follow_redirects=True) as client_http:
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

        # Update status
        await processing_msg.edit(f"📥 **Downloading {len(urls)} media file(s)...**")
        
        # Download and send media files
        for idx, media_url in enumerate(urls):
            try:
                # Update progress
                await processing_msg.edit(f"📥 **Downloading media {idx + 1}/{len(urls)}...**")
                
                # Download media to temporary file
                async with httpx.AsyncClient(timeout=60.0, headers=HEADERS, follow_redirects=True) as client_http:
                    media_response = await client_http.get(media_url)
                    media_response.raise_for_status()
                    
                    # Determine file extension
                    if media_url.endswith(".mp4") or "video" in media_url.lower():
                        file_ext = ".mp4"
                        media_type = "video"
                    elif any(media_url.lower().endswith(ext) for ext in [".jpg", ".jpeg"]):
                        file_ext = ".jpg"
                        media_type = "photo"
                    elif media_url.lower().endswith(".png"):
                        file_ext = ".png"
                        media_type = "photo"
                    elif media_url.lower().endswith(".webp"):
                        file_ext = ".webp"
                        media_type = "photo"
                    else:
                        # Default to mp4 if unknown
                        file_ext = ".mp4"
                        media_type = "video"
                    
                    # Create temp file
                    temp_file = f"downloads/insta_{message.from_user.id}_{idx}{file_ext}"
                    os.makedirs("downloads", exist_ok=True)
                    
                    # Save downloaded content
                    with open(temp_file, "wb") as f:
                        f.write(media_response.content)
                
                # Update progress
                await processing_msg.edit(f"📤 **Uploading media {idx + 1}/{len(urls)}...**")
                
                # Prepare caption
                caption = f"📱 **Instagram Media** ({idx + 1}/{len(urls)})"
                
                # Send based on media type
                if media_type == "video":
                    await message.reply_video(
                        video=temp_file,
                        caption=caption,
                        supports_streaming=True
                    )
                else:
                    await message.reply_photo(
                        photo=temp_file,
                        caption=caption
                    )
                
                # Delete temp file
                try:
                    os.remove(temp_file)
                except:
                    pass
                    
            except httpx.TimeoutException:
                await message.reply_text(f"❌ Timeout downloading media {idx + 1}/{len(urls)}")
                continue
            
            except Exception as media_error:
                await message.reply_text(
                    f"❌ Error with media {idx + 1}/{len(urls)}: {str(media_error)[:100]}"
                )
                continue

        # Delete processing message
        try:
            await processing_msg.delete()
        except:
            pass

    except httpx.TimeoutException:
        await processing_msg.edit("❌ **Timeout Error!** The API took too long to respond. Try again later.")
    
    except httpx.HTTPStatusError as e:
        await processing_msg.edit(f"❌ **HTTP Error {e.response.status_code}!** The API returned an error.")
    
    except ValueError as e:
        await processing_msg.edit(f"❌ **JSON Parse Error!** Invalid response from API.")
    
    except MessageNotModified:
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
