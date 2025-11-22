"""
Anti-Edit Message Detection Plugin — Ultimate Version
VivaanXMusic 4.0+

Features:
- Detects and deletes only *real* edited messages (not replies, bot messages, or reactions)
- Admin/owner protection is *optional* (edit exemption can be toggled)
- Replies to edited messages only, not for reactions/quote/system/service
- Full command set: /edit enable/disable, /antiedit [settings]
- Fixed: will not falsely warn for system messages or replies
"""

import asyncio
import logging
from typing import Optional, Dict
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import MessageDeleteForbidden, UserNotParticipant, FloodWait
from config import OWNER_ID, EDIT_DELETE_TIME, EDIT_WARNING_MESSAGE

from VIVAANXMUSIC import app
try:
    from VIVAANXMUSIC.mongo.edit_tracker_db import edit_tracker_db
except ImportError:
    edit_tracker_db = None

logger = logging.getLogger(__name__)

class AntiEditManager:
    def __init__(self):
        self.pending_tasks: Dict[str, asyncio.Task] = {}

    async def is_admin_or_owner(self, chat_id: int, user_id: int) -> bool:
        # Always allow OWNER_ID (useful for testing/owner override)
        if user_id == OWNER_ID:
            return True
        try:
            member = await app.get_chat_member(chat_id, user_id)
            status = str(getattr(member, "status", "")).lower()
            return status in ("administrator", "creator")
        except FloodWait as fe:
            await asyncio.sleep(fe.value)
            return await self.is_admin_or_owner(chat_id, user_id)
        except UserNotParticipant:
            return False
        except Exception as e:
            logger.error(f"[AntiEdit] Error checking admin: {e}")
            return False

    async def should_delete_edit(self, chat_id: int, user_id: int) -> bool:
        if not edit_tracker_db:
            return False
        config = await edit_tracker_db.get_config(chat_id)
        if not config.get("enabled", True):
            return False
        # Respect exemption only if config is enabled
        if config.get("exclude_admins", False):
            if await self.is_admin_or_owner(chat_id, user_id):
                return False
        return True

    async def send_warning(self, chat_id: int, message_id: int, warning_time: int) -> Optional[Message]:
        try:
            return await app.send_message(
                chat_id,
                EDIT_WARNING_MESSAGE.format(time=warning_time),
                reply_to_message_id=message_id
            )
        except Exception as e:
            logger.error(f"[AntiEdit] Error sending warning: {e}")
            return None

    async def schedule_deletion(self, chat_id: int, message_id: int, warn_id: Optional[int], delete_after_seconds: int):
        key = f"{chat_id}_{message_id}"
        if key in self.pending_tasks:
            self.pending_tasks[key].cancel()
        async def delete_task():
            try:
                await asyncio.sleep(delete_after_seconds)
                try:
                    await app.delete_messages(chat_id, message_id)
                except Exception as e:
                    logger.warning(f"[AntiEdit] Error deleting edit: {e}")
                if warn_id:
                    try:
                        await app.delete_messages(chat_id, warn_id)
                    except:
                        pass
            except asyncio.CancelledError:
                pass
            finally:
                if key in self.pending_tasks:
                    del self.pending_tasks[key]
        self.pending_tasks[key] = asyncio.create_task(delete_task())

    async def log_edit(self, chat_id: int, user_id: int, message_id: int, text: str):
        try:
            if edit_tracker_db:
                await edit_tracker_db.log_edit(
                    chat_id=chat_id,
                    user_id=user_id,
                    message_id=message_id,
                    original_text=text,
                    edited_text=text  # log both for now
                )
        except Exception as e:
            logger.error(f"[AntiEdit] Error logging edit: {e}")

anti_edit_manager = AntiEditManager()

def is_real_edit(message: Message) -> bool:
    # Ignore edits by bots, replies, service messages, forwards, etc.
    if not message or not message.from_user:
        return False
    has_content = bool(message.text or message.caption)
    # Detect "real edits" — not reply, not forward, not via-bot, not service, not reactions/quote
    if (
        not has_content
        or getattr(message, "reply_to_message", None)
        or getattr(message, "service", False)
        or getattr(message, "forward_from", None)
        or getattr(message, "forward_from_chat", None)
        or getattr(message, "via_bot", None)
        or getattr(message, "media_group_id", None)  # ignore album
        or message.from_user.is_bot
    ):
        return False
    return True

@app.on_edited_message(filters.group)
async def handle_edited_message(client: Client, message: Message):
    if not is_real_edit(message):
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    should_delete = await anti_edit_manager.should_delete_edit(chat_id, user_id)
    if not should_delete:
        return
    config = await edit_tracker_db.get_config(chat_id)
    warning_time = config.get("warning_time", EDIT_DELETE_TIME)
    text = message.text or message.caption or "[non-text content]"
    await anti_edit_manager.log_edit(chat_id, user_id, message.id, text[:300])
    warning_msg = await anti_edit_manager.send_warning(chat_id, message.id, warning_time)
    warn_id = warning_msg.id if warning_msg else None
    await anti_edit_manager.schedule_deletion(chat_id, message.id, warn_id, warning_time)

@app.on_message(filters.command("edit") & filters.group)
async def edit_toggle_command(client: Client, message: Message):
    is_admin = await anti_edit_manager.is_admin_or_owner(message.chat.id, message.from_user.id)
    if not is_admin:
        return await message.reply_text("❌ **Admin only**", quote=True)
    if not edit_tracker_db:
        return await message.reply_text("❌ **Database not initialized**")
    parts = message.text.split()
    if len(parts) < 2:
        config = await edit_tracker_db.get_config(message.chat.id)
        status = config.get("enabled", True)
        return await message.reply_text(f"Anti-edit is **{'✅ enabled' if status else '❌ disabled'}**.")
    command = parts[1].lower()
    if command == "enable":
        await edit_tracker_db.toggle_enabled(message.chat.id, True)
        await message.reply_text("✅ **Anti-edit enabled**. Edited messages will be deleted.")
    elif command == "disable":
        await edit_tracker_db.toggle_enabled(message.chat.id, False)
        await message.reply_text("❌ **Anti-edit disabled**. Edited messages will NOT be deleted.")
    else:
        await message.reply_text("**Usage:** `/edit enable` or `/edit disable`")

@app.on_message(filters.command("antiedit") & filters.group)
async def antiedit_command(client: Client, message: Message):
    is_admin = await anti_edit_manager.is_admin_or_owner(message.chat.id, message.from_user.id)
    if not is_admin:
        return await message.reply_text("❌ **Admin only**", quote=True)
    if not edit_tracker_db:
        return await message.reply_text("❌ **Database not initialized**")
    parts = message.text.split()
    config = await edit_tracker_db.get_config(message.chat.id)
    if len(parts) == 1:
        await message.reply_text(
            f"🔍 **Anti-Edit Status**\n\n"
            f"**Enabled:** {'✅ Yes' if config.get('enabled') else '❌ No'}\n"
            f"**Warning Time:** {config.get('warning_time', 60)}s\n"
            f"**Exclude Admins:** {'✅ Yes' if config.get('exclude_admins', False) else '❌ No'}\n"
        )
        return
    command = parts[1].lower()
    if command == "enable":
        await edit_tracker_db.toggle_enabled(message.chat.id, True)
        await message.reply_text("✅ **Anti-edit enabled**")
    elif command == "disable":
        await edit_tracker_db.toggle_enabled(message.chat.id, False)
        await message.reply_text("❌ **Anti-edit disabled**")
    elif command == "time":
        if len(parts) < 3:
            return await message.reply_text("❌ **Usage:** `/antiedit time [seconds]`")
        try:
            seconds = int(parts[2])
            if not (10 <= seconds <= 300):
                return await message.reply_text("❌ **Range:** 10-300 seconds")
            await edit_tracker_db.set_warning_time(message.chat.id, seconds)
            await message.reply_text(f"✅ **Warning time: {seconds}s**")
        except ValueError:
            return await message.reply_text("❌ **Invalid number**")
    elif command == "admins":
        if len(parts) < 3:
            return await message.reply_text("❌ **Usage:** `/antiedit admins yes/no`")
        exempt = parts[2].lower().startswith("y")
        await edit_tracker_db.set_admin_exemption(message.chat.id, exempt)
        await message.reply_text(f"✅ Admins are {'exempt' if exempt else 'not exempt'}")
    else:
        await message.reply_text(
            "**Commands:**\n"
            "`/antiedit` - Show status\n"
            "`/antiedit enable/disable` - Enable/Disable system\n"
            "`/antiedit time [sec]` - Set delete time (10-300s)\n"
            "`/antiedit admins yes/no` - Exempt/expose admins"
        )

@app.on_message(filters.command("antiedit_stats") & filters.group)
async def antiedit_stats_command(client: Client, message: Message):
    is_admin = await anti_edit_manager.is_admin_or_owner(message.chat.id, message.from_user.id)
    if not is_admin:
        return await message.reply_text("❌ **Admin only**")
    if not edit_tracker_db:
        return await message.reply_text("❌ **Database not initialized**")
    stats = await edit_tracker_db.get_stats(message.chat.id)
    await message.reply_text(
        f"📊 **Statistics**\n\n"
        f"**Pending:** {stats.get('pending_deletions', 0)}\n"
        f"**Completed:** {stats.get('completed_deletions', 0)}\n"
        f"**Total Edits:** {stats.get('total_edits_logged', 0)}\n"
    )

__all__ = [
    "handle_edited_message",
    "edit_toggle_command",
    "antiedit_command",
    "antiedit_stats_command",
    "AntiEditManager"
]
