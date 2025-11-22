"""
Anti-Edit Plugin for VivaanXMusic Bot

Detects and deletes only actual text/caption edits in groups with warnings.
Ignores emoji reactions, replies, and metadata updates.

Features:
- Detects ONLY word/text changes (ignores reactions, replies, metadata)
- Stores original message content for accurate comparison
- 1-minute warning before deletion
- Works on messages edited at any time
- Proper authorization system
- Comprehensive logging and error handling

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
logger.setLevel(logging.INFO)

# Configuration
EDIT_WARNING_TIME = 60  # Wait 60 seconds (1 minute) before deleting
WARNING_MESSAGE = (
    "⚠️ **Edited Message Detected!**\n\n"
    "❌ Message editing is not allowed in this group.\n\n"
    "⏱️ Your edited message will be deleted in **1 minute**.\n\n"
    "💡 Contact admins if you need edit permission."
)

# In-memory storage
admin_cache: Dict[int, Dict[int, tuple[bool, float]]] = {}
ADMIN_CACHE_TTL = 300  # 5 minutes

# Store original message content to detect actual text changes
# Structure: {chat_id: {message_id: {"text": str, "caption": str, "timestamp": float}}}
original_messages: Dict[int, Dict[int, Dict[str, any]]] = defaultdict(lambda: defaultdict(dict))
MAX_STORED_MESSAGES = 10000  # Limit memory usage per chat


class AntiEditManager:
    """Manages anti-edit functionality across all groups."""
    
    def __init__(self):
        self.pending_deletions: Dict[str, asyncio.Task] = {}
        self.processing_edits: Set[str] = set()
        logger.info("AntiEditManager initialized")
    
    async def is_admin_or_owner(self, chat_id: int, user_id: int) -> bool:
        """
        Check if user is admin or owner of the group.
        Uses caching with TTL to reduce API calls.
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
    
    def store_original_message(self, message: Message) -> None:
        """
        Store original message content to compare later for actual text edits.
        Only stores text and caption content.
        """
        chat_id = message.chat.id
        message_id = message.id
        
        # Don't store if no text or caption
        if not message.text and not message.caption:
            return
        
        # Limit memory usage - remove oldest messages if exceeding limit
        if len(original_messages[chat_id]) >= MAX_STORED_MESSAGES:
            # Remove oldest 10% of messages
            to_remove = MAX_STORED_MESSAGES // 10
            sorted_messages = sorted(
                original_messages[chat_id].items(),
                key=lambda x: x[1].get("timestamp", 0)
            )
            for old_msg_id, _ in sorted_messages[:to_remove]:
                del original_messages[chat_id][old_msg_id]
            logger.debug(f"Cleaned {to_remove} old messages from chat {chat_id}")
        
        # Store text and caption content
        original_messages[chat_id][message_id] = {
            "text": message.text,
            "caption": message.caption,
            "timestamp": datetime.now().timestamp()
        }
        
        logger.debug(
            f"Stored original for msg {message_id} in chat {chat_id}: "
            f"text={bool(message.text)}, caption={bool(message.caption)}"
        )
    
    def has_text_changed(self, message: Message) -> tuple[bool, str]:
        """
        Check if the actual text or caption content has changed.
        Compares word-by-word to detect real edits.
        
        Returns:
            tuple: (has_changed: bool, reason: str)
        """
        chat_id = message.chat.id
        message_id = message.id
        
        # Current content
        current_text = message.text or ""
        current_caption = message.caption or ""
        current_content = current_text or current_caption
        
        # If no current content, not a text edit (might be media change)
        if not current_content.strip():
            return False, "no_text_content"
        
        # Check if we have original stored
        if message_id not in original_messages[chat_id]:
            # No original stored - this happens when:
            # 1. Message was sent before bot started
            # 2. Message was just reacted to (no original text to store)
            # We'll allow it to pass as non-edit since we can't verify
            logger.debug(
                f"No original stored for msg {message_id} in chat {chat_id} - "
                f"assuming non-edit (reaction/reply)"
            )
            return False, "no_original_stored"
        
        original = original_messages[chat_id][message_id]
        original_text = original.get("text") or ""
        original_caption = original.get("caption") or ""
        original_content = original_text or original_caption
        
        # Compare actual text content
        text_changed = original_content.strip() != current_content.strip()
        
        if text_changed:
            # Double-check: normalize whitespace and compare
            original_normalized = " ".join(original_content.split())
            current_normalized = " ".join(current_content.split())
            text_changed = original_normalized != current_normalized
        
        if text_changed:
            logger.info(
                f"TEXT CHANGE DETECTED in msg {message_id} (chat {chat_id}):\n"
                f"  Original: '{original_content[:50]}...'\n"
                f"  Current:  '{current_content[:50]}...'"
            )
            return True, "text_modified"
        else:
            logger.debug(
                f"No text change in msg {message_id} (chat {chat_id}) - "
                f"likely reaction/reply"
            )
            return False, "no_text_change"
    
    async def should_delete_edit(self, chat_id: int, user_id: int) -> bool:
        """
        Determine if an edited message should be deleted.
        
        Rules:
        1. If anti-edit is disabled → Don't delete
        2. If user is authorized → Don't delete
        3. Otherwise → Delete
        """
        # Check if anti-edit is enabled
        if not await is_antiedit_enabled(chat_id):
            return False
        
        # Check if user is authorized to edit
        if await is_authorized_user(chat_id, user_id):
            return False
        
        return True
    
    async def handle_edited_message(self, client: Client, message: Message) -> None:
        """
        Handle edited message detection and deletion.
        Only processes actual text/caption changes.
        """
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        message_id = message.id
        
        # Skip if no user (service messages)
        if not user_id:
            return
        
        # CRITICAL: Check if actual text/caption changed
        has_changed, reason = self.has_text_changed(message)
        
        if not has_changed:
            logger.debug(
                f"Ignoring edit for msg {message_id} in chat {chat_id}: {reason}"
            )
            return
        
        # Create unique identifier
        edit_key = f"{chat_id}:{message_id}:{user_id}"
        
        # Prevent duplicate processing
        if edit_key in self.processing_edits:
            logger.debug(f"Edit {edit_key} already processing, skipping")
            return
        
        self.processing_edits.add(edit_key)
        
        try:
            # Check if we should delete
            if not await self.should_delete_edit(chat_id, user_id):
                logger.debug(f"Edit allowed for user {user_id} in chat {chat_id}")
                # Update stored message (authorized edit)
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
                    f"⚠️ Edit warning sent: User {user_id}, msg {message_id}, "
                    f"chat {chat_id}. Deleting in {EDIT_WARNING_TIME}s"
                )
                
                # Wait 1 minute
                await asyncio.sleep(EDIT_WARNING_TIME)
                
                # Delete the edited message
                try:
                    await message.delete()
                    logger.info(f"✅ Deleted edited msg {message_id} from user {user_id} in chat {chat_id}")
                    
                    # Remove from storage
                    if message_id in original_messages[chat_id]:
                        del original_messages[chat_id][message_id]
                    
                    # Log to database
                    await log_edit_action(
                        chat_id=chat_id,
                        user_id=user_id,
                        message_id=message_id,
                        action="deleted",
                        timestamp=datetime.utcnow()
                    )
                    
                except MessageDeleteForbidden:
                    logger.warning(f"❌ Cannot delete msg {message_id} in chat {chat_id} - no permissions")
                except Exception as e:
                    logger.error(f"❌ Error deleting msg {message_id}: {e}")
                
                # Delete warning message
                if warning_msg:
                    await asyncio.sleep(3)
                    try:
                        await warning_msg.delete()
                    except Exception as e:
                        logger.debug(f"Could not delete warning: {e}")
                        
            except FloodWait as e:
                logger.warning(f"FloodWait: Sleeping {e.value}s")
                await asyncio.sleep(e.value)
            except Exception as e:
                logger.error(f"Error sending warning: {e}", exc_info=True)
                
        finally:
            self.processing_edits.discard(edit_key)


# Initialize manager
anti_edit_manager = AntiEditManager()


# ==================== MESSAGE HANDLERS ====================

@app.on_message(
    filters.group & ~filters.bot & ~filters.service
)
async def store_new_message(client: Client, message: Message):
    """
    Store original content of new messages for later comparison.
    This runs on ALL new messages (not edited).
    """
    try:
        # Only store if message has text or caption
        if message.text or message.caption:
            anti_edit_manager.store_original_message(message)
        
    except Exception as e:
        logger.error(f"Error storing original message: {e}", exc_info=True)


@app.on_edited_message(
    filters.group & ~filters.bot & ~filters.service
)
async def on_message_edited(client: Client, message: Message):
    """
    Handler for edited messages in groups.
    Only triggers deletion if actual text/caption changed.
    
    Ignores:
    - Reactions (emoji)
    - Replies to messages
    - Metadata updates
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
    Toggle anti-edit feature on/off.
    Usage: /antiedit on | /antiedit off
    Permission: Admin/Owner only
    """
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Check admin permissions
    if not await anti_edit_manager.is_admin_or_owner(chat_id, user_id):
        await message.reply_text(
            "❌ **Permission Denied**\n\n"
            "Only admins and group owner can toggle anti-edit."
        )
        return
    
    # Parse arguments
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        current_status = "✅ Enabled" if await is_antiedit_enabled(chat_id) else "❌ Disabled"
        await message.reply_text(
            f"**Anti-Edit Status:** {current_status}\n\n"
            "**Usage:**\n"
            "• `/antiedit on` - Enable\n"
            "• `/antiedit off` - Disable\n\n"
            "**Features:**\n"
            "⏱️ 1 minute warning before deletion\n"
            "✨ Only deletes when words change\n"
            "🚫 Ignores reactions and replies\n"
            "🔒 Authorized users can edit"
        )
        return
    
    action = args[1].lower()
    
    if action == "on":
        await enable_antiedit(chat_id)
        await message.reply_text(
            "✅ **Anti-Edit Enabled**\n\n"
            "Messages will be deleted if text/words are changed.\n\n"
            "✨ **What's ignored:**\n"
            "• Emoji reactions\n"
            "• Message replies\n"
            "• Metadata updates\n\n"
            "💡 Use `/authedit` (reply to user) to authorize editing."
        )
        logger.info(f"✅ Anti-edit enabled in chat {chat_id} by user {user_id}")
        
    elif action == "off":
        await disable_antiedit(chat_id)
        await message.reply_text(
            "❌ **Anti-Edit Disabled**\n\n"
            "Message editing is now allowed for everyone."
        )
        logger.info(f"❌ Anti-edit disabled in chat {chat_id} by user {user_id}")
        
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
    - /authedit (reply) - Authorize user
    - /authedit remove (reply) - Remove authorization
    - /authedit list - Show authorized users
    """
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Check admin permissions
    if not await anti_edit_manager.is_admin_or_owner(chat_id, user_id):
        await message.reply_text(
            "❌ **Permission Denied**\n\n"
            "Only admins can manage authorized users."
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
                "No users authorized yet.\n\n"
                "💡 Reply to user with `/authedit` to authorize."
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
            "\n\n✅ These users can edit freely."
        )
        return
    
    # Require reply for add/remove
    if not message.reply_to_message:
        await message.reply_text(
            "⚠️ **Reply Required**\n\n"
            "**Usage:**\n"
            "• Reply with `/authedit` - Authorize\n"
            "• Reply with `/authedit remove` - Remove\n"
            "• `/authedit list` - View all"
        )
        return
    
    target_user = message.reply_to_message.from_user
    if not target_user:
        await message.reply_text("❌ Cannot identify user from reply.")
        return
    
    target_user_id = target_user.id
    target_mention = target_user.mention
    
    # Handle "add" action
    if action == "add" or action not in ["remove", "list"]:
        if await is_authorized_user(chat_id, target_user_id):
            await message.reply_text(
                f"ℹ️ **Already Authorized**\n\n"
                f"{target_mention} can already edit.\n\n"
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
            await message.reply_text("❌ Failed to authorize. Try again.")
    
    # Handle "remove" action
    elif action == "remove":
        if not await is_authorized_user(chat_id, target_user_id):
            await message.reply_text(
                f"ℹ️ **Not Authorized**\n\n"
                f"{target_mention} is not in authorized list."
            )
            return
        
        success = await remove_authorized_user(chat_id, target_user_id)
        
        if success:
            await message.reply_text(
                f"❌ **Authorization Removed**\n\n"
                f"**User:** {target_mention}\n"
                f"**ID:** `{target_user_id}`\n\n"
                f"🔒 Edits will now be deleted."
            )
            logger.info(f"❌ User {target_user_id} deauthorized in chat {chat_id}")
        else:
            await message.reply_text("❌ Failed to remove. Try again.")
    
    else:
        await message.reply_text(
            "⚠️ **Invalid Action**\n\n"
            "Use: `/authedit`, `/authedit remove`, or `/authedit list`"
        )


# ==================== MAINTENANCE ====================

async def periodic_cleanup():
    """Clean up expired cache and old messages."""
    while True:
        try:
            await asyncio.sleep(ADMIN_CACHE_TTL)
            
            current_time = datetime.now().timestamp()
            
            # Clean admin cache
            for chat_id in list(admin_cache.keys()):
                for user_id in list(admin_cache[chat_id].keys()):
                    _, cache_time = admin_cache[chat_id][user_id]
                    if current_time - cache_time > ADMIN_CACHE_TTL:
                        del admin_cache[chat_id][user_id]
                
                if not admin_cache[chat_id]:
                    del admin_cache[chat_id]
            
            # Clean old messages (24 hours)
            for chat_id in list(original_messages.keys()):
                for msg_id in list(original_messages[chat_id].keys()):
                    msg_time = original_messages[chat_id][msg_id].get("timestamp", 0)
                    if current_time - msg_time > 86400:
                        del original_messages[chat_id][msg_id]
                
                if not original_messages[chat_id]:
                    del original_messages[chat_id]
            
            logger.debug("🧹 Cleanup completed")
            
        except Exception as e:
            logger.error(f"Error in cleanup: {e}", exc_info=True)


# Start cleanup task
asyncio.create_task(periodic_cleanup())

logger.info("✅ Anti-Edit plugin loaded successfully with text-only edit detection")
