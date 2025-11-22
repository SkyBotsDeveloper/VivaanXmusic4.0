"""
Anti-Edit Plugin for VivaanXMusic Bot

Detects and deletes only actual text/caption edits in groups with warnings.
Ignores emoji reactions, replies, and metadata updates.

Features:
- Detects ONLY text/caption changes (ignores reactions, replies, metadata)
- Stores original message content to verify actual edits
- 1-minute warning before deletion
- Works on messages edited at any time
- Proper authorization system
- Comprehensive logging

Commands:
- /antiedit on/off: Enable/disable anti-edit (Admin/Owner only)
- /authedit: Authorize user to edit (reply to user, Admin/Owner only)
- /authedit remove: Remove edit authorization (reply to user, Admin/Owner only)
- /authedit list: Show all authorized users in the group
"""

import asyncio
import logging
from typing import Optional, Dict, Set
from datetime import datetime
from collections import defaultdict

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import (
    MessageDeleteForbidden,
    UserNotParticipant,
    ChatAdminRequired,
    FloodWait,
    RPCError
)
from pyrogram.enums import ChatMemberStatus, MessageMediaType

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
logger.setLevel(logging.INFO)

# Configuration
EDIT_WARNING_TIME = 60  # Wait 60 seconds (1 minute) before deleting
WARNING_MESSAGE = (
    "⚠️ **Edited Message Detected!**\n\n"
    "❌ Message editing is not allowed in this group.\n\n"
    "⏱️ Your edited message will be deleted in **1 minute**.\n\n"
    "💡 Contact admins if you need edit permission."
)

# In-memory cache for admin status and original messages
admin_cache: Dict[int, Dict[int, tuple[bool, float]]] = {}
ADMIN_CACHE_TTL = 300  # 5 minutes

# Store original message content to detect actual text changes
# Structure: {chat_id: {message_id: {"text": str, "caption": str, "media_type": str}}}
original_messages: Dict[int, Dict[int, Dict[str, Optional[str]]]] = defaultdict(lambda: defaultdict(dict))
MAX_STORED_MESSAGES = 10000  # Limit memory usage


class AntiEditManager:
    """Manages anti-edit functionality across all groups."""
    
    def __init__(self):
        self.pending_deletions: Dict[str, asyncio.Task] = {}
        self.processing_edits: Set[str] = set()
    
    async def is_admin_or_owner(self, chat_id: int, user_id: int) -> bool:
        """
        Check if user is admin or owner of the group.
        Uses caching with TTL to reduce API calls.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
            
        Returns:
            bool: True if user is admin/owner, False otherwise
        """
        # Check if user is bot owner
        if user_id == OWNER_ID:
            return True
        
        # Check cache first
        current_time = datetime.now().timestamp()
        if chat_id in admin_cache and user_id in admin_cache[chat_id]:
            is_admin, cache_time = admin_cache[chat_id][user_id]
            if current_time - cache_time < ADMIN_CACHE_TTL:
                return is_admin
        
        try:
            member = await app.get_chat_member(chat_id, user_id)
            is_admin = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
            
            # Update cache with timestamp
            if chat_id not in admin_cache:
                admin_cache[chat_id] = {}
            admin_cache[chat_id][user_id] = (is_admin, current_time)
            
            return is_admin
            
        except (UserNotParticipant, ChatAdminRequired, RPCError) as e:
            logger.warning(f"Error checking admin status for user {user_id} in chat {chat_id}: {e}")
            return False
    
    def store_original_message(self, message: Message):
        """
        Store original message content to compare later for actual edits.
        
        Args:
            message: Original message object
        """
        chat_id = message.chat.id
        message_id = message.id
        
        # Limit memory usage - implement simple LRU-like behavior
        if len(original_messages[chat_id]) > MAX_STORED_MESSAGES:
            # Remove oldest 10% of messages
            to_remove = len(original_messages[chat_id]) // 10
            for old_msg_id in list(original_messages[chat_id].keys())[:to_remove]:
                del original_messages[chat_id][old_msg_id]
        
        # Store text, caption, and media type
        original_messages[chat_id][message_id] = {
            "text": message.text,
            "caption": message.caption,
            "media_type": str(message.media) if message.media else None,
            "timestamp": datetime.now().timestamp()
        }
    
    def is_actual_text_edit(self, message: Message) -> bool:
        """
        Check if the edit is an actual text/caption change.
        Compares current message with stored original.
        
        Args:
            message: The edited message object
            
        Returns:
            bool: True if text/caption actually changed, False otherwise
        """
        chat_id = message.chat.id
        message_id = message.id
        
        # If we don't have the original message stored, we can't verify
        # In this case, check if there's actual content
        if message_id not in original_messages[chat_id]:
            # If message has text or caption, consider it a real edit
            # (This handles messages sent before bot started)
            has_content = bool(message.text or message.caption)
            logger.debug(
                f"No original stored for message {message_id} in chat {chat_id}. "
                f"Has content: {has_content}"
            )
            return has_content
        
        original = original_messages[chat_id][message_id]
        
        # Compare text content
        original_text = original.get("text")
        current_text = message.text
        
        # Compare caption content
        original_caption = original.get("caption")
        current_caption = message.caption
        
        # Check if text actually changed
        text_changed = original_text != current_text
        caption_changed = original_caption != current_caption
        
        actual_edit = text_changed or caption_changed
        
        if actual_edit:
            logger.info(
                f"Actual edit detected in message {message_id} (chat {chat_id}): "
                f"Text changed: {text_changed}, Caption changed: {caption_changed}"
            )
        else:
            logger.debug(
                f"No text change in message {message_id} (chat {chat_id}) - "
                f"likely reaction or metadata update"
            )
        
        return actual_edit
    
    async def should_delete_edit(self, chat_id: int, user_id: int) -> bool:
        """
        Determine if an edited message should be deleted.
        
        Rules:
        1. If anti-edit is disabled in group → Don't delete
        2. If user is authorized via /authedit → Don't delete
        3. Otherwise → Delete (even if admin/owner)
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
            
        Returns:
            bool: True if message should be deleted, False otherwise
        """
        # Check if anti-edit is enabled in this group
        if not await is_antiedit_enabled(chat_id):
            return False
        
        # Check if user is authorized to edit
        if await is_authorized_user(chat_id, user_id):
            return False
        
        # Delete the edit (even if admin/owner)
        return True
    
    async def handle_edited_message(self, client: Client, message: Message):
        """
        Handle edited message detection and deletion with 1-minute warning.
        Only processes actual text/caption edits.
        
        Args:
            client: Pyrogram client
            message: Edited message object
        """
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        message_id = message.id
        
        # Skip if no user (service messages, etc.)
        if not user_id:
            return
        
        # CRITICAL: Check if this is an actual text/caption edit
        if not self.is_actual_text_edit(message):
            logger.debug(
                f"Ignoring non-text edit for message {message_id} in chat {chat_id} "
                f"(reaction, reply, or metadata update)"
            )
            return
        
        # Create unique identifier for this edit
        edit_key = f"{chat_id}:{message_id}:{user_id}"
        
        # Prevent duplicate processing
        if edit_key in self.processing_edits:
            logger.debug(f"Edit {edit_key} already being processed, skipping")
            return
        
        self.processing_edits.add(edit_key)
        
        try:
            # Check if we should delete this edit
            if not await self.should_delete_edit(chat_id, user_id):
                logger.debug(
                    f"Edit allowed for user {user_id} in chat {chat_id} "
                    f"(authorized or anti-edit disabled)"
                )
                # Update stored message with new content (authorized edit)
                self.store_original_message(message)
                return
            
            # Send warning message
            warning_msg = None
            try:
                warning_msg = await message.reply_text(
                    WARNING_MESSAGE,
                    quote=True
                )
                
                logger.info(
                    f"Text edit detected: User {user_id} edited message {message_id} "
                    f"in chat {chat_id}. Warning sent, deletion in {EDIT_WARNING_TIME}s."
                )
                
                # Wait 1 minute before deletion
                await asyncio.sleep(EDIT_WARNING_TIME)
                
                # Delete the edited message ONLY
                try:
                    await message.delete()
                    logger.info(
                        f"Deleted edited message {message_id} from user {user_id} "
                        f"in chat {chat_id}"
                    )
                    
                    # Remove from storage
                    if message_id in original_messages[chat_id]:
                        del original_messages[chat_id][message_id]
                    
                    # Log the action to database
                    await log_edit_action(
                        chat_id=chat_id,
                        user_id=user_id,
                        message_id=message_id,
                        action="deleted",
                        timestamp=datetime.utcnow()
                    )
                    
                except MessageDeleteForbidden:
                    logger.warning(
                        f"Cannot delete message {message_id} in chat {chat_id} - "
                        f"insufficient permissions"
                    )
                except Exception as e:
                    logger.error(f"Error deleting message {message_id}: {e}")
                
                # Delete warning message after deletion
                if warning_msg:
                    await asyncio.sleep(3)
                    try:
                        await warning_msg.delete()
                    except Exception as e:
                        logger.debug(f"Could not delete warning message: {e}")
                        
            except FloodWait as e:
                logger.warning(f"FloodWait: Sleeping for {e.value} seconds")
                await asyncio.sleep(e.value)
            except Exception as e:
                logger.error(f"Error sending warning message: {e}")
                
        finally:
            # Clean up processing set
            self.processing_edits.discard(edit_key)


# Initialize manager
anti_edit_manager = AntiEditManager()


# ==================== MESSAGE HANDLERS ====================

@app.on_message(
    filters.group & ~filters.bot & ~filters.service & ~filters.edited
)
async def store_new_message(client: Client, message: Message):
    """
    Store original content of new messages for later comparison.
    This allows us to detect actual text edits vs reactions/replies.
    """
    try:
        # Only store if anti-edit might be enabled (check cache or assume yes)
        chat_id = message.chat.id
        
        # Store text and caption content
        anti_edit_manager.store_original_message(message)
        
        logger.debug(
            f"Stored original content for message {message.id} in chat {chat_id}"
        )
        
    except Exception as e:
        logger.error(f"Error storing original message: {e}")


@app.on_edited_message(
    filters.group & ~filters.bot & ~filters.service
)
async def on_message_edited(client: Client, message: Message):
    """
    Handler for all edited messages in groups.
    Triggers anti-edit check and deletion if needed.
    
    Note: This handler now only processes ACTUAL text/caption edits.
    Reactions, replies, and metadata updates are ignored.
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
    """
    Toggle anti-edit feature on/off for the group.
    Usage: /antiedit on | /antiedit off
    Permission: Admin/Owner only
    """
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Check if user is admin or owner
    if not await anti_edit_manager.is_admin_or_owner(chat_id, user_id):
        await message.reply_text(
            "❌ **Permission Denied**\n\n"
            "Only admins and group owner can toggle anti-edit feature."
        )
        return
    
    # Parse command arguments
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        current_status = "✅ Enabled" if await is_antiedit_enabled(chat_id) else "❌ Disabled"
        await message.reply_text(
            f"**Anti-Edit Status:** {current_status}\n\n"
            "**Usage:**\n"
            "• `/antiedit on` - Enable anti-edit\n"
            "• `/antiedit off` - Disable anti-edit\n\n"
            "**Info:**\n"
            "⏱️ Warning time: 1 minute before deletion\n"
            "🔒 Authorized users can edit freely\n"
            "✨ Only detects actual text changes (ignores reactions/replies)"
        )
        return
    
    action = args[1].lower()
    
    if action == "on":
        await enable_antiedit(chat_id)
        await message.reply_text(
            "✅ **Anti-Edit Enabled**\n\n"
            "All edited messages (text changes only) will be deleted after a 1-minute warning, "
            "unless the user is authorized with `/authedit`.\n\n"
            "✨ **Note:** Emoji reactions and replies won't trigger deletion.\n\n"
            "💡 **Tip:** Use `/authedit` (reply to user) to authorize someone to edit messages."
        )
        logger.info(f"Anti-edit enabled in chat {chat_id} by user {user_id}")
        
    elif action == "off":
        await disable_antiedit(chat_id)
        await message.reply_text(
            "❌ **Anti-Edit Disabled**\n\n"
            "Message editing is now allowed for all users."
        )
        logger.info(f"Anti-edit disabled in chat {chat_id} by user {user_id}")
        
    else:
        await message.reply_text(
            "⚠️ **Invalid Option**\n\n"
            "Use `/antiedit on` or `/antiedit off`"
        )


@app.on_message(
    filters.command("authedit") & filters.group
)
async def manage_authorized_users(client: Client, message: Message):
    """
    Manage users authorized to edit messages.
    
    Usage:
    - /authedit (reply to user) - Authorize user
    - /authedit remove (reply to user) - Remove authorization
    - /authedit list - Show all authorized users
    
    Permission: Admin/Owner only
    """
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Check if user is admin or owner
    if not await anti_edit_manager.is_admin_or_owner(chat_id, user_id):
        await message.reply_text(
            "❌ **Permission Denied**\n\n"
            "Only admins and group owner can manage authorized users."
        )
        return
    
    # Parse command
    command_parts = message.text.split(maxsplit=1)
    action = command_parts[1].lower() if len(command_parts) > 1 else "add"
    
    # Handle "list" action
    if action == "list":
        authorized = await get_authorized_users(chat_id)
        
        if not authorized:
            await message.reply_text(
                "📋 **Authorized Users**\n\n"
                "No users are currently authorized to edit messages.\n\n"
                "💡 Reply to a user with `/authedit` to authorize them."
            )
            return
        
        # Format user list
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
            "\n\n✅ These users can edit messages without deletion."
        )
        return
    
    # Require reply for add/remove actions
    if not message.reply_to_message:
        await message.reply_text(
            "⚠️ **Reply Required**\n\n"
            "**How to use:**\n"
            "• Reply to a user's message with `/authedit` - To authorize them\n"
            "• Reply to a user's message with `/authedit remove` - To remove authorization\n"
            "• Use `/authedit list` - To see all authorized users"
        )
        return
    
    target_user = message.reply_to_message.from_user
    if not target_user:
        await message.reply_text("❌ Cannot identify the user from the replied message.")
        return
    
    target_user_id = target_user.id
    target_name = target_user.first_name + (f" {target_user.last_name}" if target_user.last_name else "")
    target_mention = target_user.mention
    
    # Handle "add" action (default when just /authedit)
    if action == "add" or action not in ["remove", "list"]:
        # Check if already authorized
        if await is_authorized_user(chat_id, target_user_id):
            await message.reply_text(
                f"ℹ️ **Already Authorized**\n\n"
                f"{target_mention} is already authorized to edit messages.\n\n"
                f"Use `/authedit remove` (reply to user) to remove authorization."
            )
            return
        
        # Add authorization
        success = await add_authorized_user(chat_id, target_user_id)
        
        if success:
            await message.reply_text(
                f"✅ **Authorization Granted**\n\n"
                f"**User:** {target_mention}\n"
                f"**ID:** `{target_user_id}`\n\n"
                f"🔓 This user can now edit messages without deletion."
            )
            logger.info(f"User {target_user_id} authorized in chat {chat_id} by admin {user_id}")
        else:
            await message.reply_text(
                "❌ **Error**\n\n"
                "Failed to authorize user. Please try again."
            )
    
    # Handle "remove" action
    elif action == "remove":
        # Check if user is authorized
        if not await is_authorized_user(chat_id, target_user_id):
            await message.reply_text(
                f"ℹ️ **Not Authorized**\n\n"
                f"{target_mention} is not in the authorized list."
            )
            return
        
        # Remove authorization
        success = await remove_authorized_user(chat_id, target_user_id)
        
        if success:
            await message.reply_text(
                f"❌ **Authorization Removed**\n\n"
                f"**User:** {target_mention}\n"
                f"**ID:** `{target_user_id}`\n\n"
                f"🔒 This user's edits will now be deleted after warning."
            )
            logger.info(f"User {target_user_id} deauthorized in chat {chat_id} by admin {user_id}")
        else:
            await message.reply_text(
                "❌ **Error**\n\n"
                "Failed to remove authorization. Please try again."
            )
    
    else:
        await message.reply_text(
            "⚠️ **Invalid Action**\n\n"
            "Valid commands:\n"
            "• `/authedit` (reply) - Authorize user\n"
            "• `/authedit remove` (reply) - Remove authorization\n"
            "• `/authedit list` - List authorized users"
        )


# ==================== MAINTENANCE TASKS ====================

async def periodic_cache_cleanup():
    """Clean up expired cache entries and old message storage."""
    while True:
        try:
            await asyncio.sleep(ADMIN_CACHE_TTL)
            
            # Clean admin cache
            current_time = datetime.now().timestamp()
            for chat_id in list(admin_cache.keys()):
                for user_id in list(admin_cache[chat_id].keys()):
                    _, cache_time = admin_cache[chat_id][user_id]
                    if current_time - cache_time > ADMIN_CACHE_TTL:
                        del admin_cache[chat_id][user_id]
                
                # Remove empty chat entries
                if not admin_cache[chat_id]:
                    del admin_cache[chat_id]
            
            # Clean old message storage (messages older than 24 hours)
            current_time = datetime.now().timestamp()
            for chat_id in list(original_messages.keys()):
                for msg_id in list(original_messages[chat_id].keys()):
                    msg_time = original_messages[chat_id][msg_id].get("timestamp", 0)
                    if current_time - msg_time > 86400:  # 24 hours
                        del original_messages[chat_id][msg_id]
                
                # Remove empty chat entries
                if not original_messages[chat_id]:
                    del original_messages[chat_id]
            
            logger.debug("Cache cleanup completed")
            
        except Exception as e:
            logger.error(f"Error in cache cleanup: {e}")


# Start maintenance task
asyncio.create_task(periodic_cache_cleanup())

logger.info("✅ Anti-Edit plugin loaded successfully with text-only edit detection")
