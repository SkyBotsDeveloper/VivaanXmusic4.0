"""
Anti-Edit Plugin for VivaanXMusic Bot - ULTIMATE ELITE VERSION
Works across unlimited groups simultaneously with perfect accuracy.

Author: Elite Development Team
Version: 6.0 Ultimate Edition
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

# In-memory caches with proper isolation per group
admin_cache: Dict[int, Dict[int, bool]] = {}  # {chat_id: {user_id: is_admin}}
message_content_cache: Dict[str, Tuple[str, int]] = {}  # {chat:msg_id: (content_hash, timestamp)}
cache_expiry = 300  # 5 minutes


class AntiEditManager:
    """Ultimate elite anti-edit management system with multi-group support."""
    
    def __init__(self):
        self.pending_deletions: Dict[str, asyncio.Task] = {}
        self.processing_edits: Set[str] = set()
        logger.info("🎯 AntiEditManager initialized for multi-group operation")
    
    async def is_admin_or_owner(self, chat_id: int, user_id: int) -> bool:
        """
        Check if user is admin or owner with intelligent caching.
        Properly isolated per group.
        """
        # Bot owner has global admin rights
        if user_id == OWNER_ID:
            return True
        
        # Check cache for this specific group
        if chat_id in admin_cache:
            if user_id in admin_cache[chat_id]:
                return admin_cache[chat_id][user_id]
        
        try:
            member = await app.get_chat_member(chat_id, user_id)
            is_admin = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
            
            # Initialize group cache if needed
            if chat_id not in admin_cache:
                admin_cache[chat_id] = {}
            
            # Store result
            admin_cache[chat_id][user_id] = is_admin
            
            logger.debug(f"User {user_id} admin status in chat {chat_id}: {is_admin}")
            return is_admin
            
        except Exception as e:
            logger.warning(f"Error checking admin status for user {user_id} in chat {chat_id}: {e}")
            return False
    
    def get_message_content_hash(self, message: Message) -> Optional[str]:
        """
        Generate unique hash of message content to detect real edits.
        Includes text, caption, media, and formatting.
        """
        content_parts = []
        
        # Add text content
        if message.text:
            content_parts.append(f"text:{message.text}")
        
        # Add caption
        if message.caption:
            content_parts.append(f"caption:{message.caption}")
        
        # Add media type
        if message.media:
            content_parts.append(f"media:{message.media}")
        
        # Add text entities (bold, italic, links, etc.)
        if message.entities:
            entities_str = ",".join([
                f"{e.type}:{e.offset}:{e.length}" 
                for e in message.entities
            ])
            content_parts.append(f"entities:{entities_str}")
        
        # Add caption entities
        if message.caption_entities:
            entities_str = ",".join([
                f"{e.type}:{e.offset}:{e.length}" 
                for e in message.caption_entities
            ])
            content_parts.append(f"cap_entities:{entities_str}")
        
        if not content_parts:
            return None
        
        # Create hash
        content_hash = "|".join(content_parts)
        return content_hash
    
    def is_real_content_edit(self, message: Message) -> bool:
        """
        CRITICAL FUNCTION: Determine if message content actually changed.
        This distinguishes reactions from real edits.
        
        Returns:
            bool: True if content was edited, False if just reaction
        """
        chat_id = message.chat.id
        message_id = message.id
        msg_key = f"{chat_id}:{message_id}"
        
        # Get current content hash
        current_hash = self.get_message_content_hash(message)
        
        # No content = ignore
        if current_hash is None:
            logger.debug(f"No content in message {msg_key}, ignoring")
            return False
        
        # Check if we have previous content
        if msg_key in message_content_cache:
            previous_hash, _ = message_content_cache[msg_key]
            
            if current_hash == previous_hash:
                # Content unchanged = reaction only
                logger.debug(f"✓ No content change in {msg_key} - reaction ignored")
                return False
            else:
                # Content changed = real edit
                logger.info(f"⚠️ Real edit detected in {msg_key}")
                message_content_cache[msg_key] = (current_hash, int(datetime.utcnow().timestamp()))
                return True
        else:
            # First time seeing this message
            message_content_cache[msg_key] = (current_hash, int(datetime.utcnow().timestamp()))
            logger.debug(f"Cached new message {msg_key}")
            return False
    
    async def should_delete_edit(self, chat_id: int, user_id: int) -> bool:
        """
        Determine if edited message should be deleted.
        Checks per-group configuration.
        """
        # Check if anti-edit is enabled in THIS specific group
        enabled = await is_antiedit_enabled(chat_id)
        logger.debug(f"Anti-edit status for chat {chat_id}: {enabled}")
        
        if not enabled:
            return False
        
        # Check if user is authorized in THIS specific group
        authorized = await is_authorized_user(chat_id, user_id)
        logger.debug(f"User {user_id} authorized in chat {chat_id}: {authorized}")
        
        if authorized:
            return False
        
        # Delete the edit
        return True
    
    async def handle_edited_message(self, client: Client, message: Message):
        """
        ULTIMATE HANDLER: Process edited messages with elite precision.
        Works across all groups simultaneously.
        """
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        message_id = message.id
        
        # Skip if no user
        if not user_id:
            logger.debug(f"No user in edit event for message {message_id}")
            return
        
        logger.debug(f"Processing edit: chat={chat_id}, msg={message_id}, user={user_id}")
        
        # CRITICAL: Is this a real content edit or just a reaction?
        if not self.is_real_content_edit(message):
            return
        
        # Create unique identifier
        edit_key = f"{chat_id}:{message_id}:{user_id}"
        
        # Prevent duplicate processing
        if edit_key in self.processing_edits:
            logger.debug(f"Already processing {edit_key}, skipping duplicate")
            return
        
        self.processing_edits.add(edit_key)
        
        try:
            # Check if we should delete (per-group check)
            should_delete = await self.should_delete_edit(chat_id, user_id)
            
            if not should_delete:
                logger.debug(f"Edit allowed for user {user_id} in chat {chat_id}")
                return
            
            logger.info(f"🚨 Deleting edit from user {user_id} in chat {chat_id}")
            
            # Send warning message
            warning_msg = None
            try:
                warning_msg = await message.reply_text(
                    WARNING_MESSAGE,
                    quote=True
                )
                
                logger.info(
                    f"⏱️ Warning sent to user {user_id} in chat {chat_id}. "
                    f"Deletion in {EDIT_WARNING_TIME}s"
                )
                
                # Wait 1 minute
                await asyncio.sleep(EDIT_WARNING_TIME)
                
                # Delete the edited message
                try:
                    await message.delete()
                    logger.info(f"✅ Deleted edited message {message_id} from user {user_id} in chat {chat_id}")
                    
                    # Log to database
                    await log_edit_action(
                        chat_id=chat_id,
                        user_id=user_id,
                        message_id=message_id,
                        action="deleted",
                        timestamp=datetime.utcnow()
                    )
                    
                    # Clean up cache
                    msg_key = f"{chat_id}:{message_id}"
                    message_content_cache.pop(msg_key, None)
                    
                except MessageDeleteForbidden:
                    logger.warning(f"❌ Cannot delete message {message_id} in chat {chat_id} - no permission")
                except Exception as e:
                    logger.error(f"❌ Error deleting message {message_id}: {e}")
                
                # Delete warning message
                if warning_msg:
                    await asyncio.sleep(3)
                    try:
                        await warning_msg.delete()
                    except Exception:
                        pass
                        
            except FloodWait as e:
                logger.warning(f"⏳ FloodWait: {e.value}s")
                await asyncio.sleep(e.value)
            except Exception as e:
                logger.error(f"❌ Error handling edit: {e}")
                
        finally:
            self.processing_edits.discard(edit_key)


# Initialize manager
anti_edit_manager = AntiEditManager()


# ==================== CACHE ORIGINAL MESSAGES ====================

@app.on_message(
    filters.group & 
    ~filters.bot & 
    ~filters.service & 
    (filters.text | filters.caption)
)
async def cache_message_content(client: Client, message: Message):
    """
    Cache original message content for ALL groups.
    This enables edit detection across unlimited groups.
    """
    try:
        chat_id = message.chat.id
        message_id = message.id
        msg_key = f"{chat_id}:{message_id}"
        
        # Get and store content hash
        content_hash = anti_edit_manager.get_message_content_hash(message)
        if content_hash:
            message_content_cache[msg_key] = (content_hash, int(datetime.utcnow().timestamp()))
            logger.debug(f"📝 Cached message {msg_key}")
            
    except Exception as e:
        logger.debug(f"Cache error: {e}")


# ==================== MESSAGE EDIT HANDLER ====================

@app.on_edited_message(
    filters.group & 
    ~filters.bot & 
    ~filters.service
)
async def on_message_edited(client: Client, message: Message):
    """
    Global handler for ALL edited messages in ALL groups.
    Automatically works when bot is added to any group.
    """
    try:
        await anti_edit_manager.handle_edited_message(client, message)
    except Exception as e:
        logger.error(f"❌ Critical error in edit handler: {e}", exc_info=True)


# ==================== COMMAND HANDLERS ====================

@app.on_message(
    filters.command(["antiedit"], prefixes="/") & 
    filters.group
)
async def toggle_antiedit(client: Client, message: Message):
    """
    Toggle anti-edit feature for the current group.
    Works independently in each group.
    """
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        logger.info(f"📢 /antiedit command from user {user_id} in chat {chat_id}")
        
        # Check admin permissions
        if not await anti_edit_manager.is_admin_or_owner(chat_id, user_id):
            await message.reply_text(
                "❌ **Permission Denied**\n\n"
                "Only admins and group owner can toggle anti-edit."
            )
            return
        
        # Parse arguments
        command_text = message.text.strip()
        parts = command_text.split(maxsplit=1)
        
        if len(parts) < 2:
            # Show status
            current_status = await is_antiedit_enabled(chat_id)
            status_text = "✅ Enabled" if current_status else "❌ Disabled"
            
            await message.reply_text(
                f"**Anti-Edit Status:** {status_text}\n\n"
                "**Usage:**\n"
                "• `/antiedit on` - Enable\n"
                "• `/antiedit off` - Disable\n\n"
                "**Features:**\n"
                "⏱️ 1-minute warning\n"
                "🎯 Ignores reactions\n"
                "🔒 Authorized user system"
            )
            return
        
        action = parts[1].lower()
        
        if action == "on":
            await enable_antiedit(chat_id)
            await message.reply_text(
                "✅ **Anti-Edit Enabled**\n\n"
                "All edited messages will be deleted after 1-minute warning.\n\n"
                "🎯 Reactions are ignored.\n"
                "💡 Use `/authedit` to authorize users."
            )
            logger.info(f"✅ Anti-edit enabled in chat {chat_id}")
            
        elif action == "off":
            await disable_antiedit(chat_id)
            await message.reply_text(
                "❌ **Anti-Edit Disabled**\n\n"
                "Message editing is now allowed."
            )
            logger.info(f"❌ Anti-edit disabled in chat {chat_id}")
            
        else:
            await message.reply_text(
                "⚠️ Invalid option.\n\n"
                "Use `/antiedit on` or `/antiedit off`"
            )
            
    except Exception as e:
        logger.error(f"Error in /antiedit command: {e}", exc_info=True)
        await message.reply_text("❌ An error occurred. Please try again.")


@app.on_message(
    filters.command(["authedit"], prefixes="/") & 
    filters.group
)
async def manage_authorized_users(client: Client, message: Message):
    """
    Manage authorized users for the current group.
    Each group has independent authorized user list.
    """
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        logger.info(f"📢 /authedit command from user {user_id} in chat {chat_id}")
        
        # Check admin permissions
        if not await anti_edit_manager.is_admin_or_owner(chat_id, user_id):
            await message.reply_text(
                "❌ **Permission Denied**\n\n"
                "Only admins can manage authorized users."
            )
            return
        
        # Parse command
        command_text = message.text.strip()
        parts = command_text.split(maxsplit=1)
        action = parts[1].lower() if len(parts) > 1 else "add"
        
        # List action
        if action == "list":
            authorized = await get_authorized_users(chat_id)
            
            if not authorized:
                await message.reply_text(
                    "📋 **Authorized Users**\n\n"
                    "No users authorized in this group.\n\n"
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
                "• `/authedit` (reply) - Authorize\n"
                "• `/authedit remove` (reply) - Remove\n"
                "• `/authedit list` - Show all"
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
            # Check if already authorized
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
                logger.info(f"✅ User {target_user_id} authorized in chat {chat_id}")
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
                logger.info(f"❌ User {target_user_id} deauthorized in chat {chat_id}")
            else:
                await message.reply_text("❌ Failed to remove authorization.")
                
    except Exception as e:
        logger.error(f"Error in /authedit command: {e}", exc_info=True)
        await message.reply_text("❌ An error occurred. Please try again.")


# ==================== CACHE CLEANUP ====================

async def cleanup_caches_periodically():
    """Clean up expired cache entries to prevent memory bloat."""
    while True:
        await asyncio.sleep(cache_expiry)
        
        try:
            # Clean admin cache
            old_admin_count = len(admin_cache)
            admin_cache.clear()
            
            # Clean old message content cache (older than 24 hours)
            current_time = int(datetime.utcnow().timestamp())
            expired_keys = [
                key for key, (_, timestamp) in message_content_cache.items()
                if current_time - timestamp > 86400  # 24 hours
            ]
            
            for key in expired_keys:
                message_content_cache.pop(key, None)
            
            logger.info(
                f"🧹 Cache cleanup: "
                f"Admin cache cleared ({old_admin_count} groups), "
                f"{len(expired_keys)} expired messages removed"
            )
            
        except Exception as e:
            logger.error(f"Error during cache cleanup: {e}")


# Start cleanup task
asyncio.create_task(cleanup_caches_periodically())

logger.info("=" * 60)
logger.info("✅ ANTI-EDIT PLUGIN LOADED - ULTIMATE ELITE VERSION")
logger.info("🌐 Multi-Group Support: ACTIVE")
logger.info("🎯 Smart Reaction Detection: ACTIVE")
logger.info("⏱️ Warning Time: 60 seconds")
logger.info("=" * 60)
