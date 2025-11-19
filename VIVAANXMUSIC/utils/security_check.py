"""
Security Check Utilities - BioAnalyser Integration
Bio link detection using USERBOT (only way to read bios in Telegram API)
"""

import re
from typing import Tuple, Optional
from pyrogram import Client
from pyrogram.types import User, Message


# ==================== COMPREHENSIVE LINK DETECTION PATTERN ====================

URL_PATTERN = re.compile(
    r'(?i)(?:'
        r'@[a-zA-Z0-9_][a-zA-Z0-9_]{3,31}|'
        r't\.me/[a-zA-Z0-9_./\-]+|'
        r'telegram\.me/[a-zA-Z0-9_./\-]+|'
        r'tg\.me/[a-zA-Z0-9_./\-]+|'
        r'https?://[^\s]+|'
        r'www\.[a-zA-Z0-9.\-]+(?:[/?#][^\s]*)?|'
        r'(?:bit\.ly|ow\.ly|tinyurl\.com|short\.link|goo\.gl|is\.gd)/[a-zA-Z0-9.\-_]+|'
        r'(?:instagram|tiktok|twitter|facebook|youtube|linkedin|snapchat|discord|twitch|reddit)\.com/[a-zA-Z0-9.\-_~:/?#@!$&\'()*+,;=%]+|'
        r'(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+(?:com|org|net|io|co|uk|app|dev|shop|xyz|info|biz|online|site|store|club|live|pro|world|life|today|fun|space|website|email|link|click|digital|download|cloud|host)(?:[/?#][^\s]*)?'
    r')'
)


# ==================== LINK DETECTION ====================

def has_link(text: str) -> bool:
    """Check if text contains links"""
    if not text:
        return False
    return URL_PATTERN.search(text) is not None


def extract_links(text: str) -> list:
    """Extract all links from text"""
    if not text:
        return []
    links = URL_PATTERN.findall(text)
    return list(set(links))


# ==================== BIO CHECKING WITH USERBOT ====================

async def check_bio(client: Client, user_id: int) -> Tuple[bool, str]:
    """
    Check if user's bio contains links
    Uses USERBOT - bot clients cannot read user bios
    """
    try:
        # Import global userbot instance
        from VIVAANXMUSIC import userbot
        from VIVAANXMUSIC.core.userbot import assistants
        
        # Check if userbot is available
        if not assistants:
            print(f"[Security] No userbot assistants available")
            return False, ""
        
        # Use first available assistant
        userclient = None
        if 1 in assistants:
            userclient = userbot.one
        elif 2 in assistants:
            userclient = userbot.two
        elif 3 in assistants:
            userclient = userbot.three
        elif 4 in assistants:
            userclient = userbot.four
        elif 5 in assistants:
            userclient = userbot.five
        
        if not userclient:
            print(f"[Security] No userbot client found")
            return False, ""
        
        # Get user with userbot (ONLY way to read bios)
        user = await userclient.get_users(user_id)
        bio = user.bio or ""
        
        if not bio:
            return False, ""
        
        contains_link = has_link(bio)
        
        if contains_link:
            print(f"[Security] ✅ Link found in {user.first_name}'s bio: {bio}")
            print(f"[Security] Links: {extract_links(bio)}")
        
        return contains_link, bio
        
    except Exception as e:
        print(f"[Security] Error checking bio for {user_id}: {e}")
        return False, ""


async def check_bio_detailed(client: Client, user_id: int) -> dict:
    """Detailed bio check"""
    try:
        from VIVAANXMUSIC import userbot
        from VIVAANXMUSIC.core.userbot import assistants
        
        if not assistants:
            return {
                "has_link": False,
                "bio": "Userbot unavailable",
                "links": [],
                "link_count": 0,
                "username": None,
                "user_id": user_id,
                "first_name": "Unknown",
                "is_bot": False
            }
        
        # Get userbot client
        userclient = None
        if 1 in assistants:
            userclient = userbot.one
        elif 2 in assistants:
            userclient = userbot.two
        elif 3 in assistants:
            userclient = userbot.three
        elif 4 in assistants:
            userclient = userbot.four
        elif 5 in assistants:
            userclient = userbot.five
        
        if not userclient:
            return {
                "has_link": False,
                "bio": "Userbot client not found",
                "links": [],
                "link_count": 0,
                "username": None,
                "user_id": user_id,
                "first_name": "Unknown",
                "is_bot": False
            }
        
        user = await userclient.get_users(user_id)
        bio = user.bio or ""
        links_found = extract_links(bio)
        
        print(f"[Security] Detailed scan: {user.first_name} | Bio: '{bio}' | Links: {links_found}")
        
        return {
            "has_link": len(links_found) > 0,
            "bio": bio if bio else "No bio",
            "links": links_found,
            "link_count": len(links_found),
            "username": user.username,
            "user_id": user.id,
            "first_name": user.first_name,
            "is_bot": user.is_bot
        }
        
    except Exception as e:
        print(f"[Security] Detailed check error: {e}")
        return {
            "has_link": False,
            "bio": f"Error: {str(e)[:50]}",
            "links": [],
            "link_count": 0,
            "username": None,
            "user_id": user_id,
            "first_name": "Unknown",
            "is_bot": False
        }


# ==================== USER EXTRACTION ====================

async def get_target_user(message: Message) -> Optional[User]:
    """Extract target user from message"""
    if message.reply_to_message:
        return message.reply_to_message.from_user
    
    if len(message.command) < 2:
        return None
    
    user_input = message.command[1]
    
    try:
        if user_input.isdigit():
            return await message._client.get_users(int(user_input))
        return await message._client.get_users(user_input)
    except Exception as e:
        print(f"[Security] Error getting user: {e}")
        return None


async def get_user_info(client: Client, user_id: int) -> Optional[dict]:
    """Get basic user information"""
    try:
        user: User = await client.get_users(user_id)
        return {
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
            "mention": user.mention,
            "is_bot": user.is_bot,
            "bio": user.bio
        }
    except Exception as e:
        print(f"[Security] Error: {e}")
        return None


# ==================== TEXT VALIDATION ====================

def clean_bio_preview(bio: str, max_length: int = 100) -> str:
    """Clean and truncate bio"""
    if not bio or bio == "No bio":
        return "No bio"
    bio = " ".join(bio.split())
    if len(bio) > max_length:
        return bio[:max_length] + "..."
    return bio


def format_links_list(links: list, max_display: int = 5) -> str:
    """Format links for display"""
    if not links:
        return "No links found"
    
    displayed = links[:max_display]
    result = "\n".join([f"├ `{link}`" for link in displayed])
    
    if len(links) > max_display:
        result += f"\n└ ... and {len(links) - max_display} more"
    
    return result
