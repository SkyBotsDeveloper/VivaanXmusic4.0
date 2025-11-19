"""
Security Check Utilities
Bio link detection and user verification for group security
Part of VivaanXMusic Group Management System
"""

import re
from typing import Tuple, Optional
from pyrogram import Client
from pyrogram.types import User, Message


# ==================== LINK DETECTION PATTERNS ====================

# Comprehensive link patterns for bio checking
LINK_PATTERNS = [
    r'@\w+',                                    # @mentions and @usernames
    r't\.me/\w+',                               # Telegram t.me links
    r'telegram\.me/\w+',                        # Telegram telegram.me links
    r'tg://\w+',                                # Telegram tg:// protocol
    r'https?://[^\s]+',                         # HTTP/HTTPS URLs
    r'www\.[^\s]+',                             # www links
    
    # Social Media Platforms
    r'instagram\.com/[\w\.]+',                  # Instagram
    r'instagr\.am/[\w\.]+',                     # Instagram short
    r'tiktok\.com/@\w+',                        # TikTok
    r'twitter\.com/\w+',                        # Twitter
    r'x\.com/\w+',                              # X (formerly Twitter)
    r'facebook\.com/[\w\.]+',                   # Facebook
    r'fb\.com/[\w\.]+',                         # Facebook short
    r'youtube\.com/[\w@]+',                     # YouTube
    r'youtu\.be/[\w]+',                         # YouTube short
    r'linkedin\.com/in/[\w-]+',                 # LinkedIn
    r'snapchat\.com/add/\w+',                   # Snapchat
    r'reddit\.com/u/\w+',                       # Reddit
    r'twitch\.tv/\w+',                          # Twitch
    r'discord\.gg/\w+',                         # Discord invites
    
    # URL Shorteners
    r'bit\.ly/\w+',                             # Bitly
    r'tinyurl\.com/\w+',                        # TinyURL
    r'goo\.gl/\w+',                             # Google shortener
    r'ow\.ly/\w+',                              # Owly
    r'is\.gd/\w+',                              # Is.gd
    r't\.co/\w+',                               # Twitter shortener
    
    # Generic domain patterns
    r'\w+\.(com|org|net|io|shop|co|me|tv|app|dev|tech|xyz|info|biz|online|site|store|club|live|pro|world|life|today|fun|space|website|email|link|click|digital|download|cloud|host)',
]

# Compile patterns for performance
COMPILED_PATTERNS = [re.compile(pattern, re.IGNORECASE) for pattern in LINK_PATTERNS]


# ==================== LINK DETECTION FUNCTIONS ====================

def has_link(text: str) -> bool:
    """
    Check if text contains any links or URLs
    
    Args:
        text (str): Text to check
        
    Returns:
        bool: True if link found, False otherwise
    """
    if not text:
        return False
    
    # Check against all patterns
    for pattern in COMPILED_PATTERNS:
        if pattern.search(text):
            return True
    
    return False


def extract_links(text: str) -> list:
    """
    Extract all links from text
    
    Args:
        text (str): Text to extract links from
        
    Returns:
        list: List of found links
    """
    if not text:
        return []
    
    links = []
    for pattern in COMPILED_PATTERNS:
        matches = pattern.findall(text)
        links.extend(matches)
    
    return list(set(links))  # Remove duplicates


# ==================== BIO CHECKING ====================

async def check_bio(client: Client, user_id: int) -> Tuple[bool, str]:
    """
    Check if user's bio contains links
    
    Args:
        client (Client): Pyrogram client
        user_id (int): User ID to check
        
    Returns:
        Tuple[bool, str]: (has_link, bio_text)
    """
    try:
        user: User = await client.get_users(user_id)
        bio = user.bio or ""
        contains_link = has_link(bio)
        return contains_link, bio
    except Exception as e:
        print(f"[Security] Error checking bio for user {user_id}: {e}")
        return False, ""


async def check_bio_detailed(client: Client, user_id: int) -> dict:
    """
    Check user bio with detailed information
    
    Args:
        client (Client): Pyrogram client
        user_id (int): User ID to check
        
    Returns:
        dict: Detailed bio check results
    """
    try:
        user: User = await client.get_users(user_id)
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
        print(f"[Security] Error in detailed bio check for user {user_id}: {e}")
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
    """
    Extract target user from message (reply/mention/ID)
    Compatible with VivaanXMusic command patterns
    
    Args:
        message (Message): Message object
        
    Returns:
        Optional[User]: User object or None
    """
    # Check if replying to a message
    if message.reply_to_message:
        return message.reply_to_message.from_user
    
    # Check if user ID or username provided in command
    if len(message.command) < 2:
        return None
    
    user_input = message.command[1]
    
    try:
        # Try as user ID (numeric)
        if user_input.isdigit():
            return await message._client.get_users(int(user_input))
        
        # Try as username (with or without @)
        return await message._client.get_users(user_input)
        
    except Exception as e:
        print(f"[Security] Error getting target user: {e}")
        return None


async def get_user_info(client: Client, user_id: int) -> Optional[dict]:
    """
    Get basic user information
    
    Args:
        client (Client): Pyrogram client
        user_id (int): User ID
        
    Returns:
        Optional[dict]: User info or None
    """
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
    """
    Clean and truncate bio for preview
    
    Args:
        bio (str): Bio text
        max_length (int): Maximum length
        
    Returns:
        str: Cleaned preview text
    """
    if not bio:
        return "No bio"
    
    # Remove excessive whitespace
    bio = " ".join(bio.split())
    
    # Truncate if too long
    if len(bio) > max_length:
        return bio[:max_length] + "..."
    
    return bio


def format_links_list(links: list, max_display: int = 5) -> str:
    """
    Format list of links for display
    
    Args:
        links (list): List of links
        max_display (int): Maximum links to display
        
    Returns:
        str: Formatted links string
    """
    if not links:
        return "No links found"
    
    displayed = links[:max_display]
    result = "\n".join([f"├ `{link}`" for link in displayed])
    
    if len(links) > max_display:
        result += f"\n└ ... and {len(links) - max_display} more"
    
    return result
