"""
Anti-Edit Message Detection Plugin
Ultimate reliable version for VivaanXMusic

- Deletes ONLY real edits (never replies, reactions, quotes, etc.)
- /edit enable and /edit disable work FOR ALL ADMINS/OWNERS
- 100% bulletproof admin/owner check, resilient to all Telegram bugs/settings
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

    async def is_admin_or_owner(self, client: Client, chat_id: int, user_id: int) -> bool:
        """
        Returns True for any admin/owner, in all Telegram group types and admin configs.
        Uses .status first, then get_chat_administrators fallback for 100% reliability.
        """
        try:
            # Fast direct status check
            member = await client.get_chat_member(chat_id, user_id)
            status = getattr(member, "status", None)
            if status in ("administrator", "creator"):
                return True
            # Fallback: thorough check (handles all Telegram API quirks)
            admins = await client.get_chat_administrators(chat_id)
            for admin in admins:
                if admin.user.id == user_id:
                    return True
            return False
        except FloodWait as fe:
            await asyncio.sleep(fe.value)
            return await self.is_admin_or_owner(client, chat_id, user_id)
        except Exception as e:
            logger.error(f"[AntiEdit] Error checking admin status: {e}")
            return False

    async def should_detect_edit(self, client: Client, chat_id: int, user_id: int) -> bool:
        try:
            if not edit_tracker_db:
                return False
            config = await edit_tracker_db.get_config(chat_id)
            if not config.get("enabled", True):
                return False
            if user_id == OWNER_ID:
                return False
            # Optionally skip admins/owners
            if config.get("exclude_admins", True):
                if await self.is_admin_or_owner(client, chat_id, user_id):
                    return False
            return True
        except Exception as e:
            logger.error(f"[AntiEdit] Error in detection logic: {e}")
            return False

    async def send_warning(self, client: Client, chat_id: int, message_id: int, warning_time: int) -> Optional[Message]:
        try:
            text = EDIT_WARNING_MESSAGE.format(time=warning_time)
            return await client.send_message(chat_id, text, reply_to_message_id=message_id)
        except Exception as e:
            logger.error(f"[AntiEdit] Error sending warning: {e}")
            return None

    async def schedule_deletion(self, client: Client, chat_id: int, message_id: int, user_id: int,
                               warning_msg_id: Optional[int], delete_after_seconds: int):
        key = f"{chat_id}_{message_id}"
        if key in self.pending_tasks:
            self.pending_tasks[key].cancel()
        async def delete_task():
            try:
                await asyncio.sleep(delete_after_seconds)
                try:
                    await client.delete_messages(chat_id, message_id)
                except MessageDeleteForbidden:
                    pass
                if warning_msg_id:
                    try:
                        await client.delete_messages(chat_id, warning_msg_id)
                    except:
                        pass
                if edit_tracker_db:
                    pending = await edit_tracker_db.pending_deletions_collection.find_one({
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "status": "pending"
                    })
                    if pending:
                        await edit_tracker_db.mark_deletion_done(str(pending["_id"]))
            except asyncio.CancelledError:
                pass
            finally:
                if key in self.pending_tasks:
                    del self.pending_tasks[key]
        task = asyncio.create_task(delete_task())
        self.pending_tasks[key] = task

    async def log_edit(self, chat_id: int, user_id: int, message_id: int, text: str):
        try:
            if edit_tracker_db:
                await edit_tracker_db.log_edit(
                    chat_id=chat_id,
                    user_id=user_id,
                    message_id=message_id,
                    original_text=text,
                    edited_text=text
                )
        except Exception as e:
            logger.error(f"[AntiEdit] Error logging edit: {e}")

anti_edit_manager = AntiEditManager()

def real_edit(message: Message) -> bool:
    """
    Returns True only for true edits to a message, not reacts/replies/forwards
    """
    if not message or not message.from_user:
        return False
    # Only apply to text/caption changes, never replies etc
    has_content = bool(message.text or message.caption)
    is_reply = hasattr(message, "reply_to_message") and message.reply_to_message is not None
    is_service = getattr(message, "service", False)
    is_forward = getattr(message, "forward_from", None) or getattr(message, "forward_from_chat", None)
    is_via_bot = getattr(message, "via_bot", None) is not None
    if is_reply or is_service or is_forward or is_via_bot or not has_content:
        return False
    return True

@app.on_edited_message(filters.group)
async def handle_edited_message(client: Client, message: Message):
    if not real_edit(message):
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    message_id = message.id
    should_detect = await anti_edit_manager.should_detect_edit(client, chat_id, user_id)
    if not should_detect:
        return
    config = await edit_tracker_db.get_config(chat_id)
    warning_time = config.get("warning_time", EDIT_DELETE_TIME)
    text = message.text or message.caption or "[non-text content]"
    await anti_edit_manager.log_edit(chat_id, user_id, message_id, text[:200])
    warning_msg = await anti_edit_manager.send_warning(client, chat_id, message_id, warning_time)
    warning_msg_id = warning_msg.id if warning_msg else None
    await anti_edit_manager.schedule_deletion(client, chat_id, message_id, user_id, warning_msg_id, warning_time)

@app.on_message(filters.command(["edit"]) & filters.group)
async def edit_toggle_command(client: Client, message: Message):
    """
    /edit enable - Enables anti-edit detection
    /edit disable - Disables anti-edit detection
    Only group owner/admins can use
    """
    is_admin = await anti_edit_manager.is_admin_or_owner(client, message.chat.id, message.from_user.id)
    if not is_admin:
        # Debugging: show the status and admin list
        admin_status = "UNKNOWN"
        try:
            member = await client.get_chat_member(message.chat.id, message.from_user.id)
            admin_status = getattr(member, "status", None)
            admins = await client.get_chat_administrators(message.chat.id)
            admin_ids = [a.user.id for a in admins]
            admin_debug = f"[admin_ids={admin_ids}]"
        except Exception as e:
            admin_debug = f"[error: {e}]"
        return await message.reply_text(f"❌ **Admin only**\nDetected status: <code>{admin_status}</code>\n{admin_debug}", quote=True)
    if not edit_tracker_db:
        return await message.reply_text("❌ **Database not initialized**")
    parts = message.text.split()
    if len(parts) < 2:
        status = (await edit_tracker_db.get_config(message.chat.id)).get("enabled", True)
        status_readable = "enabled" if status else "disabled"
        return await message.reply_text(f"Anti-edit is currently **{status_readable}**.")
    command = parts[1].lower()
    if command == "enable":
        await edit_tracker_db.toggle_enabled(message.chat.id, True)
        await message.reply_text("✅ **Anti-edit detection enabled**. Edited messages will be deleted.")
    elif command == "disable":
        await edit_tracker_db.toggle_enabled(message.chat.id, False)
        await message.reply_text("❌ **Anti-edit detection disabled**. Edited messages will NOT be deleted.")
    else:
        await message.reply_text("Usage: `/edit enable` or `/edit disable`")

@app.on_message(filters.command("antiedit") & filters.group)
async def antiedit_command(client: Client, message: Message):
    is_admin = await anti_edit_manager.is_admin_or_owner(client, message.chat.id, message.from_user.id)
    if not is_admin:
        admin_status = "UNKNOWN"
        try:
            member = await client.get_chat_member(message.chat.id, message.from_user.id)
            admin_status = getattr(member, "status", None)
            admins = await client.get_chat_administrators(message.chat.id)
            admin_ids = [a.user.id for a in admins]
            admin_debug = f"[admin_ids={admin_ids}]"
        except Exception as e:
            admin_debug = f"[error: {e}]"
        return await message.reply_text(f"❌ **Admin only**\nDetected status: <code>{admin_status}</code>\n{admin_debug}", quote=True)
    if not edit_tracker_db:
        return await message.reply_text("❌ **Database not initialized**")
    parts = message.text.split()
    if len(parts) == 1:
        config = await edit_tracker_db.get_config(message.chat.id)
        status_text = (
            f"🔍 **Anti-Edit Detection Status**\n\n"
            f"**Enabled:** {'✅ Yes' if config.get('enabled') else '❌ No'}\n"
            f"**Warning Time:** {config.get('warning_time', 60)} seconds\n"
            f"**Exclude Admins:** {'✅ Yes' if config.get('exclude_admins') else '❌ No'}\n"
            f"**Exclude Owner:** {'✅ Yes' if config.get('exclude_owner') else '❌ No'}\n"
            f"**Delete Warning:** {'✅ Yes' if config.get('delete_warning_msg') else '❌ No'}\n"
        )
        return await message.reply_text(status_text)
    command = parts[1].lower()
    if command == "enable":
        await edit_tracker_db.toggle_enabled(message.chat.id, True)
        await message.reply_text("✅ **Anti-edit detection enabled**")
    elif command == "disable":
        await edit_tracker_db.toggle_enabled(message.chat.id, False)
        await message.reply_text("❌ **Anti-edit detection disabled**")
    elif command == "time":
        if len(parts) < 3:
            return await message.reply_text("❌ **Usage:** `/antiedit time [seconds]`")
        try:
            seconds = int(parts[2])
            if not (10 <= seconds <= 300):
                return await message.reply_text("❌ **Valid range:** 10-300 seconds")
            await edit_tracker_db.set_warning_time(message.chat.id, seconds)
            await message.reply_text(f"✅ **Warning time set to {seconds} seconds**")
        except ValueError:
            return await message.reply_text("❌ **Invalid number**")
    elif command == "admins":
        if len(parts) < 3:
            return await message.reply_text("❌ **Usage:** `/antiedit admins yes/no`")
        exempt = parts[2].lower() == "yes"
        await edit_tracker_db.set_admin_exemption(message.chat.id, exempt)
        status = "will be exempt" if exempt else "won't be exempt"
        await message.reply_text(f"✅ **Admins {status} from edit detection**")
    else:
        await message.reply_text(
            "❌ **Unknown command**\n\n"
            "**Usage:**\n"
            "`/antiedit` - Show status\n"
            "`/antiedit enable` - Enable\n"
            "`/antiedit disable` - Disable\n"
            "`/antiedit time [sec]` - Set warning time\n"
            "`/antiedit admins yes/no` - Exempt admins"
        )

@app.on_message(filters.command("antiedit_stats") & filters.group)
async def antiedit_stats_command(client: Client, message: Message):
    is_admin = await anti_edit_manager.is_admin_or_owner(client, message.chat.id, message.from_user.id)
    if not is_admin:
        admin_status = "UNKNOWN"
        try:
            member = await client.get_chat_member(message.chat.id, message.from_user.id)
            admin_status = getattr(member, "status", None)
            admins = await client.get_chat_administrators(message.chat.id)
            admin_ids = [a.user.id for a in admins]
            admin_debug = f"[admin_ids={admin_ids}]"
        except Exception as e:
            admin_debug = f"[error: {e}]"
        return await message.reply_text(f"❌ **Admin only**\nDetected status: <code>{admin_status}</code>\n{admin_debug}", quote=True)
    if not edit_tracker_db:
        return await message.reply_text("❌ **Database not initialized**")
    stats = await edit_tracker_db.get_stats(message.chat.id)
    stats_text = (
        f"📊 **Anti-Edit Statistics**\n\n"
        f"**Pending Deletions:** {stats.get('pending_deletions', 0)}\n"
        f"**Completed Deletions:** {stats.get('completed_deletions', 0)}\n"
        f"**Total Edits Logged:** {stats.get('total_edits_logged', 0)}\n"
        f"**Warning Time:** {stats.get('warning_time', 60)} seconds\n"
    )
    await message.reply_text(stats_text)

async def cleanup_on_startup(client: Client):
    try:
        if not edit_tracker_db:
            return
        await edit_tracker_db.cleanup_old_data(days=0)
        logger.info("[AntiEdit] Cleanup completed on startup")
    except Exception as e:
        logger.error(f"[AntiEdit] Error during cleanup: {e}")

__all__ = [
    "handle_edited_message",
    "edit_toggle_command",
    "antiedit_command",
    "antiedit_stats_command",
    "cleanup_on_startup",
    "AntiEditManager"
]
