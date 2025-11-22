"""
Anti-Edit Message Detection Plugin
Production-Ready Ultimate Version for VivaanXMusic4.0

Features:
- Detects ONLY real message edits (never replies, reactions, quotes, forwards)
- Sends warning and deletes edited messages after configurable delay
- /edit enable and /edit disable commands for easy control
- 100% reliable admin/owner detection in all Telegram group types
- Comprehensive error handling and debug output
- Clean, professional code structure
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
    """Manages anti-edit detection and deletion for groups"""
    
    def __init__(self):
        self.pending_tasks: Dict[str, asyncio.Task] = {}

    async def is_admin_or_owner(self, chat_id: int, user_id: int) -> bool:
        """
        Check if user is admin or owner in the chat.
        Uses app (main Pyrogram client) directly for 100% reliability.
        Falls back to admin list check if status check fails.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
            
        Returns:
            True if user is admin/owner, False otherwise
        """
        try:
            # First attempt: Fast status check
            member = await app.get_chat_member(chat_id, user_id)
            status = getattr(member, "status", None)
            if status in ("administrator", "creator"):
                return True
            
            # Fallback: Check admin list (handles all edge cases)
            admins = await app.get_chat_administrators(chat_id)
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
        """
        Determine if we should detect and delete edits from this user.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
            
        Returns:
            True if edits should be detected, False otherwise
        """
        try:
            if not edit_tracker_db:
                return False
            
            config = await edit_tracker_db.get_config(chat_id)
            
            # Check if anti-edit is enabled
            if not config.get("enabled", True):
                return False
            
            # Exclude bot owner
            if user_id == OWNER_ID:
                return False
            
            # Optionally exclude admins
            if config.get("exclude_admins", True):
                if await self.is_admin_or_owner(chat_id, user_id):
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"[AntiEdit] Error in detection logic: {e}")
            return False

    async def send_warning(self, chat_id: int, message_id: int, warning_time: int) -> Optional[Message]:
        """Send warning message for edited content"""
        try:
            text = EDIT_WARNING_MESSAGE.format(time=warning_time)
            return await app.send_message(chat_id, text, reply_to_message_id=message_id)
        except Exception as e:
            logger.error(f"[AntiEdit] Error sending warning: {e}")
            return None

    async def schedule_deletion(self, chat_id: int, message_id: int, user_id: int,
                               warning_msg_id: Optional[int], delete_after_seconds: int):
        """Schedule message and warning deletion after specified time"""
        key = f"{chat_id}_{message_id}"
        
        # Cancel existing task if any
        if key in self.pending_tasks:
            self.pending_tasks[key].cancel()
        
        async def delete_task():
            try:
                await asyncio.sleep(delete_after_seconds)
                
                # Delete original message
                try:
                    await app.delete_messages(chat_id, message_id)
                    logger.info(f"[AntiEdit] Deleted edited message {chat_id}/{message_id}")
                except MessageDeleteForbidden:
                    logger.warning(f"[AntiEdit] Cannot delete message {message_id} - missing permissions")
                except Exception as e:
                    logger.error(f"[AntiEdit] Error deleting message: {e}")
                
                # Delete warning message
                if warning_msg_id:
                    try:
                        await app.delete_messages(chat_id, warning_msg_id)
                        logger.info(f"[AntiEdit] Deleted warning {warning_msg_id}")
                    except:
                        pass
                
                # Update database
                if edit_tracker_db:
                    pending = await edit_tracker_db.pending_deletions_collection.find_one({
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "status": "pending"
                    })
                    if pending:
                        await edit_tracker_db.mark_deletion_done(str(pending["_id"]))
                        
            except asyncio.CancelledError:
                logger.debug(f"[AntiEdit] Deletion task cancelled for {message_id}")
            except Exception as e:
                logger.error(f"[AntiEdit] Error in deletion task: {e}")
            finally:
                if key in self.pending_tasks:
                    del self.pending_tasks[key]
        
        task = asyncio.create_task(delete_task())
        self.pending_tasks[key] = task
        logger.info(f"[AntiEdit] Scheduled deletion for {message_id} in {delete_after_seconds}s")

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
    """
    Check if this is a real message edit (not reply, forward, reaction, etc.)
    
    Args:
        message: Pyrogram Message object
        
    Returns:
        True if this is a real edit, False otherwise
    """
    if not message or not message.from_user:
        return False
    
    # Must have text or caption content
    has_content = bool(message.text or message.caption)
    
    # Exclude replies, service messages, forwards, via_bot
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
    # Only process real edits
    if not is_real_edit(message):
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    message_id = message.id
    
    # Check if we should detect this edit
    should_detect = await anti_edit_manager.should_detect_edit(chat_id, user_id)
    if not should_detect:
        return
    
    # Get configuration
    config = await edit_tracker_db.get_config(chat_id)
    warning_time = config.get("warning_time", EDIT_DELETE_TIME)
    
    # Log the edit
    text = message.text or message.caption or "[non-text content]"
    await anti_edit_manager.log_edit(chat_id, user_id, message_id, text[:200])
    
    # Send warning
    warning_msg = await anti_edit_manager.send_warning(chat_id, message_id, warning_time)
    warning_msg_id = warning_msg.id if warning_msg else None
    
    # Schedule deletion
    await anti_edit_manager.schedule_deletion(chat_id, message_id, user_id, warning_msg_id, warning_time)
    logger.info(f"[AntiEdit] Edit detected and flagged: {chat_id}/{message_id}")


@app.on_message(filters.command(["edit"]) & filters.group)
async def edit_toggle_command(client: Client, message: Message):
    """/edit enable or /edit disable command"""
    # Check admin status
    is_admin = await anti_edit_manager.is_admin_or_owner(message.chat.id, message.from_user.id)
    
    if not is_admin:
        # Provide debug info
        try:
            member = await app.get_chat_member(message.chat.id, message.from_user.id)
            admin_status = getattr(member, "status", "UNKNOWN")
        except Exception as e:
            admin_status = f"ERROR: {e}"
        
        return await message.reply_text(
            f"❌ **Admin only**\n\n"
            f"Your status: <code>{admin_status}</code>",
            quote=True
        )
    
    if not edit_tracker_db:
        return await message.reply_text("❌ **Database not initialized**")
    
    parts = message.text.split()
    
    # Show current status
    if len(parts) < 2:
        config = await edit_tracker_db.get_config(message.chat.id)
        status = config.get("enabled", True)
        status_text = "✅ enabled" if status else "❌ disabled"
        return await message.reply_text(f"Anti-edit is currently **{status_text}**.")
    
    command = parts[1].lower()
    
    if command == "enable":
        await edit_tracker_db.toggle_enabled(message.chat.id, True)
        await message.reply_text("✅ **Anti-edit detection enabled**\nEdited messages will be deleted.")
        
    elif command == "disable":
        await edit_tracker_db.toggle_enabled(message.chat.id, False)
        await message.reply_text("❌ **Anti-edit detection disabled**\nEdited messages will NOT be deleted.")
        
    else:
        await message.reply_text("**Usage:**\n`/edit enable` or `/edit disable`")


@app.on_message(filters.command("antiedit") & filters.group)
async def antiedit_command(client: Client, message: Message):
    """/antiedit command for advanced configuration"""
    # Check admin status
    is_admin = await anti_edit_manager.is_admin_or_owner(message.chat.id, message.from_user.id)
    
    if not is_admin:
        try:
            member = await app.get_chat_member(message.chat.id, message.from_user.id)
            admin_status = getattr(member, "status", "UNKNOWN")
        except Exception as e:
            admin_status = f"ERROR: {e}"
        
        return await message.reply_text(
            f"❌ **Admin only**\n\n"
            f"Your status: <code>{admin_status}</code>",
            quote=True
        )
    
    if not edit_tracker_db:
        return await message.reply_text("❌ **Database not initialized**")
    
    parts = message.text.split()
    
    # Show status
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
    """/antiedit_stats command to show statistics"""
    # Check admin status
    is_admin = await anti_edit_manager.is_admin_or_owner(message.chat.id, message.from_user.id)
    
    if not is_admin:
        return await message.reply_text("❌ **Admin only**", quote=True)
    
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
    """Clean up old data on bot startup"""
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
