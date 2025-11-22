"""
Anti-Abuse Detection Plugin - DIAGNOSTIC VERSION
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from pyrogram import Client, filters
from pyrogram.types import Message, ChatMember, User, ChatPermissions
from pyrogram.errors import (
    MessageDeleteForbidden,
    ChatAdminRequired,
    UserNotParticipant,
    PeerIdInvalid
)

try:
    from config import OWNER_ID
except ImportError:
    OWNER_ID = 0

from VIVAANXMUSIC import app

try:
    from VIVAANXMUSIC.mongo.abuse_words_db import abuse_words_db
    from VIVAANXMUSIC.utils.abuse_detector import get_detector
except ImportError:
    abuse_words_db = None
    get_detector = None

logger = logging.getLogger(__name__)


class AntiAbuseManager:
    """Manages anti-abuse detection for groups"""
    
    def __init__(self):
        self.detector = get_detector() if get_detector else None
        self.warning_delete_tasks: Dict[int, asyncio.Task] = {}
    
    async def is_admin(self, chat_id: int, user_id: int) -> bool:
        """Check if user is admin"""
        try:
            member = await app.get_chat_member(chat_id, user_id)
            status = getattr(member, "status", None)
            
            logger.info(f"[AntiAbuse] Admin check: user {user_id} has status: {status}")
            
            if status in ("administrator", "creator"):
                return True
            
            if hasattr(member, "status"):
                status_str = str(member.status).lower()
                if "admin" in status_str or "creator" in status_str or "owner" in status_str:
                    return True
            
            return False
        except UserNotParticipant:
            logger.warning(f"[AntiAbuse] User {user_id} not in chat {chat_id}")
            return False
        except Exception as e:
            logger.error(f"[AntiAbuse] Error checking admin: {e}")
            return False
    
    async def is_owner(self, user_id: int) -> bool:
        """Check if user is bot owner"""
        return user_id == OWNER_ID
    
    async def should_detect_abuse(self, chat_id: int, user_id: int) -> bool:
        """Check if abuse should be detected"""
        try:
            if not abuse_words_db:
                return False
            
            config = await abuse_words_db.get_config(chat_id)
            
            if not config.get("enabled", True):
                return False
            
            if await self.is_owner(user_id):
                return False
            
            if config.get("exclude_admins", True):
                if await self.is_admin(chat_id, user_id):
                    return False
            
            return True
        except Exception as e:
            logger.error(f"[AntiAbuse] Error checking detection: {e}")
            return False
    
    async def detect_abuse_in_message(
        self,
        text: str,
        chat_id: int,
        strict_mode: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """Detect abuse in message"""
        try:
            if not text or not self.detector or not abuse_words_db:
                return False, None
            
            abuse_words = await abuse_words_db.get_all_abuse_words()
            
            if not abuse_words:
                return False, None
            
            words_list = [w.get("word") for w in abuse_words]
            
            is_detected, matched_word = self.detector.detect_abuse(
                text,
                words_list,
                strict_mode=strict_mode
            )
            
            return is_detected, matched_word
        except Exception as e:
            logger.error(f"[AntiAbuse] Error detecting abuse: {e}")
            return False, None
    
    async def send_warning_message(
        self,
        chat_id: int,
        message_id: int,
        warnings: int,
        username: str = "User"
    ) -> Optional[Message]:
        """Send warning message"""
        try:
            warning_text = (
                f"⚠️ **Warning**\n\n"
                f"**{username}**, please avoid using abusive language.\n"
                f"Your message has been deleted.\n\n"
                f"**Total Warnings:** {warnings}"
            )
            
            msg = await app.send_message(
                chat_id,
                warning_text,
                reply_to_message_id=message_id
            )
            
            logger.info(f"[AntiAbuse] Warning sent in {chat_id}/{message_id}")
            return msg
        except Exception as e:
            logger.error(f"[AntiAbuse] Error sending warning: {e}")
            return None
    
    async def schedule_warning_deletion(
        self,
        chat_id: int,
        warning_msg_id: int,
        delete_after_seconds: int = 10
    ):
        """Schedule warning message deletion"""
        try:
            task_key = f"{chat_id}_{warning_msg_id}"
            
            if task_key in self.warning_delete_tasks:
                self.warning_delete_tasks[task_key].cancel()
            
            async def delete_warning():
                try:
                    await asyncio.sleep(delete_after_seconds)
                    await app.delete_messages(chat_id, warning_msg_id)
                except:
                    pass
                finally:
                    if task_key in self.warning_delete_tasks:
                        del self.warning_delete_tasks[task_key]
            
            task = asyncio.create_task(delete_warning())
            self.warning_delete_tasks[task_key] = task
        except Exception as e:
            logger.error(f"[AntiAbuse] Error scheduling deletion: {e}")


anti_abuse_manager = AntiAbuseManager()


@app.on_message(filters.text & filters.group & ~filters.bot & ~filters.service)
async def handle_message_abuse(client: Client, message: Message):
    """Handle messages and detect abuse"""
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        message_id = message.id
        
        if not user_id or not abuse_words_db:
            return
        
        should_detect = await anti_abuse_manager.should_detect_abuse(chat_id, user_id)
        if not should_detect:
            return
        
        text = message.text or message.caption or ""
        if not text:
            return
        
        config = await abuse_words_db.get_config(chat_id)
        strict_mode = config.get("strict_mode", False)
        delete_warning = config.get("delete_warning", True)
        warning_delete_time = config.get("warning_delete_time", 10)
        
        is_detected, matched_word = await anti_abuse_manager.detect_abuse_in_message(
            text, chat_id, strict_mode
        )
        
        if not is_detected:
            return
        
        try:
            await app.delete_messages(chat_id, message_id)
            logger.info(f"[AntiAbuse] Deleted message in {chat_id}")
        except Exception as e:
            logger.error(f"[AntiAbuse] Error deleting: {e}")
        
        warnings = await abuse_words_db.add_warning(chat_id, user_id, matched_word, text[:100])
        await abuse_words_db.log_abuse_detection(chat_id, user_id, matched_word, text[:100], "delete_only")
        
        username = message.from_user.first_name if message.from_user else "User"
        warning_msg = await anti_abuse_manager.send_warning_message(chat_id, message_id, warnings, username)
        
        if delete_warning and warning_msg:
            await anti_abuse_manager.schedule_warning_deletion(chat_id, warning_msg.id, warning_delete_time)
        
        logger.info(f"[AntiAbuse] Handled: {matched_word}")
    except Exception as e:
        logger.error(f"[AntiAbuse] Error: {e}")


# ═══════════════════════════════════════════════════════════
# DIAGNOSTIC COMMAND - THIS WILL SHOW US WHAT'S HAPPENING
# ═══════════════════════════════════════════════════════════

@app.on_message(filters.command("antiabuse") & filters.group)
async def antiabuse_command(client: Client, message: Message):
    """Configure anti-abuse detection - WITH FULL DIAGNOSTICS"""
    try:
        # Log that command was received
        logger.info(f"[AntiAbuse] ✅ /antiabuse command RECEIVED from user {message.from_user.id} ({message.from_user.first_name})")
        
        # Check database
        if not abuse_words_db:
            logger.error("[AntiAbuse] ❌ Database not initialized!")
            return await message.reply_text("❌ **Database not initialized**")
        
        logger.info("[AntiAbuse] ✅ Database is initialized")
        
        # Check admin with detailed logging
        try:
            member = await app.get_chat_member(message.chat.id, message.from_user.id)
            status = getattr(member, "status", "unknown")
            logger.info(f"[AntiAbuse] User {message.from_user.id} status in chat: {status}")
        except Exception as e:
            logger.error(f"[AntiAbuse] ❌ Error getting member: {e}")
            return await message.reply_text(f"❌ **Error checking admin:** {str(e)[:100]}")
        
        is_admin = await anti_abuse_manager.is_admin(message.chat.id, message.from_user.id)
        
        logger.info(f"[AntiAbuse] Is admin? {is_admin}")
        
        if not is_admin:
            return await message.reply_text(
                f"❌ **Admin only**\n\n"
                f"Your status: `{status}`\n"
                f"User ID: `{message.from_user.id}`\n"
                f"Owner ID: `{OWNER_ID}`"
            )
        
        logger.info("[AntiAbuse] ✅ User is admin, proceeding with command")
        
        parts = message.text.split()
        
        if len(parts) == 1:
            logger.info("[AntiAbuse] Fetching config and stats...")
            config = await abuse_words_db.get_config(message.chat.id)
            stats = await abuse_words_db.get_abuse_stats(message.chat.id)
            
            status_text = (
                f"🚫 **Anti-Abuse Status**\n\n"
                f"**Enabled:** {'✅ Yes' if config.get('enabled') else '❌ No'}\n"
                f"**Mode:** Delete & Warn Only\n"
                f"**Exclude Admins:** {'✅ Yes' if config.get('exclude_admins') else '❌ No'}\n"
                f"**Strict Mode:** {'✅ Yes' if config.get('strict_mode') else '❌ No'}\n\n"
                f"**Stats:**\n"
                f"📊 Words: {stats.get('total_abuse_words', 0)}\n"
                f"📊 Violations: {stats.get('total_violations', 0)}\n"
                f"📊 Warned Users: {stats.get('users_with_warnings', 0)}\n"
            )
            logger.info("[AntiAbuse] ✅ Sending status response")
            return await message.reply_text(status_text)
        
        command = parts[1].lower()
        logger.info(f"[AntiAbuse] Processing subcommand: {command}")
        
        if command in ("on", "enable"):
            await abuse_words_db.toggle_enabled(message.chat.id, True)
            await message.reply_text("✅ **Anti-abuse enabled**")
        
        elif command in ("off", "disable"):
            await abuse_words_db.toggle_enabled(message.chat.id, False)
            await message.reply_text("❌ **Anti-abuse disabled**")
        
        elif command == "strict":
            if len(parts) < 3:
                return await message.reply_text("❌ **Usage:** `/antiabuse strict yes/no`")
            
            strict = parts[2].lower() == "yes"
            config = await abuse_words_db.get_config(message.chat.id)
            config["strict_mode"] = strict
            await abuse_words_db.set_config(message.chat.id, config)
            await message.reply_text(f"✅ **Strict mode {'on' if strict else 'off'}**")
        
        elif command == "admins":
            if len(parts) < 3:
                return await message.reply_text("❌ **Usage:** `/antiabuse admins yes/no`")
            
            exclude = parts[2].lower() == "yes"
            config = await abuse_words_db.get_config(message.chat.id)
            config["exclude_admins"] = exclude
            await abuse_words_db.set_config(message.chat.id, config)
            await message.reply_text(f"✅ **Admins {'excluded' if exclude else 'included'}**")
        
        else:
            await message.reply_text(
                "**Commands:**\n"
                "`/antiabuse` - Status\n"
                "`/antiabuse on/enable` - Enable\n"
                "`/antiabuse off/disable` - Disable\n"
                "`/antiabuse strict yes/no` - Strict mode\n"
                "`/antiabuse admins yes/no` - Exclude admins"
            )
        
        logger.info(f"[AntiAbuse] ✅ Command completed successfully")
        
    except Exception as e:
        logger.error(f"[AntiAbuse] ❌ Command error: {e}", exc_info=True)
        await message.reply_text(f"❌ **Error:** {str(e)[:200]}")


@app.on_message(filters.command("test") & filters.group)
async def test_command(client: Client, message: Message):
    """Simple test command to verify bot responds"""
    logger.info(f"[AntiAbuse] TEST COMMAND received from {message.from_user.id}")
    await message.reply_text(f"✅ **Bot is responding!**\n\nYour ID: `{message.from_user.id}`\nOwner ID: `{OWNER_ID}`")


__all__ = [
    "handle_message_abuse",
    "antiabuse_command",
    "test_command",
    "AntiAbuseManager"
]
