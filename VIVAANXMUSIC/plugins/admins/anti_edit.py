"""
Anti-Edit Plugin for VivaanXMusic Bot - FINAL PERFECT VERSION
Production-ready for public use with perfect command handling.

Author: Elite Development Team  
Version: 7.0 Final Release
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
EDIT_WARNING_TIME = 60  # 60 seconds
WARNING_MESSAGE = (
    "⚠️ **Edited Message Detected!**\n\n"
    "❌ Message editing is not allowed in this group.\n\n"
    "⏱️ Your edited message will be deleted in **1 minute**.\n\n"
    "💡 Contact admins if you need edit permission."
)

# Caches
admin_cache: Dict[int, Dict[int, bool]] = {}
message_content_cache: Dict[str, Tuple[str, int]] = {}
cache_expiry = 300


class AntiEditManager:
    """Production-ready anti-edit manager for public bots."""
    
    def __init__(self):
        self.pending_deletions: Dict[str, asyncio.Task] = {}
        self.processing_edits: Set[str] = set()
        logger.info("🎯 AntiEditManager initialized")
    
    async def is_admin_or_owner(self, chat_id: int, user_id: int) -> bool:
        """Check admin status with caching."""
        if user_id == OWNER_ID:
            return True
        
        if chat_id in admin_cache and user_id in admin_cache[chat_id]:
            return admin_cache[chat_id][user_id]
        
        try:
            member = await app.get_chat_member(chat_id, user_id)
            is_admin = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
            
            if chat_id not in admin_cache:
                admin_cache[chat_id] = {}
            admin_cache[chat_id][user_id] = is_admin
            
            return is_admin
            
        except Exception as e:
            logger.warning(f"Admin check error: {e}")
            return False
    
    def get_message_content_hash(self, message: Message) -> Optional[str]:
        """Generate content hash for edit detection."""
        content_parts = []
        
        if message.text:
            content_parts.append(f"text:{message.text}")
        if message.caption:
            content_parts.append(f"caption:{message.caption}")
        if message.media:
            content_parts.append(f"media:{message.media}")
        if message.entities:
            entities_str = ",".join([f"{e.type}:{e.offset}:{e.length}" for e in message.entities])
            content_parts.append(f"entities:{entities_str}")
        if message.caption_entities:
            entities_str = ",".join([f"{e.type}:{e.offset}:{e.length}" for e in message.caption_entities])
            content_parts.append(f"cap_entities:{entities_str}")
        
        if not content_parts:
            return None
        
        return "|".join(content_parts)
    
    def is_real_content_edit(self, message: Message) -> bool:
        """Detect if content actually changed (not just reaction)."""
        chat_id = message.chat.id
        message_id = message.id
        msg_key = f"{chat_id}:{message_id}"
        
        current_hash = self.get_message_content_hash(message)
        
        if current_hash is None:
            return False
        
        if msg_key in message_content_cache:
            previous_hash, _ = message_content_cache[msg_key]
            
            if current_hash == previous_hash:
                logger.debug(f"✓ Reaction only: {msg_key}")
                return False
            else:
                logger.info(f"⚠️ Real edit: {msg_key}")
                message_content_cache[msg_key] = (current_hash, int(datetime.utcnow().timestamp()))
                return True
        else:
            message_content_cache[msg_key] = (current_hash, int(datetime.utcnow().timestamp()))
            return False
    
    async def should_delete_edit(self, chat_id: int, user_id: int) -> bool:
        """Check if edit should be deleted."""
        enabled = await is_antiedit_enabled(chat_id)
        logger.debug(f"Chat {chat_id} anti-edit enabled: {enabled}")
        
        if not enabled:
            return False
        
        authorized = await is_authorized_user(chat_id, user_id)
        logger.debug(f"User {user_id} authorized in {chat_id}: {authorized}")
        
        if authorized:
            return False
        
        return True
    
    async def handle_edited_message(self, client: Client, message: Message):
        """Handle edited messages with precision."""
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        message_id = message.id
        
        if not user_id:
            return
        
        # Check if real edit
        if not self.is_real_content_edit(message):
            return
        
        edit_key = f"{chat_id}:{message_id}:{user_id}"
        
        if edit_key in self.processing_edits:
            return
        
        self.processing_edits.add(edit_key)
        
        try:
            should_delete = await self.should_delete_edit(chat_id, user_id)
            
            if not should_delete:
                logger.debug(f"Edit allowed: user={user_id}, chat={chat_id}")
                return
            
            logger.info(f"🚨 Deleting edit: user={user_id}, chat={chat_id}")
            
            warning_msg = None
            try:
                warning_msg = await message.reply_text(WARNING_MESSAGE, quote=True)
                logger.info(f"⏱️ Warning sent, deletion in {EDIT_WARNING_TIME}s")
                
                await asyncio.sleep(EDIT_WARNING_TIME)
                
                try:
                    await message.delete()
                    logger.info(f"✅ Deleted message {message_id}")
                    
                    await log_edit_action(
                        chat_id=chat_id,
                        user_id=user_id,
                        message_id=message_id,
                        action="deleted",
                        timestamp=datetime.utcnow()
                    )
                    
                    msg_key = f"{chat_id}:{message_id}"
                    message_content_cache.pop(msg_key, None)
                    
                except MessageDeleteForbidden:
                    logger.warning(f"❌ No permission to delete in {chat_id}")
                except Exception as e:
                    logger.error(f"❌ Delete error: {e}")
                
                if warning_msg:
                    await asyncio.sleep(3)
                    try:
                        await warning_msg.delete()
                    except:
                        pass
                        
            except FloodWait as e:
                logger.warning(f"⏳ FloodWait: {e.value}s")
                await asyncio.sleep(e.value)
            except Exception as e:
                logger.error(f"❌ Handler error: {e}")
                
        finally:
            self.processing_edits.discard(edit_key)


# Initialize
anti_edit_manager = AntiEditManager()


# ==================== CACHE MESSAGES ====================

@app.on_message(
    filters.group & ~filters.bot & ~filters.service & (filters.text | filters.caption)
)
async def cache_message_content(client: Client, message: Message):
    """Cache original messages for edit detection."""
    try:
        msg_key = f"{message.chat.id}:{message.id}"
        content_hash = anti_edit_manager.get_message_content_hash(message)
        if content_hash:
            message_content_cache[msg_key] = (content_hash, int(datetime.utcnow().timestamp()))
    except:
        pass


# ==================== EDIT HANDLER ====================

@app.on_edited_message(filters.group & ~filters.bot & ~filters.service)
async def on_message_edited(client: Client, message: Message):
    """Handle all edited messages."""
    try:
        await anti_edit_manager.handle_edited_message(client, message)
    except Exception as e:
        logger.error(f"❌ Edit handler error: {e}", exc_info=True)


# ==================== COMMANDS ====================

@app.on_message(filters.command("antiedit") & filters.group)
async def cmd_antiedit(client: Client, message: Message):
    """
    Enable/disable anti-edit feature.
    Usage: /antiedit on | /antiedit off
    """
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        logger.info(f"📢 /antiedit from user {user_id} in chat {chat_id}")
        
        # Check permissions
        is_admin = await anti_edit_manager.is_admin_or_owner(chat_id, user_id)
        logger.info(f"   User {user_id} is admin: {is_admin}")
        
        if not is_admin:
            await message.reply_text(
                "❌ **Permission Denied**\n\n"
                "Only group admins can use this command."
            )
            return
        
        # Parse command
        args = message.text.split()
        
        if len(args) < 2:
            # Show status
            enabled = await is_antiedit_enabled(chat_id)
            status = "✅ **Enabled**" if enabled else "❌ **Disabled**"
            
            await message.reply_text(
                f"**Anti-Edit Status:** {status}\n\n"
                "**How to use:**\n"
                "• `/antiedit on` - Enable anti-edit\n"
                "• `/antiedit off` - Disable anti-edit\n\n"
                "**Features:**\n"
                "⏱️ 1-minute warning before deletion\n"
                "🎯 Ignores emoji reactions\n"
                "🔒 Supports authorized users\n\n"
                "**Other commands:**\n"
                "• `/authedit` - Manage authorized users"
            )
            logger.info(f"   Status shown to user")
            return
        
        action = args[1].lower()
        
        if action == "on":
            await enable_antiedit(chat_id)
            await message.reply_text(
                "✅ **Anti-Edit Enabled!**\n\n"
                "From now on:\n"
                "• All edited messages will be deleted after 1-minute warning\n"
                "• Emoji reactions are ignored\n"
                "• Use `/authedit` (reply to user) to authorize someone\n\n"
                "**Note:** Authorized users can edit without restriction."
            )
            logger.info(f"✅ Anti-edit ENABLED in chat {chat_id}")
            
        elif action == "off":
            await disable_antiedit(chat_id)
            await message.reply_text(
                "❌ **Anti-Edit Disabled!**\n\n"
                "Message editing is now allowed for everyone.\n\n"
                "Use `/antiedit on` to enable it again."
            )
            logger.info(f"❌ Anti-edit DISABLED in chat {chat_id}")
            
        else:
            await message.reply_text(
                "⚠️ **Invalid option!**\n\n"
                "Use:\n"
                "• `/antiedit on` - to enable\n"
                "• `/antiedit off` - to disable"
            )
            
    except Exception as e:
        logger.error(f"❌ /antiedit command error: {e}", exc_info=True)
        await message.reply_text(
            "❌ **Error occurred!**\n\n"
            "Please try again or contact support."
        )


@app.on_message(filters.command("authedit") & filters.group)
async def cmd_authedit(client: Client, message: Message):
    """
    Manage authorized users.
    Usage: 
    - /authedit (reply) - Authorize user
    - /authedit remove (reply) - Remove authorization
    - /authedit list - Show all authorized users
    """
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        logger.info(f"📢 /authedit from user {user_id} in chat {chat_id}")
        
        # Check permissions
        is_admin = await anti_edit_manager.is_admin_or_owner(chat_id, user_id)
        
        if not is_admin:
            await message.reply_text(
                "❌ **Permission Denied**\n\n"
                "Only group admins can use this command."
            )
            return
        
        # Parse command
        args = message.text.split()
        action = args[1].lower() if len(args) > 1 else "add"
        
        # List authorized users
        if action == "list":
            authorized = await get_authorized_users(chat_id)
            
            if not authorized:
                await message.reply_text(
                    "📋 **Authorized Users**\n\n"
                    "No users are authorized in this group.\n\n"
                    "**To authorize someone:**\n"
                    "Reply to their message with `/authedit`"
                )
                return
            
            user_list = []
            for idx, auth_user_id in enumerate(authorized, 1):
                try:
                    user = await client.get_users(auth_user_id)
                    name = user.first_name
                    if user.last_name:
                        name += f" {user.last_name}"
                    username = f"@{user.username}" if user.username else "No username"
                    user_list.append(f"{idx}. **{name}**\n   {username}\n   ID: `{auth_user_id}`")
                except:
                    user_list.append(f"{idx}. User ID: `{auth_user_id}`")
            
            await message.reply_text(
                f"📋 **Authorized Users** ({len(authorized)})\n\n"
                + "\n\n".join(user_list) +
                "\n\n✅ These users can edit messages freely."
            )
            return
        
        # Require reply for add/remove
        if not message.reply_to_message:
            await message.reply_text(
                "⚠️ **Please reply to a user's message!**\n\n"
                "**Available commands:**\n"
                "• `/authedit` (reply to user) - Authorize\n"
                "• `/authedit remove` (reply to user) - Remove authorization\n"
                "• `/authedit list` - Show all authorized users\n\n"
                "**Example:**\n"
                "Reply to someone's message and type `/authedit`"
            )
            return
        
        target_user = message.reply_to_message.from_user
        if not target_user:
            await message.reply_text("❌ Cannot identify the user.")
            return
        
        target_user_id = target_user.id
        target_name = target_user.first_name
        target_mention = target_user.mention
        
        # Add authorization
        if action == "add" or action not in ["remove", "list"]:
            already_auth = await is_authorized_user(chat_id, target_user_id)
            
            if already_auth:
                await message.reply_text(
                    f"ℹ️ **Already Authorized**\n\n"
                    f"{target_mention} is already authorized to edit messages.\n\n"
                    f"Use `/authedit remove` (reply to user) to revoke."
                )
                return
            
            success = await add_authorized_user(chat_id, target_user_id)
            
            if success:
                await message.reply_text(
                    f"✅ **Authorization Granted!**\n\n"
                    f"**User:** {target_mention}\n"
                    f"**Name:** {target_name}\n"
                    f"**ID:** `{target_user_id}`\n\n"
                    f"🔓 This user can now edit messages without restriction."
                )
                logger.info(f"✅ User {target_user_id} authorized in chat {chat_id}")
            else:
                await message.reply_text("❌ Failed to authorize user. Try again.")
        
        # Remove authorization
        elif action == "remove":
            is_auth = await is_authorized_user(chat_id, target_user_id)
            
            if not is_auth:
                await message.reply_text(
                    f"ℹ️ **Not Authorized**\n\n"
                    f"{target_mention} is not in the authorized users list."
                )
                return
            
            success = await remove_authorized_user(chat_id, target_user_id)
            
            if success:
                await message.reply_text(
                    f"❌ **Authorization Removed!**\n\n"
                    f"**User:** {target_mention}\n"
                    f"**Name:** {target_name}\n"
                    f"**ID:** `{target_user_id}`\n\n"
                    f"🔒 This user's edits will now be deleted after warning."
                )
                logger.info(f"❌ User {target_user_id} deauthorized in chat {chat_id}")
            else:
                await message.reply_text("❌ Failed to remove authorization. Try again.")
                
    except Exception as e:
        logger.error(f"❌ /authedit command error: {e}", exc_info=True)
        await message.reply_text(
            "❌ **Error occurred!**\n\n"
            "Please try again or contact support."
        )


# ==================== CACHE CLEANUP ====================

async def cleanup_caches():
    """Periodic cache cleanup."""
    while True:
        await asyncio.sleep(cache_expiry)
        try:
            admin_cache.clear()
            current_time = int(datetime.utcnow().timestamp())
            expired = [k for k, (_, t) in message_content_cache.items() if current_time - t > 86400]
            for k in expired:
                message_content_cache.pop(k, None)
            logger.info(f"🧹 Cache cleanup: {len(expired)} messages removed")
        except Exception as e:
            logger.error(f"Cache cleanup error: {e}")

asyncio.create_task(cleanup_caches())

logger.info("=" * 60)
logger.info("✅ ANTI-EDIT PLUGIN LOADED - FINAL PERFECT VERSION")
logger.info("🌐 Multi-Group: ACTIVE | 🎯 Smart Detection: ACTIVE")
logger.info("=" * 60)
