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
    """Get the first available and STARTED userbot client"""
    try:
        import config
        
        # Get the userbot instance
        userbot = get_userbot_instance()
        
        # Try to use the first available client that has a session string
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
        bio = ""
        
        if userbot:
            try:
                print(f"[Security] Attempting to get user {user_id} with userbot...")
                user = await userbot.get_users(user_id)
                bio = user.bio or ""
                
                print(f"[Security] ✅ Successfully got bio using userbot for user {user_id}")
                print(f"[Security] User: {user.first_name} (@{user.username})")
                print(f"[Security] Bio raw: '{bio}'")
                print(f"[Security] Bio length: {len(bio)}")
                
            except Exception as e:
                print(f"[Security] ❌ Userbot failed: {e}")
                print(f"[Security] Falling back to bot client...")
                try:
                    user = await client.get_users(user_id)
                    bio = user.bio or ""
                    print(f"[Security] Bot client bio: '{bio}'")
                except Exception as e2:
                    print(f"[Security] ❌ Bot client also failed: {e2}")
                    return False, ""
        else:
            # No userbot, use bot client (won't work for bot accounts)
            print(f"[Security] No userbot available, using bot client")
            try:
                user = await client.get_users(user_id)
                bio = user.bio or ""
            except Exception as e:
                print(f"[Security] Bot client failed: {e}")
                return False, ""
        
        contains_link = has_link(bio)
        
        # Debug logging
        if bio:
            print(f"[Security] Bio content: '{bio}'")
            print(f"[Security] Link detected: {contains_link}")
            if contains_link:
                links = extract_links(bio)
                print(f"[Security] Links found: {links}")
        else:
            print(f"[Security] User {user_id} has no bio (empty)")
        
        return contains_link, bio
        
    except Exception as e:
        print(f"[Security] CRITICAL Error checking bio for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        return False, ""


async def check_bio_detailed(client: Client, user_id: int) -> dict:
    """Check user bio with detailed information using userbot"""
    print(f"\n{'='*60}")
    print(f"[Security DEBUG] Starting detailed bio check for user {user_id}")
    
    try:
        userbot = await get_userbot_client()
        print(f"[Security DEBUG] Userbot client: {userbot}")
        print(f"[Security DEBUG] Userbot type: {type(userbot)}")
        
        user = None
        bio = ""
        
        if userbot:
            try:
                print(f"[Security DEBUG] Attempting userbot.get_users({user_id})...")
                user = await userbot.get_users(user_id)
                
                print(f"[Security DEBUG] ✅ User retrieved successfully")
                print(f"[Security DEBUG] User ID: {user.id}")
                print(f"[Security DEBUG] First name: {user.first_name}")
                print(f"[Security DEBUG] Username: @{user.username}")
                print(f"[Security DEBUG] Is bot: {user.is_bot}")
                print(f"[Security DEBUG] Bio (raw): '{user.bio}'")
                print(f"[Security DEBUG] Bio type: {type(user.bio)}")
                print(f"[Security DEBUG] Bio is None: {user.bio is None}")
                
                bio = user.bio or ""
                print(f"[Security DEBUG] Bio after processing: '{bio}'")
                print(f"[Security DEBUG] Bio length: {len(bio)}")
                
            except Exception as e:
                print(f"[Security DEBUG] ❌ Userbot failed: {e}")
                import traceback
                traceback.print_exc()
                
                print(f"[Security DEBUG] Trying bot client...")
                user = await client.get_users(user_id)
                bio = user.bio or ""
                print(f"[Security DEBUG] Bot client bio: '{bio}'")
        else:
            print(f"[Security DEBUG] ❌ No userbot available!")
            user = await client.get_users(user_id)
            bio = user.bio or ""
            print(f"[Security DEBUG] Bot client bio: '{bio}'")
        
        links_found = extract_links(bio)
        print(f"[Security DEBUG] Links extracted: {links_found}")
        print(f"[Security DEBUG] Has link: {len(links_found) > 0}")
        print(f"{'='*60}\n")
        
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
        print(f"[Security DEBUG] ❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        print(f"{'='*60}\n")
        
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
