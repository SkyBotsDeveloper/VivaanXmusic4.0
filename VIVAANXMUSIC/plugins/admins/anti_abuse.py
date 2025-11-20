"""
Anti-Abusive Word Detection Plugin
Smart pattern-based detection of abusive language
Part of VivaanXMusic4.0 Security System

Features:
- Pattern-based abuse detection
- User warning system (mute/ban/delete_only/warn_only)
- Admin word management
- Statistics and logging
- Configurable per group
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from pyrogram import Client, filters
from pyrogram.types import Message, ChatMember, User
from pyrogram.errors import (
    MessageNotModified,
    MessageDeleteForbidden,
    ChatAdminRequired,
    UserNotParticipant,
    PeerIdInvalid
)
from config import (
    OWNER_ID,
    DEFAULT_WARNING_LIMIT,
    DEFAULT_ABUSE_ACTION,
    DEFAULT_MUTE_DURATION,
    ABUSE_WARNING_DELETE_TIME
)

# Import database and utilities
try:
    from VIVAANXMUSIC.mongo.abuse_words_db import abuse_words_db
    from VIVAANXMUSIC.utils.abuse_detector import AbuseDetector, get_detector
    from VIVAANXMUSIC.utils.warning_manager import WarningManager, get_warning_manager
except ImportError:
    abuse_words_db = None
    AbuseDetector = None
    WarningManager = None

logger = logging.getLogger(__name__)


class AntiAbuseManager:
    """Manages anti-abuse detection for groups"""
    
    def __init__(self):
        """Initialize anti-abuse manager"""
        self.detector = get_detector() if get_detector else None
        self.warning_manager = get_warning_manager() if get_warning_manager else None
        self.mute_tasks: Dict[str, asyncio.Task] = {}  # Track mute tasks
        self.warning_delete_tasks: Dict[int, asyncio.Task] = {}  # Track warning deletion tasks
    
    async def is_admin(self, client: Client, chat_id: int, user_id: int) -> bool:
        """Check if user is admin"""
        try:
            member = await client.get_chat_member(chat_id, user_id)
            return member.status in ["creator", "administrator"]
        except UserNotParticipant:
            return False
        except Exception as e:
            logger.error(f"[AntiAbuse] Error checking admin: {e}")
            return False
    
    async def is_owner(self, user_id: int) -> bool:
        """Check if user is bot owner"""
        return user_id == OWNER_ID
    
    async def should_detect_abuse(
        self,
        chat_id: int,
        user_id: int
    ) -> bool:
        """
        Check if abuse should be detected
        
        Args:
            chat_id: Chat ID
            user_id: User ID
            
        Returns:
            bool: True if should detect
        """
        try:
            if not abuse_words_db:
                return False
            
            config = await abuse_words_db.get_config(chat_id)
            
            if not config.get("enabled", True):
                return False
            
            # Skip owner
            if await self.is_owner(user_id):
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
        """
        Detect abuse in message
        
        Args:
            text: Message text
            chat_id: Chat ID
            strict_mode: Enable strict mode
            
        Returns:
            tuple: (detected, matched_word)
        """
        try:
            if not text or not self.detector or not abuse_words_db:
                return False, None
            
            # Get all abuse words
            abuse_words = await abuse_words_db.get_all_abuse_words()
            
            if not abuse_words:
                return False, None
            
            # Extract base words
            words_list = [w.get("word") for w in abuse_words]
            
            # Detect
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
        client: Client,
        chat_id: int,
        message_id: int,
        warnings: int,
        limit: int,
        action: str,
        username: str = "User"
    ) -> Optional[Message]:
        """
        Send warning message
        
        Args:
            client: Pyrogram client
            chat_id: Chat ID
            message_id: Original message ID
            warnings: Warning count
            limit: Warning limit
            action: Action type
            username: Username
            
        Returns:
            Message: Sent message or None
        """
        try:
            if not self.warning_manager:
                return None
            
            warning_text = self.warning_manager.generate_warning_message(
                warnings,
                limit,
                action,
                username
            )
            
            msg = await client.send_message(
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
        client: Client,
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
                    await client.delete_messages(chat_id, warning_msg_id)
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
    
    async def mute_user(
        self,
        client: Client,
        chat_id: int,
        user_id: int,
        duration_minutes: int = 1440
    ) -> bool:
        """
        Mute user for specified duration
        
        Args:
            client: Pyrogram client
            chat_id: Chat ID
            user_id: User ID
            duration_minutes: Mute duration in minutes
            
        Returns:
            bool: True if successful
        """
        try:
            from pyrogram.types import ChatPermissions
            
            # Restrict user
            await client.restrict_chat_member(
                chat_id,
                user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=datetime.now() + timedelta(minutes=duration_minutes)
            )
            
            logger.info(f"[AntiAbuse] User {user_id} muted in {chat_id} for {duration_minutes}m")
            return True
        except Exception as e:
            logger.error(f"[AntiAbuse] Error muting user: {e}")
            return False
    
    async def ban_user(
        self,
        client: Client,
        chat_id: int,
        user_id: int
    ) -> bool:
        """
        Ban user permanently
        
        Args:
            client: Pyrogram client
            chat_id: Chat ID
            user_id: User ID
            
        Returns:
            bool: True if successful
        """
        try:
            await client.ban_chat_member(chat_id, user_id)
            logger.info(f"[AntiAbuse] User {user_id} banned from {chat_id}")
            return True
        except Exception as e:
            logger.error(f"[AntiAbuse] Error banning user: {e}")
            return False
    
    async def execute_action(
        self,
        client: Client,
        chat_id: int,
        user_id: int,
        action: str,
        username: str = "User",
        duration_minutes: int = 1440
    ) -> bool:
        """
        Execute action on user
        
        Args:
            client: Pyrogram client
            chat_id: Chat ID
            user_id: User ID
            action: Action type (mute/ban/delete_only/warn_only)
            username: Username
            duration_minutes: Mute duration
            
        Returns:
            bool: True if successful
        """
        try:
            if action == "mute":
                success = await self.mute_user(client, chat_id, user_id, duration_minutes)
                
                if success:
                    msg_text = self.warning_manager.generate_action_message(
                        "mute",
                        username,
                        duration_minutes
                    )
                    
                    try:
                        await client.send_message(chat_id, msg_text)
                    except:
                        pass
                
                return success
            
            elif action == "ban":
                success = await self.ban_user(client, chat_id, user_id)
                
                if success:
                    msg_text = self.warning_manager.generate_action_message(
                        "ban",
                        username
                    )
                    
                    try:
                        await client.send_message(chat_id, msg_text)
                    except:
                        pass
                
                return success
            
            # delete_only and warn_only don't need action
            return True
        except Exception as e:
            logger.error(f"[AntiAbuse] Error executing action: {e}")
            return False


# Initialize manager
anti_abuse_manager = AntiAbuseManager()


# ────────────────────────────────────────────────────────────
# Event Handlers
# ────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.group & ~filters.bot & ~filters.service)
async def handle_message_abuse(client: Client, message: Message):
    """
    Handle messages and detect abuse
    
    Args:
        client: Pyrogram client
        message: Message
    """
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        message_id = message.message_id
        
        if not user_id:
            return
        
        # Check if should detect
        should_detect = await anti_abuse_manager.should_detect_abuse(chat_id, user_id)
        
        if not should_detect:
            return
        
        # Get message text
        text = message.text or message.caption or ""
        
        if not text:
            return
        
        # Get config
        config = await abuse_words_db.get_config(chat_id)
        strict_mode = config.get("strict_mode", False)
        warning_limit = config.get("warning_limit", DEFAULT_WARNING_LIMIT)
        action = config.get("action", DEFAULT_ABUSE_ACTION)
        mute_duration = config.get("mute_duration", DEFAULT_MUTE_DURATION)
        delete_warning = config.get("delete_warning", True)
        warning_delete_time = config.get("warning_delete_time", ABUSE_WARNING_DELETE_TIME)
        
        # Detect abuse
        is_detected, matched_word = await anti_abuse_manager.detect_abuse_in_message(
            text,
            chat_id,
            strict_mode
        )
        
        if not is_detected:
            return
        
        # Delete abusive message
        try:
            await client.delete_messages(chat_id, message_id)
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
            action
        )
        
        # Get user info
        username = message.from_user.first_name if message.from_user else "User"
        
        # Send warning message
        warning_msg = await anti_abuse_manager.send_warning_message(
            client,
            chat_id,
            message_id,
            warnings,
            warning_limit,
            action,
            username
        )
        
        # Schedule warning deletion if configured
        if delete_warning and warning_msg:
            await anti_abuse_manager.schedule_warning_deletion(
                client,
                chat_id,
                warning_msg.message_id,
                warning_delete_time
            )
        
        # Check if action should be taken
        should_act_result = anti_abuse_manager.warning_manager.should_take_action(
            warnings,
            warning_limit,
            action
        )
        
        if should_act_result["should_act"]:
            await anti_abuse_manager.execute_action(
                client,
                chat_id,
                user_id,
                action,
                username,
                mute_duration
            )
        
        logger.info(f"[AntiAbuse] Abuse detected and handled: {matched_word}")
    
    except Exception as e:
        logger.error(f"[AntiAbuse] Error handling message: {e}")


# ────────────────────────────────────────────────────────────
# Admin Commands
# ────────────────────────────────────────────────────────────

@Client.on_message(filters.command("antiabuse") & filters.group)
async def antiabuse_command(client: Client, message: Message):
    """
    Configure anti-abuse detection
    
    /antiabuse - Show status
    /antiabuse enable - Enable
    /antiabuse disable - Disable
    /antiabuse action mute/ban/delete_only/warn_only - Set action
    /antiabuse limit 3 - Set warning limit
    /antiabuse strict yes/no - Toggle strict mode
    """
    try:
        # Check if admin
        user = await client.get_chat_member(message.chat.id, message.from_user.id)
        if user.status not in ["creator", "administrator"]:
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
                f"**Action:** `{config.get('action', 'delete_only')}`\n"
                f"**Warning Limit:** {config.get('warning_limit', 3)} (0 = unlimited)\n"
                f"**Mute Duration:** {config.get('mute_duration', 1440)} minutes\n"
                f"**Strict Mode:** {'✅ Yes' if config.get('strict_mode') else '❌ No'}\n\n"
                f"**Statistics:**\n"
                f"📊 Total Words: {stats.get('total_abuse_words', 0)}\n"
                f"📊 Total Violations: {stats.get('total_violations', 0)}\n"
                f"📊 Users Warned: {stats.get('users_with_warnings', 0)}\n"
            )
            
            return await message.reply_text(status_text)
        
        command = parts[1].lower()
        
        if command == "enable":
            await abuse_words_db.toggle_enabled(message.chat.id, True)
            await message.reply_text("✅ **Anti-abuse detection enabled**")
        
        elif command == "disable":
            await abuse_words_db.toggle_enabled(message.chat.id, False)
            await message.reply_text("❌ **Anti-abuse detection disabled**")
        
        elif command == "action":
            if len(parts) < 3:
                return await message.reply_text(
                    "❌ **Usage:** `/antiabuse action [mute|ban|delete_only|warn_only]`"
                )
            
            action = parts[2].lower()
            if await abuse_words_db.set_action(message.chat.id, action):
                await message.reply_text(f"✅ **Action set to `{action}`**")
            else:
                await message.reply_text("❌ **Invalid action**")
        
        elif command == "limit":
            if len(parts) < 3:
                return await message.reply_text("❌ **Usage:** `/antiabuse limit [0-100]`")
            
            try:
                limit = int(parts[2])
                if await abuse_words_db.set_warning_limit(message.chat.id, limit):
                    msg = "unlimited" if limit == 0 else f"{limit}"
                    await message.reply_text(f"✅ **Warning limit set to {msg}**")
                else:
                    await message.reply_text("❌ **Invalid limit**")
            except ValueError:
                await message.reply_text("❌ **Invalid number**")
        
        elif command == "strict":
            if len(parts) < 3:
                return await message.reply_text("❌ **Usage:** `/antiabuse strict yes/no`")
            
            strict = parts[2].lower() == "yes"
            config = await abuse_words_db.get_config(message.chat.id)
            config["strict_mode"] = strict
            
            await abuse_words_db.set_config(message.chat.id, config)
            status = "enabled" if strict else "disabled"
            await message.reply_text(f"✅ **Strict mode {status}**")
        
        else:
            await message.reply_text(
                "❌ **Unknown command**\n\n"
                "**Usage:**\n"
                "`/antiabuse` - Show status\n"
                "`/antiabuse enable` - Enable\n"
                "`/antiabuse disable` - Disable\n"
                "`/antiabuse action [type]` - Set action\n"
                "`/antiabuse limit [0-100]` - Set limit\n"
                "`/antiabuse strict yes/no` - Toggle strict mode"
            )
    
    except Exception as e:
        logger.error(f"[AntiAbuse] Error in command: {e}")
        await message.reply_text(f"❌ **Error:** {str(e)[:100]}")


@Client.on_message(filters.command("addabuse") & filters.group)
async def addabuse_command(client: Client, message: Message):
    """Add abusive word"""
    try:
        # Check if owner
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
            await message.reply_text(f"❌ **Word already exists or error occurred**")
    
    except Exception as e:
        logger.error(f"[AntiAbuse] Error in addabuse: {e}")
        await message.reply_text(f"❌ **Error:** {str(e)[:100]}")


@Client.on_message(filters.command("delabuse") & filters.group)
async def delabuse_command(client: Client, message: Message):
    """Remove abusive word"""
    try:
        # Check if owner
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


@Client.on_message(filters.command("listabuse") & filters.group)
async def listabuse_command(client: Client, message: Message):
    """List all abusive words"""
    try:
        if not abuse_words_db:
            return await message.reply_text("❌ **Database not initialized**")
        
        words = await abuse_words_db.get_all_abuse_words()
        
        if not words:
            return await message.reply_text("❌ **No abusive words configured**")
        
        # Format as list
        word_list = []
        for i, w in enumerate(words, 1):
            word_list.append(f"{i}. `{w.get('word')}` ({w.get('severity', 'high')})")
        
        text = f"📋 **Abusive Words List** ({len(words)} total)\n\n"
        text += "\n".join(word_list)
        
        # Split if too long
        if len(text) > 4000:
            text = text[:3997] + "..."
        
        await message.reply_text(text)
    
    except Exception as e:
        logger.error(f"[AntiAbuse] Error in listabuse: {e}")
        await message.reply_text(f"❌ **Error:** {str(e)[:100]}")


@Client.on_message(filters.command("abusetest") & filters.group)
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
            await message.reply_text(f"🚫 **Abuse detected!**\n\nMatched word: `{matched_word}`")
        else:
            await message.reply_text("✅ **No abuse detected**")
    
    except Exception as e:
        logger.error(f"[AntiAbuse] Error in abusetest: {e}")
        await message.reply_text(f"❌ **Error:** {str(e)[:100]}")


@Client.on_message(filters.command("abuseinfo") & filters.group)
async def abuseinfo_command(client: Client, message: Message):
    """Get user abuse info"""
    try:
        if not abuse_words_db:
            return await message.reply_text("❌ **Database not initialized**")
        
        # Get reply message user
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
            f"**Total Warnings:** {history.get('warnings', 0)}\n"
            f"**First Offense:** {history.get('first_offense', 'N/A')}\n"
            f"**Last Offense:** {history.get('last_offense', 'N/A')}\n"
        )
        
        offenses = history.get('offenses', [])
        if offenses:
            info_text += f"\n**Recent Violations:**\n"
            for i, offense in enumerate(offenses[-5:], 1):
                word = offense.get('word', 'unknown')
                info_text += f"{i}. `{word}`\n"
        
        await message.reply_text(info_text)
    
    except Exception as e:
        logger.error(f"[AntiAbuse] Error in abuseinfo: {e}")
        await message.reply_text(f"❌ **Error:** {str(e)[:100]}")


__all__ = [
    "handle_message_abuse",
    "antiabuse_command",
    "addabuse_command",
    "delabuse_command",
    "listabuse_command",
    "abusetest_command",
    "abuseinfo_command",
    "AntiAbuseManager"
]
