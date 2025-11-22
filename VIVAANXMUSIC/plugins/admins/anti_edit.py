"""
Anti-Edit Plugin for VivaanXMusic Bot - ELITE VERSION
Detects and deletes edited messages with precision.
Properly distinguishes between reactions and actual edits.

Author: World's Best Developer Team
Version: 5.0 Elite Edition
"""

import asyncio
import logging
from typing import Optional, Dict, Set, Tuple
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import (
    MessageDeleteForbidden,
    UserNotParticipant,
    ChatAdminRequired,
    FloodWait,
    RPCError
)
from pyrogram.enums import ChatMemberStatus

from config import OWNER_ID
from VIVAANXMUSIC import app
from VIVAANXMUSIC.mongo.edit_tracker_db import (
    enable_antiedit,
    disable_antiedit,
    is_antiedit_enabled,
    add_authorized_user,
    remove_authorized_user,
    is_authorized_user,
    get_authorized_users,
    log_edit_action
)

# Logger setup
logger = logging.getLogger(__name__)

# Configuration
EDIT_WARNING_TIME = 60  # 60 seconds = 1 minute
WARNING_MESSAGE = (
    "⚠️ **Edited Message Detected!**\n\n"
    "❌ Message editing is not allowed in this group.\n\n"
    "⏱️ Your edited message will be deleted in **1 minute**.\n\n"
    "💡 Contact admins if you need edit permission."
)

# In-memory caches
admin_cache: Dict[int, Dict[int, bool]] = {}
message_content_cache: Dict[str, Tuple[str, int]] = {}  # {msg_key: (content_hash, timestamp)}
cache_expiry = 300  # 5 minutes


class AntiEditManager:
    """Elite-level anti-edit management system."""
    
    def __init__(self):
        self.pending_deletions: Dict[str, asyncio.Task] = {}
        self.processing_edits: Set[str] = set()
    
    async def is_admin_or_owner(self, chat_id: int, user_id: int) -> bool:
        """
        Check if user is admin or owner with intelligent caching.
        """
        if user_id == OWNER_ID:
            return True
        
        # Check cache
        if chat_id in admin_cache and user_id in admin_cache[chat_id]:
            return admin_cache[chat_id][user_id]
        
        try:
            member = await app.get_chat_member(chat_id, user_id)
            is_admin = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
            
            # Update cache
            if chat_id not in admin_cache:
                admin_cache[chat_id] = {}
            admin_cache[chat_id][user_id] = is_admin
            
            return is_admin
            
        except Exception as e:
            logger.warning(f"Error checking admin status: {e}")
            return False
    
    def get_message_content_hash(self, message: Message) -> Optional[str]:
        """
        Generate a unique hash of message content to detect real edits.
        This includes text, caption, and media type.
        
        Returns:
            str: Content hash or None if no content
        """
        content_parts = []
        
        # Add text content
        if message.text:
            content_parts.append(f"text:{message.text}")
        
        # Add caption
        if message.caption:
            content_parts.append(f"caption:{message.caption}")
        
        # Add media type (photo, video, etc.)
        if message.media:
            content_parts.append(f"media:{message.media}")
        
        # Add entities (formatting, links, etc.)
        if message.entities:
            entities_str = ",".join([f"{e.type}:{e.offset}:{e.length}" for e in message.entities])
            content_parts.append(f"entities:{entities_str}")
        
        if message.caption_entities:
            entities_str = ",".join([f"{e.type}:{e.offset}:{e.length}" for e in message.caption_entities])
            content_parts.append(f"cap_entities:{entities_str}")
        
        if not content_parts:
            return None
        
        # Create hash
        return "|".join(content_parts)
    
    def is_real_content_edit(self, message: Message) -> bool:
        """
        ELITE METHOD: Determine if message content actually changed.
        
        This is the KEY function that distinguishes reactions from edits.
        
        How it works:
        1. Store hash of original message content
        2. When edit event fires, compare current content hash with stored hash
        3. If hash unchanged → Just a reaction (ignore)
        4. If hash changed → Real edit (delete)
        
        Args:
            message: The edited message object
            
        Returns:
            bool: True if content was actually edited, False if just reaction
        """
        chat_id = message.chat.id
        message_id = message.id
        msg_key = f"{chat_id}:{message_id}"
        
        # Get current content hash
        current_hash = self.get_message_content_hash(message)
        
        # If no content (service message, etc.), ignore
        if current_hash is None:
            return False
        
        # Check if we have previous content stored
        if msg_key in message_content_cache:
            previous_hash, _ = message_content_cache[msg_key]
            
            # Compare hashes
            if current_hash == previous_hash:
                # Content unchanged → Just a reaction or metadata update
                logger.debug(f"No content change detected for {msg_key} - likely a reaction")
                return False
            else:
                # Content changed → Real edit
                logger.info(f"Real content edit detected for {msg_key}")
                message_content_cache[msg_key] = (current_hash, int(datetime.utcnow().timestamp()))
                return True
        else:
            # First time seeing this message, store its hash
            message_content_cache[msg_key] = (current_hash, int(datetime.utcnow().timestamp()))
            return False  # Can't determine on first sight, assume no edit
    
    async def should_delete_edit(self, chat_id: int, user_id: int) -> bool:
        """
        Determine if edited message should be deleted.
        """
        # Check if anti-edit enabled
        if not await is_antiedit_enabled(chat_id):
            return False
        
        # Check if user is authorized
        if await is_authorized_user(chat_id, user_id):
            return False
        
        return True
    
    async def handle_edited_message(self, client: Client, message: Message):
        """
        ELITE HANDLER: Process edited messages with precision.
        """
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        message_id = message.id
        
        # Skip if no user
        if not user_id:
            return
        
        # CRITICAL CHECK: Is this a real content edit or just a reaction?
        if not self.is_real_content_edit(message):
            logger.debug(f"Ignoring non-edit update for message {message_id} in chat {chat_id}")
            return
        
        # Create unique identifier
        edit_key = f"{chat_id}:{message_id}:{user_id}"
        
        # Prevent duplicate processing
        if edit_key in self.processing_edits:
            return
        
        self.processing_edits.add(edit_key)
        
        try:
            # Check if we should delete this edit
            if not await self.should_delete_edit(chat_id, user_id):
                return
            
            # Send warning message
            warning_msg = None
            try:
                warning_msg = await message.reply_text(
                    WARNING_MESSAGE,
                    quote=True
                )
                
                logger.info(
                    f"Real edit detected: User {user_id} edited message {message_id} in chat {chat_id}. "
                    f"Deletion scheduled in {EDIT_WARNING_TIME} seconds."
                )
                
                # Wait 1 minute
                await asyncio.sleep(EDIT_WARNING_TIME)
                
                # Delete the edited message
                try:
                    await message.delete()
                    logger.info(f"Deleted edited message {message_id} from user {user_id} in chat {chat_id}")
                    
                    # Log to database
                    await log_edit_action(
                        chat_id=chat_id,
                        user_id=user_id,
                        message_id=message_id,
                        action="deleted",
                        timestamp=datetime.utcnow()
                    )
                    
                    # Clean up cache entry
                    msg_key = f"{chat_id}:{message_id}"
                    message_content_cache.pop(msg_key, None)
                    
                except MessageDeleteForbidden:
                    logger.warning(f"Cannot delete message {message_id} - insufficient permissions")
                except Exception as e:
                    logger.error(f"Error deleting message {message_id}: {e}")
                
                # Delete warning message
                if warning_msg:
                    await asyncio.sleep(3)
                    try:
                        await warning_msg.delete()
                    except Exception:
                        pass
                        
            except FloodWait as e:
                logger.warning(f"FloodWait: Sleeping for {e.value} seconds")
                await asyncio.sleep(e.value)
            except Exception as e:
                logger.error(f"Error handling edit: {e}")
                
        finally:
            self.processing_edits.discard(edit_key)


# Initialize manager
anti_edit_manager = AntiEditManager()


# ==================== CACHE ORIGINAL MESSAGES ====================

@app.on_message(
    filters.group & ~filters.bot & ~filters.service & (filters.text | filters.caption)
)
async def cache_message_content(client: Client, message: Message):
    """
    Cache original message content to detect real edits later.
    This is CRITICAL for distinguishing reactions from edits.
    """
    try:
        chat_id = message.chat.id
        message_id = message.id
        msg_key = f"{chat_id}:{message_id}"
        
        # Get and store content hash
        content_hash = anti_edit_manager.get_message_content_hash(message)
        if content_hash:
            message_content_cache[msg_key] = (content_hash, int(datetime.utcnow().timestamp()))
            logger.debug(f"Cached content for message {msg_key}")
            
    except Exception as e:
        logger.debug(f"Error caching message content: {e}")


# ==================== MESSAGE EDIT HANDLER ====================

@app.on_edited_message(
    filters.group & ~filters.bot & ~filters.service
)
async def on_message_edited(client: Client, message: Message):
    """
    Handler for edited messages with elite-level detection.
    Ignores reactions, only processes real text edits.
    """
    try:
        await anti_edit_manager.handle_edited_message(client, message)
    except Exception as e:
        logger.error(f"Error in edit handler: {e}", exc_info=True)


# ==================== COMMAND HANDLERS ====================

@app.on_message(
    filters.command("antiedit") & filters.group
)
async def toggle_antiedit(client: Client, message: Message):
    """Toggle anti-edit feature."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not await anti_edit_manager.is_admin_or_owner(chat_id, user_id):
        await message.reply_text(
            "❌ **Permission Denied**\n\n"
            "Only admins and group owner can toggle anti-edit feature."
        )
        return
    
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        current_status = "✅ Enabled" if await is_antiedit_enabled(chat_id) else "❌ Disabled"
        await message.reply_text(
            f"**Anti-Edit Status:** {current_status}\n\n"
            "**Usage:**\n"
            "• `/antiedit on` - Enable\n"
            "• `/antiedit off` - Disable\n\n"
            "**Features:**\n"
            "⏱️ 1-minute warning before deletion\n"
            "🎯 Ignores emoji reactions\n"
            "🔒 Authorized users can edit freely"
        )
        return
    
    action = args[1].lower()
    
    if action == "on":
        await enable_antiedit(chat_id)
        await message.reply_text(
            "✅ **Anti-Edit Enabled**\n\n"
            "All edited messages will be deleted after a 1-minute warning.\n\n"
            "🎯 **Smart Detection:** Emoji reactions are ignored.\n"
            "💡 Use `/authedit` to authorize users."
        )
        logger.info(f"Anti-edit enabled in chat {chat_id}")
        
    elif action == "off":
        await disable_antiedit(chat_id)
        await message.reply_text(
            "❌ **Anti-Edit Disabled**\n\n"
            "Message editing is now allowed."
        )
        logger.info(f"Anti-edit disabled in chat {chat_id}")
        
    else:
        await message.reply_text("⚠️ Use `/antiedit on` or `/antiedit off`")


@app.on_message(
    filters.command("authedit") & filters.group
)
async def manage_authorized_users(client: Client, message: Message):
    """Manage authorized users."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not await anti_edit_manager.is_admin_or_owner(chat_id, user_id):
        await message.reply_text(
            "❌ **Permission Denied**\n\n"
            "Only admins can manage authorized users."
        )
        return
    
    command_parts = message.text.split(maxsplit=1)
    action = command_parts[1].lower() if len(command_parts) > 1 else "add"
    
    # List action
    if action == "list":
        authorized = await get_authorized_users(chat_id)
        
        if not authorized:
            await message.reply_text(
                "📋 **Authorized Users**\n\n"
                "No users authorized yet.\n\n"
                "💡 Reply to a user with `/authedit` to authorize."
            )
            return
        
        user_list = []
        for idx, auth_user_id in enumerate(authorized, 1):
            try:
                user = await client.get_users(auth_user_id)
                name = user.first_name + (f" {user.last_name}" if user.last_name else "")
                username = f"@{user.username}" if user.username else ""
                user_list.append(f"{idx}. {name} {username}\n   └ ID: `{auth_user_id}`")
            except Exception:
                user_list.append(f"{idx}. User ID: `{auth_user_id}`")
        
        await message.reply_text(
            f"📋 **Authorized Users** ({len(authorized)})\n\n"
            + "\n\n".join(user_list) +
            "\n\n✅ These users can edit without restriction."
        )
        return
    
    # Require reply for add/remove
    if not message.reply_to_message:
        await message.reply_text(
            "⚠️ **Reply Required**\n\n"
            "**Commands:**\n"
            "• `/authedit` (reply) - Authorize user\n"
            "• `/authedit remove` (reply) - Remove authorization\n"
            "• `/authedit list` - Show authorized users"
        )
        return
    
    target_user = message.reply_to_message.from_user
    if not target_user:
        await message.reply_text("❌ Cannot identify user.")
        return
    
    target_user_id = target_user.id
    target_mention = target_user.mention
    
    # Add authorization
    if action == "add" or action not in ["remove", "list"]:
        if await is_authorized_user(chat_id, target_user_id):
            await message.reply_text(
                f"ℹ️ {target_mention} is already authorized.\n\n"
                f"Use `/authedit remove` to revoke."
            )
            return
        
        success = await add_authorized_user(chat_id, target_user_id)
        
        if success:
            await message.reply_text(
                f"✅ **Authorization Granted**\n\n"
                f"**User:** {target_mention}\n"
                f"**ID:** `{target_user_id}`\n\n"
                f"🔓 Can now edit messages freely."
            )
            logger.info(f"User {target_user_id} authorized in chat {chat_id}")
        else:
            await message.reply_text("❌ Failed to authorize user.")
    
    # Remove authorization
    elif action == "remove":
        if not await is_authorized_user(chat_id, target_user_id):
            await message.reply_text(f"ℹ️ {target_mention} is not authorized.")
            return
        
        success = await remove_authorized_user(chat_id, target_user_id)
        
        if success:
            await message.reply_text(
                f"❌ **Authorization Removed**\n\n"
                f"**User:** {target_mention}\n"
                f"**ID:** `{target_user_id}`\n\n"
                f"🔒 Edits will now be deleted after warning."
            )
            logger.info(f"User {target_user_id} deauthorized in chat {chat_id}")
        else:
            await message.reply_text("❌ Failed to remove authorization.")


# ==================== CACHE CLEANUP ====================

async def cleanup_caches_periodically():
    """Clean up expired cache entries."""
    while True:
        await asyncio.sleep(cache_expiry)
        
        try:
            # Clean admin cache
            admin_cache.clear()
            
            # Clean old message content cache (older than 24 hours)
            current_time = int(datetime.utcnow().timestamp())
            expired_keys = [
                key for key, (_, timestamp) in message_content_cache.items()
                if current_time - timestamp > 86400  # 24 hours
            ]
            
            for key in expired_keys:
                message_content_cache.pop(key, None)
            
            logger.debug(f"Cache cleanup: Removed {len(expired_keys)} expired message entries")
            
        except Exception as e:
            logger.error(f"Error during cache cleanup: {e}")


# Start cleanup task
asyncio.create_task(cleanup_caches_periodically())

logger.info("✅ Anti-Edit Plugin Loaded - ELITE VERSION with Smart Reaction Detection")
