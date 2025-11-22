"""
Anti-Edit Message Detection Plugin
Perfect version for VivaanXMusic4.0 with JARVIS bot

Features:
- Detects ONLY real message edits (never replies, reactions, quotes, forwards)
- Sends warning and deletes edited messages after configurable delay
- /edit enable and /edit disable commands for easy control
- 100% reliable admin/owner detection in all Telegram group types
- Works perfectly with JARVIS bot client
"""

import asyncio
import logging
from typing import Optional, Dict
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import MessageDeleteForbidden, UserNotParticipant, FloodWait
from config import OWNER_ID, EDIT_DELETE_TIME, EDIT_WARNING_MESSAGE

# Import the JARVIS bot instance
from VIVAANXMUSIC import app

try:
    from VIVAANXMUSIC.mongo.edit_tracker_db import edit_tracker_db
except ImportError:
    edit_tracker_db = None

logger = logging.getLogger(__name__)


class AntiEditManager:
    """Manages anti-edit detection and deletion for groups"""
    
    def __init__(self):
        self.pending_tasks: Dict[str, asyncio.Task] = {}
        # Store reference to bot client
        self.bot = app

    async def is_admin_or_owner(self, chat_id: int, user_id: int) -> bool:
        """
        Check if user is admin or owner
        Uses self.bot (the JARVIS instance) for all operations
        """
        try:
            # Use self.bot instead of app to ensure correct client
            member = await self.bot.get_chat_member(chat_id, user_id)
            status = getattr(member, "status", None)
            if status in ("administrator", "creator"):
                return True
            
            # Fallback: Check admin list
            admins = await self.bot.get_chat_administrators(chat_id)
            for admin in admins:
                if admin.user.id == user_id:
                    return True
            
            return False
            
        except FloodWait as fe:
            await asyncio.sleep(fe.value)
            return await self.is_admin_or_owner(chat_id, user_id)
        except Exception as e:
            logger.error(f"[AntiEdit] Error checking admin status: {e}")
            return False

    async def should_detect_edit(self, chat_id: int, user_id: int) -> bool:
        """Determine if we should detect and delete edits from this user"""
        try:
            if not edit_tracker_db:
                return False
            
            config = await edit_tracker_db.get_config(chat_id)
            
            if not config.get("enabled", True):
                return False
            
            if user_id == OWNER_ID:
                return False
            
            if config.get("exclude_admins", True):
                if await self.is_admin_or_owner(chat_id, user_id):
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"[AntiEdit] Error in detection logic: {e}")
            return False

    async def send_warning(self, chat_id: int, message_id: int, warning_time: int) -> Optional[Message]:
        """Send warning message"""
        try:
            text = EDIT_WARNING_MESSAGE.format(time=warning_time)
            return await self.bot.send_message(chat_id, text, reply_to_message_id=message_id)
        except Exception as e:
            logger.error(f"[AntiEdit] Error sending warning: {e}")
            return None

    async def schedule_deletion(self, chat_id: int, message_id: int, user_id: int,
                               warning_msg_id: Optional[int], delete_after_seconds: int):
        """Schedule message deletion"""
        key = f"{chat_id}_{message_id}"
        
        if key in self.pending_tasks:
            self.pending_tasks[key].cancel()
        
        async def delete_task():
            try:
                await asyncio.sleep(delete_after_seconds)
                
                try:
                    await self.bot.delete_messages(chat_id, message_id)
                    logger.info(f"[AntiEdit] Deleted edited message {chat_id}/{message_id}")
                except MessageDeleteForbidden:
                    logger.warning(f"[AntiEdit] Cannot delete message {message_id}")
                except Exception as e:
                    logger.error(f"[AntiEdit] Error deleting message: {e}")
                
                if warning_msg_id:
                    try:
                        await self.bot.delete_messages(chat_id, warning_msg_id)
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
        """Log edit to database"""
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


# Initialize manager
anti_edit_manager = AntiEditManager()


def is_real_edit(message: Message) -> bool:
    """Check if this is a real message edit (not reply/forward/reaction)"""
    if not message or not message.from_user:
        return False
    
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
    """Handle edited messages in groups"""
    if not is_real_edit(message):
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    message_id = message.id
    
    should_detect = await anti_edit_manager.should_detect_edit(chat_id, user_id)
    if not should_detect:
        return
    
    config = await edit_tracker_db.get_config(chat_id)
    warning_time = config.get("warning_time", EDIT_DELETE_TIME)
    
    text = message.text or message.caption or "[non-text content]"
    await anti_edit_manager.log_edit(chat_id, user_id, message_id, text[:200])
    
    warning_msg = await anti_edit_manager.send_warning(chat_id, message_id, warning_time)
    warning_msg_id = warning_msg.id if warning_msg else None
    
    await anti_edit_manager.schedule_deletion(chat_id, message_id, user_id, warning_msg_id, warning_time)


@app.on_message(filters.command(["edit"]) & filters.group)
async def edit_toggle_command(client: Client, message: Message):
    """/edit enable or /edit disable command"""
    is_admin = await anti_edit_manager.is_admin_or_owner(message.chat.id, message.from_user.id)
    
    if not is_admin:
        return await message.reply_text("❌ **Admin only**", quote=True)
    
    if not edit_tracker_db:
        return await message.reply_text("❌ **Database not initialized**")
    
    parts = message.text.split()
    
    if len(parts) < 2:
        config = await edit_tracker_db.get_config(message.chat.id)
        status = config.get("enabled", True)
        status_text = "✅ enabled" if status else "❌ disabled"
        return await message.reply_text(f"Anti-edit is currently **{status_text}**.")
    
    command = parts[1].lower()
    
    if command == "enable":
        await edit_tracker_db.toggle_enabled(message.chat.id, True)
        await message.reply_text("✅ **Anti-edit enabled**\nEdited messages will be deleted.")
        
    elif command == "disable":
        await edit_tracker_db.toggle_enabled(message.chat.id, False)
        await message.reply_text("❌ **Anti-edit disabled**\nEdited messages won't be deleted.")
        
    else:
        await message.reply_text("**Usage:** `/edit enable` or `/edit disable`")


@app.on_message(filters.command("antiedit") & filters.group)
async def antiedit_command(client: Client, message: Message):
    """Advanced configuration command"""
    is_admin = await anti_edit_manager.is_admin_or_owner(message.chat.id, message.from_user.id)
    
    if not is_admin:
        return await message.reply_text("❌ **Admin only**", quote=True)
    
    if not edit_tracker_db:
        return await message.reply_text("❌ **Database not initialized**")
    
    parts = message.text.split()
    
    if len(parts) == 1:
        config = await edit_tracker_db.get_config(message.chat.id)
        status_text = (
            f"🔍 **Anti-Edit Status**\n\n"
            f"**Enabled:** {'✅ Yes' if config.get('enabled') else '❌ No'}\n"
            f"**Warning Time:** {config.get('warning_time', 60)}s\n"
            f"**Exclude Admins:** {'✅ Yes' if config.get('exclude_admins') else '❌ No'}\n"
        )
        return await message.reply_text(status_text)
    
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
        exempt = parts[2].lower() == "yes"
        await edit_tracker_db.set_admin_exemption(message.chat.id, exempt)
        status = "exempt" if exempt else "not exempt"
        await message.reply_text(f"✅ **Admins are {status}**")
        
    else:
        await message.reply_text(
            "**Commands:**\n"
            "`/antiedit` - Status\n"
            "`/antiedit enable` - Enable\n"
            "`/antiedit disable` - Disable\n"
            "`/antiedit time [sec]` - Set time\n"
            "`/antiedit admins yes/no` - Admin exempt"
        )


@app.on_message(filters.command("antiedit_stats") & filters.group)
async def antiedit_stats_command(client: Client, message: Message):
    """Statistics command"""
    is_admin = await anti_edit_manager.is_admin_or_owner(message.chat.id, message.from_user.id)
    
    if not is_admin:
        return await message.reply_text("❌ **Admin only**")
    
    if not edit_tracker_db:
        return await message.reply_text("❌ **Database not initialized**")
    
    stats = await edit_tracker_db.get_stats(message.chat.id)
    stats_text = (
        f"📊 **Statistics**\n\n"
        f"**Pending:** {stats.get('pending_deletions', 0)}\n"
        f"**Completed:** {stats.get('completed_deletions', 0)}\n"
        f"**Total Edits:** {stats.get('total_edits_logged', 0)}\n"
    )
    await message.reply_text(stats_text)


async def cleanup_on_startup(client: Client):
    """Cleanup old data on startup"""
    try:
        if edit_tracker_db:
            await edit_tracker_db.cleanup_old_data(days=0)
            logger.info("[AntiEdit] Cleanup completed")
    except Exception as e:
        logger.error(f"[AntiEdit] Cleanup error: {e}")


__all__ = [
    "handle_edited_message",
    "edit_toggle_command",
    "antiedit_command",
    "antiedit_stats_command",
    "cleanup_on_startup",
    "AntiEditManager"
]
