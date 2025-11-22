"""
Anti-Abusive Word Detection Plugin
Smart pattern-based detection of abusive language
Part of VivaanXMusic4.0 Security System

Features:
- Pattern-based abuse detection
- Warns users and deletes abusive messages
- No mute/ban - just warnings
- Admin word management
- Statistics and logging
- Configurable per group
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from pyrogram import Client, filters
from pyrogram.types import Message, ChatMember, User, ChatPermissions
from pyrogram.errors import (
    MessageNotModified,
    MessageDeleteForbidden,
    ChatAdminRequired,
    UserNotParticipant,
    PeerIdInvalid
)
from config import OWNER_ID

# Import the correct bot client
from VIVAANXMUSIC import app

# Import database and utilities
try:
    from VIVAANXMUSIC.mongo.abuse_words_db import abuse_words_db
    from VIVAANXMUSIC.utils.abuse_detector import AbuseDetector, get_detector
except ImportError:
    abuse_words_db = None
    AbuseDetector = None

logger = logging.getLogger(__name__)


class AntiAbuseManager:
    """Manages anti-abuse detection for groups"""
    
    def __init__(self):
        """Initialize anti-abuse manager"""
        self.detector = get_detector() if get_detector else None
        self.warning_delete_tasks: Dict[int, asyncio.Task] = {}
    
    async def is_admin(self, chat_id: int, user_id: int) -> bool:
        """Check if user is admin - uses app directly"""
        try:
            member = await app.get_chat_member(chat_id, user_id)
            status = getattr(member, "status", None)
            
            if status in ("administrator", "creator"):
                return True
            
            # Fallback string check
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
            
            # Skip bot owner
            if await self.is_owner(user_id):
                return False
            
            # Skip admins if configured
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
                f"**Warnings:** {warnings}"
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
                    logger.debug(f"[AntiAbuse] Deleted warning {warning_msg_id}")
                except:
                    pass
                finally:
                    if task_key in self.warning_delete_tasks:
                        del self.warning_delete_tasks[task_key]
            
            task = asyncio.create_task(delete_warning())
            self.warning_delete_tasks[task_key] = task
        except Exception as e:
            logger.error(f"[AntiAbuse] Error scheduling warning deletion: {e}")


anti_abuse_manager = AntiAbuseManager()


# ═══════════════════════════════════════════════════════════
# MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════

@app.on_message(filters.text & filters.group & ~filters.bot & ~filters.service)
async def handle_message_abuse(client: Client, message: Message):
    """Handle messages and detect abuse"""
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        message_id = message.id
        
        if not user_id:
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
            text,
            chat_id,
            strict_mode
        )
        
        if not is_detected:
            return
        
        # Delete abusive message
        try:
            await app.delete_messages(chat_id, message_id)
            logger.info(f"[AntiAbuse] Deleted abusive message in {chat_id}")
        except MessageDeleteForbidden:
            logger.warning(f"[AntiAbuse] Cannot delete message {message_id}")
        except Exception as e:
            logger.error(f"[AntiAbuse] Error deleting message: {e}")
        
        # Add warning
        warnings = await abuse_words_db.add_warning(
            chat_id,
            user_id,
            matched_word,
            text[:100]
        )
        
        # Log detection
        await abuse_words_db.log_abuse_detection(
            chat_id,
            user_id,
            matched_word,
            text[:100],
            "delete_only"
        )
        
        # Get user info
        username = message.from_user.first_name if message.from_user else "User"
        
        # Send warning message
        warning_msg = await anti_abuse_manager.send_warning_message(
            chat_id,
            message_id,
            warnings,
            username
        )
        
        # Schedule warning deletion if configured
        if delete_warning and warning_msg:
            await anti_abuse_manager.schedule_warning_deletion(
                chat_id,
                warning_msg.id,
                warning_delete_time
            )
        
        logger.info(f"[AntiAbuse] Abuse detected and handled: {matched_word}")
    
    except Exception as e:
        logger.error(f"[AntiAbuse] Error handling message: {e}")


# ═══════════════════════════════════════════════════════════
# ADMIN COMMANDS
# ═══════════════════════════════════════════════════════════

@app.on_message(filters.command("antiabuse") & filters.group)
async def antiabuse_command(client: Client, message: Message):
    """Configure anti-abuse detection"""
    try:
        is_admin = await anti_abuse_manager.is_admin(message.chat.id, message.from_user.id)
        if not is_admin:
            return await message.reply_text("❌ **Admin only**")
        
        if not abuse_words_db:
            return await message.reply_text("❌ **Database not initialized**")
        
        parts = message.text.split()
        
        if len(parts) == 1:
            # Show status
            config = await abuse_words_db.get_config(message.chat.id)
            stats = await abuse_words_db.get_abuse_stats(message.chat.id)
            
            status_text = (
                f"🚫 **Anti-Abuse Detection Status**\n\n"
                f"**Enabled:** {'✅ Yes' if config.get('enabled') else '❌ No'}\n"
                f"**Mode:** Delete & Warn Only\n"
                f"**Exclude Admins:** {'✅ Yes' if config.get('exclude_admins') else '❌ No'}\n"
                f"**Strict Mode:** {'✅ Yes' if config.get('strict_mode') else '❌ No'}\n\n"
                f"**Statistics:**\n"
                f"📊 Total Words: {stats.get('total_abuse_words', 0)}\n"
                f"📊 Violations: {stats.get('total_violations', 0)}\n"
                f"📊 Users Warned: {stats.get('users_with_warnings', 0)}\n"
            )
            
            return await message.reply_text(status_text)
        
        command = parts[1].lower()
        
        # Support both "on/off" and "enable/disable"
        if command in ("on", "enable"):
            await abuse_words_db.toggle_enabled(message.chat.id, True)
            await message.reply_text("✅ **Anti-abuse detection enabled**\nAbusive messages will be deleted with warnings.")
        
        elif command in ("off", "disable"):
            await abuse_words_db.toggle_enabled(message.chat.id, False)
            await message.reply_text("❌ **Anti-abuse detection disabled**")
        
        elif command == "strict":
            if len(parts) < 3:
                return await message.reply_text("❌ **Usage:** `/antiabuse strict yes/no`")
            
            strict = parts[2].lower() == "yes"
            config = await abuse_words_db.get_config(message.chat.id)
            config["strict_mode"] = strict
            
            await abuse_words_db.set_config(message.chat.id, config)
            status = "enabled" if strict else "disabled"
            await message.reply_text(f"✅ **Strict mode {status}**")
        
        elif command == "admins":
            if len(parts) < 3:
                return await message.reply_text("❌ **Usage:** `/antiabuse admins yes/no`")
            
            exclude = parts[2].lower() == "yes"
            config = await abuse_words_db.get_config(message.chat.id)
            config["exclude_admins"] = exclude
            
            await abuse_words_db.set_config(message.chat.id, config)
            status = "excluded" if exclude else "not excluded"
            await message.reply_text(f"✅ **Admins are {status} from detection**")
        
        else:
            await message.reply_text(
                "**Commands:**\n"
                "`/antiabuse` - Show status\n"
                "`/antiabuse on` or `enable` - Enable\n"
                "`/antiabuse off` or `disable` - Disable\n"
                "`/antiabuse strict yes/no` - Strict mode\n"
                "`/antiabuse admins yes/no` - Exclude admins"
            )
    
    except Exception as e:
        logger.error(f"[AntiAbuse] Error in command: {e}")
        await message.reply_text(f"❌ **Error:** {str(e)[:100]}")


@app.on_message(filters.command("addabuse") & filters.group)
async def addabuse_command(client: Client, message: Message):
    """Add abusive word"""
    try:
        if message.from_user.id != OWNER_ID:
            return await message.reply_text("❌ **Owner only**")
        
        if not abuse_words_db:
            return await message.reply_text("❌ **Database not initialized**")
        
        parts = message.text.split()
        
        if len(parts) < 2:
            return await message.reply_text("❌ **Usage:** `/addabuse [word] [severity]`")
        
        word = parts[1].lower()
        severity = parts[2].lower() if len(parts) > 2 else "high"
        
        if severity not in ["low", "medium", "high"]:
            severity = "high"
        
        success = await abuse_words_db.add_abuse_word(
            word,
            severity,
            [],
            message.from_user.id
        )
        
        if success:
            await message.reply_text(f"✅ **Word added:** `{word}` ({severity})")
        else:
            await message.reply_text(f"❌ **Word exists or error**")
    
    except Exception as e:
        logger.error(f"[AntiAbuse] Error in addabuse: {e}")
        await message.reply_text(f"❌ **Error:** {str(e)[:100]}")


@app.on_message(filters.command("delabuse") & filters.group)
async def delabuse_command(client: Client, message: Message):
    """Remove abusive word"""
    try:
        if message.from_user.id != OWNER_ID:
            return await message.reply_text("❌ **Owner only**")
        
        if not abuse_words_db:
            return await message.reply_text("❌ **Database not initialized**")
        
        parts = message.text.split()
        
        if len(parts) < 2:
            return await message.reply_text("❌ **Usage:** `/delabuse [word]`")
        
        word = parts[1].lower()
        
        success = await abuse_words_db.remove_abuse_word(word)
        
        if success:
            await message.reply_text(f"✅ **Word removed:** `{word}`")
        else:
            await message.reply_text(f"❌ **Word not found**")
    
    except Exception as e:
        logger.error(f"[AntiAbuse] Error in delabuse: {e}")
        await message.reply_text(f"❌ **Error:** {str(e)[:100]}")


@app.on_message(filters.command("listabuse") & filters.group)
async def listabuse_command(client: Client, message: Message):
    """List all abusive words"""
    try:
        if not abuse_words_db:
            return await message.reply_text("❌ **Database not initialized**")
        
        words = await abuse_words_db.get_all_abuse_words()
        
        if not words:
            return await message.reply_text("❌ **No abusive words configured**")
        
        word_list = []
        for i, w in enumerate(words[:50], 1):  # Show first 50
            word_list.append(f"{i}. `{w.get('word')}` ({w.get('severity', 'high')})")
        
        text = f"📋 **Abusive Words** ({len(words)} total)\n\n"
        text += "\n".join(word_list)
        
        if len(words) > 50:
            text += f"\n\n... and {len(words) - 50} more words"
        
        if len(text) > 4000:
            text = text[:3997] + "..."
        
        await message.reply_text(text)
    
    except Exception as e:
        logger.error(f"[AntiAbuse] Error in listabuse: {e}")
        await message.reply_text(f"❌ **Error:** {str(e)[:100]}")


@app.on_message(filters.command("abusetest") & filters.group)
async def abusetest_command(client: Client, message: Message):
    """Test abuse detection"""
    try:
        if not abuse_words_db:
            return await message.reply_text("❌ **Database not initialized**")
        
        parts = message.text.split(' ', 1)
        
        if len(parts) < 2:
            return await message.reply_text("❌ **Usage:** `/abusetest [text]`")
        
        text = parts[1]
        
        is_detected, matched_word = await anti_abuse_manager.detect_abuse_in_message(
            text,
            message.chat.id
        )
        
        if is_detected:
            await message.reply_text(f"🚫 **Abuse detected!**\n\nMatched: `{matched_word}`")
        else:
            await message.reply_text("✅ **No abuse detected**")
    
    except Exception as e:
        logger.error(f"[AntiAbuse] Error in abusetest: {e}")
        await message.reply_text(f"❌ **Error:** {str(e)[:100]}")


@app.on_message(filters.command("abuseinfo") & filters.group)
async def abuseinfo_command(client: Client, message: Message):
    """Get user abuse info"""
    try:
        if not abuse_words_db:
            return await message.reply_text("❌ **Database not initialized**")
        
        if message.reply_to_message and message.reply_to_message.from_user:
            user_id = message.reply_to_message.from_user.id
            username = message.reply_to_message.from_user.first_name
        else:
            return await message.reply_text("❌ **Reply to a user's message**")
        
        history = await abuse_words_db.get_user_history(message.chat.id, user_id)
        
        if not history:
            return await message.reply_text(f"✅ **{username}** has no violations")
        
        info_text = (
            f"📊 **Abuse Info - {username}**\n\n"
            f"**Warnings:** {history.get('warnings', 0)}\n"
            f"**First:** {history.get('first_offense', 'N/A')}\n"
            f"**Last:** {history.get('last_offense', 'N/A')}\n"
        )
        
        offenses = history.get('offenses', [])
        if offenses:
            info_text += f"\n**Recent:**\n"
            for i, offense in enumerate(offenses[-5:], 1):
                word = offense.get('word', 'unknown')
                info_text += f"{i}. `{word}`\n"
        
        await message.reply_text(info_text)
    
    except Exception as e:
        logger.error(f"[AntiAbuse] Error in abuseinfo: {e}")
        await message.reply_text(f"❌ **Error:** {str(e)[:100]}")


@app.on_message(filters.command("clearabuse") & filters.group)
async def clearabuse_command(client: Client, message: Message):
    """Clear user warnings"""
    try:
        is_admin = await anti_abuse_manager.is_admin(message.chat.id, message.from_user.id)
        if not is_admin:
            return await message.reply_text("❌ **Admin only**")
        
        if not abuse_words_db:
            return await message.reply_text("❌ **Database not initialized**")
        
        if message.reply_to_message and message.reply_to_message.from_user:
            user_id = message.reply_to_message.from_user.id
            username = message.reply_to_message.from_user.first_name
        else:
            return await message.reply_text("❌ **Reply to a user's message**")
        
        # Clear warnings
        await abuse_words_db.clear_user_warnings(message.chat.id, user_id)
        
        await message.reply_text(f"✅ **Cleared warnings for {username}**")
    
    except Exception as e:
        logger.error(f"[AntiAbuse] Error in clearabuse: {e}")
        await message.reply_text(f"❌ **Error:** {str(e)[:100]}")


__all__ = [
    "handle_message_abuse",
    "antiabuse_command",
    "addabuse_command",
    "delabuse_command",
    "listabuse_command",
    "abusetest_command",
    "abuseinfo_command",
    "clearabuse_command",
    "AntiAbuseManager"
]
