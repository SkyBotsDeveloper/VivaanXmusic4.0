"""
Anti-Edit Message Detection Plugin
Automatically deletes edited messages with 1-minute warning
Part of VivaanXMusic4.0 Security System

Features:
- Detects edited messages
- Sends 60-second warning
- Auto-deletes after countdown
- Configurable per group
- Admin exemption
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict
from pyrogram import Client, filters
from pyrogram.types import Message, ChatMember
from pyrogram.errors import (
    MessageNotModified,
    MessageDeleteForbidden,
    ChatAdminRequired,
    UserNotParticipant
)
from config import (
    OWNER_ID,
    EDIT_DELETE_TIME,
    EDIT_WARNING_MESSAGE
)

# Import bot instance
from VIVAANXMUSIC import app

# Import database and utilities
try:
    from VIVAANXMUSIC.mongo.edit_tracker_db import edit_tracker_db
except ImportError:
    edit_tracker_db = None

logger = logging.getLogger(__name__)


class AntiEditManager:
    """Manages anti-edit detection for groups"""
    
    def __init__(self):
        """Initialize anti-edit manager"""
        self.pending_tasks: Dict[str, asyncio.Task] = {}
        self.message_cache: Dict[str, Dict] = {}  # Store original messages
    
    async def is_admin(self, client: Client, chat_id: int, user_id: int) -> bool:
        """
        Check if user is admin in chat
        
        Args:
            client: Pyrogram client
            chat_id: Chat ID
            user_id: User ID
            
        Returns:
            bool: True if admin
        """
        try:
            member = await client.get_chat_member(chat_id, user_id)
            return member.status in ["creator", "administrator"]
        except UserNotParticipant:
            return False
        except Exception as e:
            logger.error(f"[AntiEdit] Error checking admin status: {e}")
            return False
    
    async def is_owner(self, user_id: int) -> bool:
        """Check if user is bot owner"""
        return user_id == OWNER_ID
    
    async def should_detect_edit(
        self,
        client: Client,
        chat_id: int,
        user_id: int,
        message_id: int
    ) -> bool:
        """
        Determine if edit should be detected
        
        Args:
            client: Pyrogram client
            chat_id: Chat ID
            user_id: User ID
            message_id: Message ID
            
        Returns:
            bool: True if should detect
        """
        try:
            if not edit_tracker_db:
                return False
            
            # Get config
            config = await edit_tracker_db.get_config(chat_id)
            
            # Check if enabled
            if not config.get("enabled", True):
                return False
            
            # Skip owner
            if await self.is_owner(user_id):
                return False
            
            # Skip admins if configured
            if config.get("exclude_admins", True):
                if await self.is_admin(client, chat_id, user_id):
                    return False
            
            # Skip owner of group
            if config.get("exclude_owner", True):
                try:
                    chat = await client.get_chat(chat_id)
                    if chat.owner_id == user_id:
                        return False
                except:
                    pass
            
            return True
        except Exception as e:
            logger.error(f"[AntiEdit] Error checking detection: {e}")
            return False
    
    async def send_warning(
        self,
        client: Client,
        chat_id: int,
        message_id: int,
        warning_time: int = 60
    ) -> Optional[Message]:
        """
        Send warning message
        
        Args:
            client: Pyrogram client
            chat_id: Chat ID
            message_id: Original message ID
            warning_time: Warning time in seconds
            
        Returns:
            Message: Sent warning message or None
        """
        try:
            warning_text = EDIT_WARNING_MESSAGE.format(time=warning_time)
            
            warning_msg = await client.send_message(
                chat_id,
                warning_text,
                reply_to_message_id=message_id
            )
            
            logger.info(f"[AntiEdit] Warning sent in {chat_id}/{message_id}")
            return warning_msg
        except Exception as e:
            logger.error(f"[AntiEdit] Error sending warning: {e}")
            return None
    
    async def schedule_deletion(
        self,
        client: Client,
        chat_id: int,
        message_id: int,
        user_id: int,
        warning_msg_id: Optional[int] = None,
        delete_after_seconds: int = 60
    ):
        """
        Schedule message deletion
        
        Args:
            client: Pyrogram client
            chat_id: Chat ID
            message_id: Message ID to delete
            user_id: User ID
            warning_msg_id: Warning message ID (for cleanup)
            delete_after_seconds: Seconds until deletion
        """
        task_key = f"{chat_id}_{message_id}"
        
        # Cancel existing task if any
        if task_key in self.pending_tasks:
            self.pending_tasks[task_key].cancel()
        
        try:
            # Add to database
            if edit_tracker_db:
                await edit_tracker_db.add_pending_deletion(
                    chat_id=chat_id,
                    message_id=message_id,
                    user_id=user_id,
                    warning_msg_id=warning_msg_id,
                    delete_in_seconds=delete_after_seconds
                )
            
            # Create deletion task
            async def delete_after_delay():
                try:
                    await asyncio.sleep(delete_after_seconds)
                    
                    # Delete original message
                    try:
                        await client.delete_messages(chat_id, message_id)
                        logger.info(f"[AntiEdit] Deleted message {chat_id}/{message_id}")
                    except MessageDeleteForbidden:
                        logger.warning(f"[AntiEdit] Cannot delete message {message_id}")
                    except Exception as e:
                        logger.error(f"[AntiEdit] Error deleting message: {e}")
                    
                    # Delete warning message
                    if warning_msg_id:
                        try:
                            await client.delete_messages(chat_id, warning_msg_id)
                            logger.info(f"[AntiEdit] Deleted warning {warning_msg_id}")
                        except:
                            pass
                    
                    # Mark as done in database
                    if edit_tracker_db:
                        # Get the pending deletion ID
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
                    # Remove from pending tasks
                    if task_key in self.pending_tasks:
                        del self.pending_tasks[task_key]
            
            # Store task
            task = asyncio.create_task(delete_after_delay())
            self.pending_tasks[task_key] = task
            
            logger.info(f"[AntiEdit] Deletion scheduled for {message_id} in {delete_after_seconds}s")
        except Exception as e:
            logger.error(f"[AntiEdit] Error scheduling deletion: {e}")
    
    async def log_edit(
        self,
        chat_id: int,
        user_id: int,
        message_id: int,
        original_text: str,
        edited_text: str
    ):
        """
        Log edited message
        
        Args:
            chat_id: Chat ID
            user_id: User ID
            message_id: Message ID
            original_text: Original text
            edited_text: Edited text
        """
        try:
            if edit_tracker_db:
                await edit_tracker_db.log_edit(
                    chat_id=chat_id,
                    user_id=user_id,
                    message_id=message_id,
                    original_text=original_text,
                    edited_text=edited_text
                )
            
            logger.debug(f"[AntiEdit] Edit logged for message {message_id}")
        except Exception as e:
            logger.error(f"[AntiEdit] Error logging edit: {e}")


# Initialize manager
anti_edit_manager = AntiEditManager()


# ────────────────────────────────────────────────────────────
# Event Handlers
# ────────────────────────────────────────────────────────────

@app.on_edited_message(filters.group)
async def handle_edited_message(client: Client, message: Message):
    """
    Handle edited messages in groups
    
    Args:
        client: Pyrogram client
        message: Edited message
    """
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        message_id = message.message_id
        
        if not user_id:
            return
        
        # Check if should detect
        should_detect = await anti_edit_manager.should_detect_edit(
            client,
            chat_id,
            user_id,
            message_id
        )
        
        if not should_detect:
            logger.debug(f"[AntiEdit] Edit not detected for {message_id}")
            return
        
        # Get config
        config = await edit_tracker_db.get_config(chat_id)
        warning_time = config.get("warning_time", EDIT_DELETE_TIME)
        
        # Get original message for logging
        original_text = message.text or message.caption or "[non-text content]"
        
        # Log the edit
        await anti_edit_manager.log_edit(
            chat_id,
            user_id,
            message_id,
            original_text[:200],
            original_text[:200]  # We don't have original, just store current
        )
        
        # Send warning
        warning_msg = await anti_edit_manager.send_warning(
            client,
            chat_id,
            message_id,
            warning_time
        )
        
        warning_msg_id = warning_msg.message_id if warning_msg else None
        
        # Schedule deletion
        await anti_edit_manager.schedule_deletion(
            client,
            chat_id,
            message_id,
            user_id,
            warning_msg_id,
            warning_time
        )
        
        logger.info(f"[AntiEdit] Edit detected and flagged for deletion: {chat_id}/{message_id}")
    
    except Exception as e:
        logger.error(f"[AntiEdit] Error handling edited message: {e}")


# ────────────────────────────────────────────────────────────
# Admin Commands
# ────────────────────────────────────────────────────────────

@app.on_message(filters.command("antiedit") & filters.group)
async def antiedit_command(client: Client, message: Message):
    """
    Configure anti-edit detection
    
    /antiedit - Show status
    /antiedit enable - Enable feature
    /antiedit disable - Disable feature
    /antiedit time 120 - Set warning time
    /antiedit admins yes/no - Exempt admins
    """
    try:
        # Check if user is admin
        user = await client.get_chat_member(message.chat.id, message.from_user.id)
        if user.status not in ["creator", "administrator"]:
            return await message.reply_text("❌ **Admin only**")
        
        if not edit_tracker_db:
            return await message.reply_text("❌ **Database not initialized**")
        
        parts = message.text.split()
        
        if len(parts) == 1:
            # Show status
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
                await message.reply_text("❌ **Invalid number**")
        
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
    
    except Exception as e:
        logger.error(f"[AntiEdit] Error in command: {e}")
        await message.reply_text(f"❌ **Error:** {str(e)[:100]}")


@app.on_message(filters.command("antiedit_stats") & filters.group)
async def antiedit_stats_command(client: Client, message: Message):
    """Show anti-edit statistics"""
    try:
        # Check if admin
        user = await client.get_chat_member(message.chat.id, message.from_user.id)
        if user.status not in ["creator", "administrator"]:
            return await message.reply_text("❌ **Admin only**")
        
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
    
    except Exception as e:
        logger.error(f"[AntiEdit] Error in stats command: {e}")
        await message.reply_text(f"❌ **Error:** {str(e)[:100]}")


# ────────────────────────────────────────────────────────────
# Cleanup on Startup
# ────────────────────────────────────────────────────────────

async def cleanup_on_startup(client: Client):
    """Cleanup pending deletions on startup"""
    try:
        if not edit_tracker_db:
            return
        
        # Clean up pending deletions older than 1 hour
        await edit_tracker_db.cleanup_old_data(days=0)
        
        logger.info("[AntiEdit] Cleanup completed on startup")
    except Exception as e:
        logger.error(f"[AntiEdit] Error during cleanup: {e}")


__all__ = [
    "handle_edited_message",
    "antiedit_command",
    "antiedit_stats_command",
    "cleanup_on_startup",
    "AntiEditManager"
]
