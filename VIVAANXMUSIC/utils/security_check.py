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


# ==================== USERBOT ACCESS ====================

_userbot_instance = None

def get_userbot_instance():
    """Get or create the Userbot instance"""
    global _userbot_instance
    if _userbot_instance is None:
        from VIVAANXMUSIC.core.userbot import Userbot
        _userbot_instance = Userbot()
    return _userbot_instance


async def get_userbot_client():
    """Get the first available userbot client"""
    try:
        import config
        
        # Get the userbot instance
        userbot = get_userbot_instance()
        
        # Try to use the first available client
        if config.STRING1:
            print(f"[Security] Using userbot client 'one'")
            return userbot.one
        elif config.STRING2:
            print(f"[Security] Using userbot client 'two'")
            return userbot.two
        elif config.STRING3:
            print(f"[Security] Using userbot client 'three'")
            return userbot.three
        elif config.STRING4:
            print(f"[Security] Using userbot client 'four'")
            return userbot.four
        elif config.STRING5:
            print(f"[Security] Using userbot client 'five'")
            return userbot.five
        else:
            print(f"[Security] WARNING: No userbot session strings configured!")
            return None
            
    except Exception as e:
        print(f"[Security] Error getting userbot client: {e}")
        import traceback
        traceback.print_exc()
        return None


# ==================== BIO CHECKING ====================

async def check_bio(client: Client, user_id: int) -> Tuple[bool, str]:
    """
    Check if user's bio contains links
    Uses USERBOT client to access full bio data
    """
    try:
        # Get userbot client
        userbot = await get_userbot_client()
        
        user = None
        
        if userbot:
            try:
                user = await userbot.get_users(user_id)
                print(f"[Security] ✅ Successfully got bio using userbot for user {user_id}")
            except Exception as e:
                print(f"[Security] Userbot failed: {e}, trying bot client")
                user = await client.get_users(user_id)
        else:
            # No userbot, use bot client (won't work for bot accounts)
            print(f"[Security] No userbot available, using bot client")
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
            print(f"[Security] User {user_id} ({user.first_name}) has no bio")
        
        return contains_link, bio
        
    except Exception as e:
        print(f"[Security] Error checking bio for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        return False, ""


async def check_bio_detailed(client: Client, user_id: int) -> dict:
    """Check user bio with detailed information using userbot"""
    try:
        userbot = await get_userbot_client()
        
        user = None
        
        if userbot:
            try:
                user = await userbot.get_users(user_id)
                print(f"[Security] ✅ Detailed scan using userbot for user {user_id}")
            except Exception as e:
                print(f"[Security] Userbot failed in detailed check: {e}")
                user = await client.get_users(user_id)
        else:
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
        import traceback
        traceback.print_exc()
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
