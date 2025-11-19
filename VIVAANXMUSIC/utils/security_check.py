"""
Security Check Utilities - BioAnalyser Integration
Bio link detection and user verification for group security
Uses ALREADY STARTED userbot client for bio access
"""

import re
import asyncio
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

async def get_userbot_client():
    """Get the ALREADY STARTED userbot client from global instance"""
    try:
        # Import the GLOBAL userbot instance that was started in __main__
        from VIVAANXMUSIC import userbot
        from VIVAANXMUSIC.core.userbot import assistants
        
        # Wait for assistants to be ready
        if not assistants:
            print(f"[Security] Waiting for assistants...")
            for _ in range(20):
                await asyncio.sleep(0.5)
                if assistants:
                    break
        
        if not assistants:
            print(f"[Security] No assistants available")
            return None
        
        print(f"[Security] Available assistants: {assistants}")
        
        # Use the first available assistant from the GLOBAL started instance
        if 1 in assistants:
            print(f"[Security] Using global assistant 1")
            return userbot.one
        elif 2 in assistants:
            print(f"[Security] Using global assistant 2")
            return userbot.two
        elif 3 in assistants:
            print(f"[Security] Using global assistant 3")
            return userbot.three
        elif 4 in assistants:
            print(f"[Security] Using global assistant 4")
            return userbot.four
        elif 5 in assistants:
            print(f"[Security] Using global assistant 5")
            return userbot.five
        
        print(f"[Security] No assistants in list")
        return None
            
    except Exception as e:
        print(f"[Security] Error getting userbot: {e}")
        import traceback
        traceback.print_exc()
        return None


# ==================== BIO CHECKING ====================

async def check_bio(client: Client, user_id: int) -> Tuple[bool, str]:
    """Check if user's bio contains links"""
    try:
        userbot = await get_userbot_client()
        
        if userbot:
            try:
                user = await userbot.get_users(user_id)
                bio = user.bio or ""
                
                if user.is_bot:
                    print(f"[Security] ⚠️ Bot account {user.first_name} - bio cannot be read")
                    return False, ""
                
                contains_link = has_link(bio)
                
                if bio:
                    print(f"[Security] ✅ {user.first_name}: '{bio[:50]}...' | Links: {contains_link}")
                    if contains_link:
                        print(f"[Security] Found: {extract_links(bio)}")
                
                return contains_link, bio
                
            except Exception as e:
                print(f"[Security] Userbot error: {e}")
                user = await client.get_users(user_id)
                return False, user.bio or ""
        else:
            user = await client.get_users(user_id)
            return False, user.bio or ""
        
    except Exception as e:
        print(f"[Security] Error: {e}")
        return False, ""


async def check_bio_detailed(client: Client, user_id: int) -> dict:
    """Detailed bio check"""
    try:
        userbot = await get_userbot_client()
        
        if userbot:
            try:
                user = await userbot.get_users(user_id)
                bio = user.bio or ""
                
                if user.is_bot:
                    return {
                        "has_link": False,
                        "bio": "⚠️ Bot account - bio cannot be read",
                        "links": [],
                        "link_count": 0,
                        "username": user.username,
                        "user_id": user.id,
                        "first_name": user.first_name,
                        "is_bot": True
                    }
                
                links_found = extract_links(bio)
                
                return {
                    "has_link": len(links_found) > 0,
                    "bio": bio if bio else "No bio",
                    "links": links_found,
                    "link_count": len(links_found),
                    "username": user.username,
                    "user_id": user.id,
                    "first_name": user.first_name,
                    "is_bot": False
                }
                
            except Exception as e:
                print(f"[Security] Userbot error: {e}")
                user = await client.get_users(user_id)
                return {
                    "has_link": False,
                    "bio": user.bio or "No bio",
                    "links": [],
                    "link_count": 0,
                    "username": user.username,
                    "user_id": user.id,
                    "first_name": user.first_name,
                    "is_bot": user.is_bot
                }
        else:
            user = await client.get_users(user_id)
            return {
                "has_link": False,
                "bio": user.bio or "No bio",
                "links": [],
                "link_count": 0,
                "username": user.username,
                "user_id": user.id,
                "first_name": user.first_name,
                "is_bot": user.is_bot
            }
            
    except Exception as e:
        print(f"[Security] Error: {e}")
        return {
            "has_link": False,
            "bio": "Error",
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
        print(f"[Security] Error: {e}")
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
