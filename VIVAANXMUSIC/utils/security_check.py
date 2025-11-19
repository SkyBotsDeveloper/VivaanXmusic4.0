"""
Security Check Utilities
Bio link detection and user verification for group security
Uses USERBOT client for bio access (bots can't read bios)
Part of VivaanXMusic Group Management System
"""

import re
from typing import Tuple, Optional
from pyrogram import Client
from pyrogram.types import User, Message


# ==================== COMPREHENSIVE LINK DETECTION PATTERN ====================

# Enhanced URL pattern from BioAnalyser
URL_PATTERN = re.compile(
    r'(?i)(?:'
        r'@[a-zA-Z0-9_][a-zA-Z0-9_]{3,31}|'  # @username mentions (4-32 chars)
        r't\.me/[a-zA-Z0-9_./\-]+|'  # t.me links
        r'telegram\.me/[a-zA-Z0-9_./\-]+|'  # telegram.me links
        r'tg\.me/[a-zA-Z0-9_./\-]+|'  # tg.me links
        r'https?://[^\s]+|'  # http:// or https:// URLs
        r'www\.[a-zA-Z0-9.\-]+(?:[/?#][^\s]*)?|'  # www.example.com
        r'(?:bit\.ly|ow\.ly|tinyurl\.com|short\.link|goo\.gl|is\.gd)/[a-zA-Z0-9.\-_]+|'  # URL shorteners
        r'(?:instagram|tiktok|twitter|facebook|youtube|linkedin|snapchat|discord|twitch|reddit)\.com/[a-zA-Z0-9.\-_~:/?#@!$&\'()*+,;=%]+|'  # Social media
        r'(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+(?:com|org|net|io|co|uk|app|dev|shop|xyz|info|biz|online|site|store|club|live|pro|world|life|today|fun|space|website|email|link|click|digital|download|cloud|host)(?:[/?#][^\s]*)?'  # Domain names
    r')'
)


# ==================== LINK DETECTION FUNCTIONS ====================

def has_link(text: str) -> bool:
    """Check if text contains any links or URLs"""
    if not text:
        return False
    return URL_PATTERN.search(text) is not None


def extract_links(text: str) -> list:
    """Extract all links from text"""
    if not text:
        return []
    links = URL_PATTERN.findall(text)
    return list(set(links))


# ==================== BIO CHECKING (USING USERBOT) ====================

async def check_bio(client: Client, user_id: int) -> Tuple[bool, str]:
    """
    Check if user's bio contains links
    Uses USERBOT client to access full bio data
    
    Args:
        client (Client): Pyrogram client (should be userbot)
        user_id (int): User ID to check
        
    Returns:
        Tuple[bool, str]: (has_link, bio_text)
    """
    try:
        # Import userbot client
        from VIVAANXMUSIC.core.userbot import Userbot
        
        # Use userbot to get full user data including bio
        # Userbot clients can access bios that bot clients can't
        userbot_clients = Userbot()
        
        # Try with first available userbot
        user = None
        for userbot in userbot_clients:
            try:
                user = await userbot.get_users(user_id)
                break
            except:
                continue
        
        if not user:
            # Fallback to bot client (won't work for bot accounts)
            user = await client.get_users(user_id)
        
        bio = user.bio or ""
        contains_link = has_link(bio)
        
        # Debug logging
        if bio:
            print(f"[Security] User {user_id} ({user.first_name}) bio: '{bio}'")
            print(f"[Security] Link detected: {contains_link}")
            if contains_link:
                links = extract_links(bio)
                print(f"[Security] Links found: {links}")
        else:
            print(f"[Security] User {user_id} has no bio")
        
        return contains_link, bio
        
    except Exception as e:
        print(f"[Security] Error checking bio for user {user_id}: {e}")
        return False, ""


async def check_bio_detailed(client: Client, user_id: int) -> dict:
    """Check user bio with detailed information using userbot"""
    try:
        # Import userbot client
        from VIVAANXMUSIC.core.userbot import Userbot
        
        userbot_clients = Userbot()
        
        user = None
        for userbot in userbot_clients:
            try:
                user = await userbot.get_users(user_id)
                break
            except:
                continue
        
        if not user:
            user = await client.get_users(user_id)
        
        bio = user.bio or ""
        links_found = extract_links(bio)
        
        return {
            "has_link": len(links_found) > 0,
            "bio": bio,
            "links": links_found,
            "link_count": len(links_found),
            "username": user.username,
            "user_id": user.id,
            "first_name": user.first_name
        }
    except Exception as e:
        print(f"[Security] Error in detailed bio check: {e}")
        return {
            "has_link": False,
            "bio": "",
            "links": [],
            "link_count": 0,
            "username": None,
            "user_id": user_id,
            "first_name": "Unknown"
        }


# ==================== USER EXTRACTION ====================

async def get_target_user(message: Message) -> Optional[User]:
    """Extract target user from message (reply/mention/ID)"""
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
        print(f"[Security] Error getting target user: {e}")
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
        print(f"[Security] Error getting user info: {e}")
        return None


# ==================== TEXT VALIDATION ====================

def clean_bio_preview(bio: str, max_length: int = 100) -> str:
    """Clean and truncate bio for preview"""
    if not bio:
        return "No bio"
    bio = " ".join(bio.split())
    if len(bio) > max_length:
        return bio[:max_length] + "..."
    return bio


def format_links_list(links: list, max_display: int = 5) -> str:
    """Format list of links for display"""
    if not links:
        return "No links found"
    
    displayed = links[:max_display]
    result = "\n".join([f"├ `{link}`" for link in displayed])
    
    if len(links) > max_display:
        result += f"\n└ ... and {len(links) - max_display} more"
    
    return result
