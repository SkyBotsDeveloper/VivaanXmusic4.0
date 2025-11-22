"""
Anti-Abuse Detection Plugin - PRODUCTION VERSION
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
            
            if status in ("administrator", "creator"):
                return True
            
            if hasattr(member, "status"):
                status_str = str(member.status).lower()
                if "admin" in status_str or "creator" in status_str or "owner" in status_str:
                    return True
            
            return False
        except UserNotParticipant:
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


# ═══════════════════════════════════════════════════════════
# MESSAGE HANDLER - Group 5 (runs early)
# ═══════════════════════════════════════════════════════════

@app.on_message(filters.text & filters.group & ~filters.bot & ~filters.service, group=5)
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
# COMMAND HANDLERS - Group 4 (higher priority than default)
# ═══════════════════════════════════════════════════════════

@app.on_message(filters.command("antiabuse") & filters.group, group=4)
async def antiabuse_command(client: Client, message: Message):
    """Configure anti-abuse detection"""
    try:
        logger.info(f"[AntiAbuse] Command received from {message.from_user.id}")
        
        if not abuse_words_db:
            return await message.reply_text("❌ **Database not initialized**")
        
        is_admin = await anti_abuse_manager.is_admin(message.chat.id, message.from_user.id)
        if not is_admin:
            return await message.reply_text("❌ **Admin only**")
        
        parts = message.text.split()
        
        if len(parts) == 1:
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
            return await message.reply_text(status_text)
        
        command = parts[1].lower()
        
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
    except Exception as e:
        logger.error(f"[AntiAbuse] Command error: {e}")
        await message.reply_text(f"❌ **Error:** {str(e)[:100]}")


@app.on_message(filters.command("addabuse") & filters.group, group=4)
async def addabuse_command(client: Client, message: Message):
    """Add abusive word"""
    try:
        if message.from_user.id != OWNER_ID:
            return await message.reply_text("❌ **Owner only**")
        
        if not abuse_words_db:
            return await message.reply_text("❌ **Database not initialized**")
        
        parts = message.text.split()
        if len(parts) < 2:
            return await message.reply_text("❌ **Usage:** `/addabuse [word]`")
        
        word = parts[1].lower()
        severity = parts[2].lower() if len(parts) > 2 else "high"
        
        if severity not in ["low", "medium", "high"]:
            severity = "high"
        
        success = await abuse_words_db.add_abuse_word(word, severity, [], message.from_user.id)
        
        if success:
            await message.reply_text(f"✅ **Word added:** `{word}` ({severity})")
        else:
            await message.reply_text(f"❌ **Word exists**")
    except Exception as e:
        logger.error(f"[AntiAbuse] Error: {e}")
        await message.reply_text(f"❌ **Error**")


@app.on_message(filters.command("listabuse") & filters.group, group=4)
async def listabuse_command(client: Client, message: Message):
    """List abusive words"""
    try:
        if not abuse_words_db:
            return await message.reply_text("❌ **Database not initialized**")
        
        words = await abuse_words_db.get_all_abuse_words()
        
        if not words:
            return await message.reply_text("❌ **No words configured**")
        
        word_list = []
        for i, w in enumerate(words[:30], 1):
            word_list.append(f"{i}. `{w.get('word')}` ({w.get('severity', 'high')})")
        
        text = f"📋 **Abusive Words** ({len(words)} total)\n\n"
        text += "\n".join(word_list)
        
        if len(words) > 30:
            text += f"\n\n... and {len(words) - 30} more"
        
        await message.reply_text(text)
    except Exception as e:
        logger.error(f"[AntiAbuse] Error: {e}")
        await message.reply_text(f"❌ **Error**")


@app.on_message(filters.command("clearabuse") & filters.group, group=4)
async def clearabuse_command(client: Client, message: Message):
    """Clear user warnings"""
    try:
        if not abuse_words_db:
            return await message.reply_text("❌ **Database not initialized**")
        
        is_admin = await anti_abuse_manager.is_admin(message.chat.id, message.from_user.id)
        if not is_admin:
            return await message.reply_text("❌ **Admin only**")
        
        if message.reply_to_message and message.reply_to_message.from_user:
            user_id = message.reply_to_message.from_user.id
            username = message.reply_to_message.from_user.first_name
        else:
            return await message.reply_text("❌ **Reply to a user**")
        
        await abuse_words_db.clear_warnings(message.chat.id, user_id)
        await message.reply_text(f"✅ **Cleared warnings for {username}**")
    except Exception as e:
        logger.error(f"[AntiAbuse] Error: {e}")
        await message.reply_text(f"❌ **Error**")


__all__ = [
    "handle_message_abuse",
    "antiabuse_command",
    "addabuse_command",
    "listabuse_command",
    "clearabuse_command",
    "AntiAbuseManager"
]
