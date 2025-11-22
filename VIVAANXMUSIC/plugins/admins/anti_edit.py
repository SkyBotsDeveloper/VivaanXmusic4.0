"""
Anti-Edit Plugin for VivaanXMusic Bot
Detects and deletes edited messages in groups with warnings.
Only authorized users can edit messages without deletion.

Features:
- Ignores emoji reactions (Telegram's reaction feature)
- 1-minute warning before deletion
- Works on messages edited at any time (even hours later)
- Only deletes the edited message (not replies)
- Proper authorization system

Commands:
- /antiedit on/off: Enable/disable anti-edit (Admin/Owner only)
- /authedit: Authorize user to edit (reply to user, Admin/Owner only)
- /authedit remove: Remove edit authorization (reply to user, Admin/Owner only)
- /authedit list: Show all authorized users in the group
"""

import asyncio
import logging
from typing import Dict, Set
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
EDIT_WARNING_TIME = 60  # Wait 60 seconds (1 minute) before deleting
WARNING_MESSAGE = (
    "⚠️ **Edited Message Detected!**\n\n"
    "❌ Message editing is not allowed in this group.\n\n"
    "⏱️ Your edited message will be deleted in **1 minute**.\n\n"
    "💡 Contact admins if you need edit permission."
)

# In-memory cache for admin status (reduces API calls)
admin_cache: Dict[int, Dict[int, bool]] = {}
cache_expiry = 300  # 5 minutes

# In-memory message content cache to detect reaction-only updates.
# Key: "chat_id:message_id" -> value: normalized content (text/caption or media marker)
message_cache: Dict[str, str] = {}
message_cache_expiry_seconds = 3600  # keep for 1 hour (simple; you can tune as needed)


class AntiEditManager:
    """Manages anti-edit functionality across all groups."""

    def __init__(self):
        self.pending_deletions: Dict[str, asyncio.Task] = {}
        self.processing_edits: Set[str] = set()

    async def is_admin_or_owner(self, chat_id: int, user_id: int) -> bool:
        """
        Check if user is admin or owner of the group.
        Uses caching to reduce API calls.
        """
        # Check if user is bot owner
        if user_id == OWNER_ID:
            return True

        # Check cache first
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

        except (UserNotParticipant, ChatAdminRequired, RPCError) as e:
            logger.warning(f"Error checking admin status for user {user_id} in chat {chat_id}: {e}")
            return False

    def _make_cache_key(self, chat_id: int, message_id: int) -> str:
        return f"{chat_id}:{message_id}"

    def _normalize_message_content(self, message: Message) -> str:
        """
        Produce a normalized string representing the visible content of a message
        (text, caption, or media-type marker). This helps detect if an edit changed
        the visible content or only metadata / reactions.
        """
        if message.text:
            return f"text:{message.text}"
        if message.caption:
            return f"caption:{message.caption}"
        # For media-only messages (photos, stickers, voice, etc.), include media type
        if message.media:
            try:
                mt = message.media.value
            except Exception:
                mt = str(type(message.media))
            return f"media:{mt}"
        return "empty"

    def is_reaction_update(self, message: Message) -> bool:
        """
        Check if the update is just an emoji reaction (not a text edit).
        Uses the message cache: if the previous content equals the current content,
        we treat it as a reaction/metadata-only change and skip deletion.
        """
        # If message has no text/caption and no media change, it's likely just metadata
        if not message.text and not message.caption and not message.media:
            return True

        # If we have the original content cached, compare it to current content.
        key = self._make_cache_key(message.chat.id, message.id)
        current_content = self._normalize_message_content(message)
        previous_content = message_cache.get(key)

        if previous_content is not None:
            if previous_content == current_content:
                # Nothing visible changed — likely reactions/other metadata changed
                return True

        # If there's no previous cached content, try the time-diff heuristic.
        if message.edit_date and message.date:
            time_diff = abs((message.edit_date - message.date).total_seconds())
            if time_diff < 1:
                return True

        return False

    async def should_delete_edit(self, chat_id: int, user_id: int) -> bool:
        """
        Determine if an edited message should be deleted.

        Rules:
        1. If anti-edit is disabled in group → Don't delete
        2. If user is authorized via /authedit → Don't delete
        3. Otherwise → Delete (even if admin/owner)
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
        """
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        message_id = message.id

        # Skip if no user (service messages, etc.)
        if not user_id:
            return

        # Create unique identifier for this edit
        edit_key = f"{chat_id}:{message_id}:{user_id}"

        # Prevent duplicate processing
        if edit_key in self.processing_edits:
            return

        self.processing_edits.add(edit_key)

        try:
            # Skip if it's just a reaction or metadata update (not actual text edit)
            if self.is_reaction_update(message):
                logger.debug(f"Skipping reaction/metadata update in chat {chat_id} for message {message_id}")
                # Update cache to current content so future edits will be compared correctly
                try:
                    key = self._make_cache_key(chat_id, message_id)
                    message_cache[key] = self._normalize_message_content(message)
                except Exception:
                    pass
                return

            # Check if we should delete this edit
            if not await self.should_delete_edit(chat_id, user_id):
                # If we are not deleting, update cached content so subsequent edits compare correctly
                try:
                    key = self._make_cache_key(chat_id, message_id)
                    message_cache[key] = self._normalize_message_content(message)
                except Exception:
                    pass
                return

            # Send warning message
            warning_msg = None
            try:
                warning_msg = await message.reply_text(
                    WARNING_MESSAGE,
                    quote=True
                )

                logger.info(
                    f"Edit detected: User {user_id} edited message {message_id} in chat {chat_id}. "
                    f"Warning sent, deletion in {EDIT_WARNING_TIME} seconds."
                )

                # Wait 1 minute before deletion
                await asyncio.sleep(EDIT_WARNING_TIME)

                # Delete the edited message ONLY (not the warning or any replies)
                try:
                    await message.delete()
                    logger.info(f"Deleted edited message {message_id} from user {user_id} in chat {chat_id}")

                    # Log the action to database
                    await log_edit_action(
                        chat_id=chat_id,
                        user_id=user_id,
                        message_id=message_id,
                        action="deleted",
                        timestamp=datetime.utcnow()
                    )

                    # Also remove from cache (no longer exists)
                    try:
                        key = self._make_cache_key(chat_id, message_id)
                        if key in message_cache:
                            del message_cache[key]
                    except Exception:
                        pass

                except MessageDeleteForbidden:
                    logger.warning(
                        f"Cannot delete message {message_id} in chat {chat_id} - insufficient permissions"
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


# ==================== MESSAGE CREATE HANDLER (cache new messages) ====================
@app.on_message(
    filters.group & ~filters.bot & ~filters.service
)
async def cache_new_message(client: Client, message: Message):
    """
    Cache message content when a new message is posted. This allows us to compare
    original content to edited content and detect reaction/metadata-only updates.
    """
    try:
        key = f"{message.chat.id}:{message.id}"
        # Normalize content (text/caption/media marker)
        if message.text:
            content = f"text:{message.text}"
        elif message.caption:
            content = f"caption:{message.caption}"
        elif message.media:
            try:
                mt = message.media.value
            except Exception:
                mt = str(type(message.media))
            content = f"media:{mt}"
        else:
            content = "empty"
        message_cache[key] = content
    except Exception as e:
        logger.debug(f"Failed to cache message {message.id} in chat {message.chat.id}: {e}")


# ==================== MESSAGE EDIT HANDLER ====================
@app.on_edited_message(
    filters.group & ~filters.bot & ~filters.service
)
async def on_message_edited(client: Client, message: Message):
    """
    Handler for all edited messages in groups.
    Triggers anti-edit check and deletion if needed.

    Note: This handler ignores:
    - Bot messages
    - Service messages (user joined, etc.)
    - Emoji reactions (detected via is_reaction_update)
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
            "🔒 Authorized users can edit freely"
        )
        return

    action = args[1].lower()

    if action == "on":
        await enable_antiedit(chat_id)
        await message.reply_text(
            "✅ **Anti-Edit Enabled**\n\n"
            "All edited messages will be deleted after a 1-minute warning, "
            "unless the user is authorized with `/authedit`.\n\n"
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


# ==================== CACHE CLEANUP ====================
async def clear_admin_cache_periodically():
    """Clear admin cache every 5 minutes to ensure fresh data."""
    while True:
        await asyncio.sleep(cache_expiry)
        admin_cache.clear()
        logger.debug("Admin cache cleared")


# Start cache cleanup task
asyncio.create_task(clear_admin_cache_periodically())

logger.info("Anti-Edit plugin loaded successfully with 1-minute warning system")
