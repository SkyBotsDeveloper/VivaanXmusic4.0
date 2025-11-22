"""
VivaanXMusic Anti-Abuse Plugin — ULTIMATE MODERN VERSION

Features:
- Owner adds words once—GLOBAL for all groups.
- Command structure for public/admin/owner use.
- False-positive proof for normal chat (default).
- Strict mode (optional, per group) for tolerant, leet, separator, typo catching.
- Completely async, robust structure.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import MessageDeleteForbidden, UserNotParticipant

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
    def __init__(self):
        self.detector = get_detector() if get_detector else None
        self.warning_delete_tasks: Dict[int, asyncio.Task] = {}

    async def is_admin(self, chat_id: int, user_id: int) -> bool:
        try:
            member = await app.get_chat_member(chat_id, user_id)
            return getattr(member, "status", "").lower() in ("administrator", "creator")
        except UserNotParticipant:
            return False
        except:
            return False
    
    async def should_detect_abuse(self, chat_id: int) -> bool:
        if not abuse_words_db:
            return False
        config = await abuse_words_db.get_config(chat_id)
        return config.get("enabled", True)
    
    async def detect_abuse_in_message(self, text: str, strict_mode: bool = False) -> Tuple[bool, Optional[str]]:
        if not text or not self.detector or not abuse_words_db:
            return False, None
        abuse_words = await abuse_words_db.get_all_abuse_words()
        words_list = [w.get("word") for w in abuse_words]
        return self.detector.detect_abuse(text, words_list, strict_mode)

    async def send_warning_message(self, chat_id: int, message_id: int, warnings: int, username: str = "User") -> Optional[Message]:
        warning_text = (
            f"⚠️ **Warning**\n\n"
            f"**{username}**, please avoid using abusive language.\n"
            f"Your message has been deleted.\n\n"
            f"**Total Warnings:** {warnings}"
        )
        try:
            return await app.send_message(chat_id, warning_text, reply_to_message_id=message_id)
        except:
            return None

    async def schedule_warning_deletion(self, chat_id: int, msg_id: int, delay: int = 10):
        async def delete_task():
            await asyncio.sleep(delay)
            try:
                await app.delete_messages(chat_id, msg_id)
            except:
                pass
        asyncio.create_task(delete_task())

anti_abuse_manager = AntiAbuseManager()

@app.on_message(filters.text & filters.group & ~filters.bot & ~filters.service, group=5)
async def handle_message_abuse(client: Client, message: Message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        if not user_id or not abuse_words_db:
            return
        if not await anti_abuse_manager.should_detect_abuse(chat_id):
            return
        # Get config for strict mode only, everything else is global
        config = await abuse_words_db.get_config(chat_id)
        strict_mode = config.get("strict_mode", False)
        delete_warning = config.get("delete_warning", True)
        warning_delete_time = config.get("warning_delete_time", 10)
        is_detected, matched_word = await anti_abuse_manager.detect_abuse_in_message(
            message.text or message.caption or "", strict_mode
        )
        if not is_detected:
            return
        try:
            await app.delete_messages(chat_id, message.id)
        except Exception as e:
            logger.warning(f"[AntiAbuse] Error deleting: {e}")
        warnings = await abuse_words_db.add_warning(chat_id, user_id, matched_word, (message.text or "")[:100])
        await abuse_words_db.log_abuse_detection(chat_id, user_id, matched_word, (message.text or "")[:100], "delete_only")
        username = message.from_user.first_name if message.from_user else "User"
        warning_msg = await anti_abuse_manager.send_warning_message(chat_id, message.id, warnings, username)
        if delete_warning and warning_msg:
            await anti_abuse_manager.schedule_warning_deletion(chat_id, warning_msg.id, warning_delete_time)
    except Exception as e:
        logger.error(f"[AntiAbuse] Error: {e}")

# GROUP 4: COMMAND HANDLERS

@app.on_message(filters.command("antiabuse") & filters.group, group=4)
async def antiabuse_command(client: Client, message: Message):
    try:
        if not abuse_words_db:
            return await message.reply_text("❌ **Database not initialized**")
        is_admin = await anti_abuse_manager.is_admin(message.chat.id, message.from_user.id)
        if not is_admin:
            return await message.reply_text("❌ **Admin only**")
        parts = message.text.strip().split()
        if len(parts) == 1:
            config = await abuse_words_db.get_config(message.chat.id)
            stats = await abuse_words_db.get_abuse_stats(message.chat.id)
            return await message.reply_text(
                f"🚫 **Anti-Abuse Status**\n\n"
                f"**Enabled:** {'✅ Yes' if config.get('enabled') else '❌ No'}\n"
                f"**Strict Mode:** {'✅ Yes' if config.get('strict_mode') else '❌ No'}\n\n"
                f"**Stats:**\n"
                f"📊 Words: {stats.get('total_abuse_words', 0)}\n"
                f"📊 Violations: {stats.get('total_violations', 0)}\n"
                f"📊 Warned Users: {stats.get('users_with_warnings', 0)}\n"
            )
        cmd = parts[1].lower()
        if cmd in ("on", "enable"):
            await abuse_words_db.toggle_enabled(message.chat.id, True)
            await message.reply_text("✅ **Anti-abuse enabled**")
        elif cmd in ("off", "disable"):
            await abuse_words_db.toggle_enabled(message.chat.id, False)
            await message.reply_text("❌ **Anti-abuse disabled**")
        elif cmd == "strict":
            if len(parts) < 3:
                return await message.reply_text("❌ **Usage:** `/antiabuse strict yes/no`")
            strict = parts[2].lower().startswith('y')
            config = await abuse_words_db.get_config(message.chat.id)
            config["strict_mode"] = strict
            await abuse_words_db.set_config(message.chat.id, config)
            await message.reply_text(f"✅ **Strict mode {'on' if strict else 'off'}**")
        else:
            await message.reply_text(
                "**Commands:**\n"
                "`/antiabuse` - Status\n"
                "`/antiabuse on/enable` - Enable\n"
                "`/antiabuse off/disable` - Disable\n"
                "`/antiabuse strict yes/no` - Strict mode"
            )
    except Exception as e:
        await message.reply_text(f"❌ **Error:** {e}")

@app.on_message(filters.command(["addabuse", "addbadword"]) & filters.group, group=4)
async def addabuse_command(client: Client, message: Message):
    """Owner adds a word globally."""
    try:
        if message.from_user.id != OWNER_ID:
            return await message.reply_text("❌ Owner only")
        if not abuse_words_db:
            return await message.reply_text("❌ Not initialized")
        parts = message.text.strip().split()
        if len(parts) < 2:
            return await message.reply_text("❌ **Usage:** `/addabuse word`")
        word = parts[1].lower()
        severity = parts[2] if len(parts) > 2 and parts[2] in ("low", "medium", "high") else "high"
        if await abuse_words_db.add_abuse_word(word, severity, [], message.from_user.id):
            await message.reply_text(f"✅ Word added: `{word}`\nDetected globally.")
        else:
            await message.reply_text(f"❌ Word exists or error: `{word}`")
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")

@app.on_message(filters.command(["addmany", "addbulkwords", "addabusewords"]) & filters.group, group=4)
async def addmanyabuse_command(client: Client, message: Message):
    """Owner adds several words at once."""
    try:
        if message.from_user.id != OWNER_ID:
            return await message.reply_text("❌ Owner only")
        if not abuse_words_db:
            return await message.reply_text("❌ Not initialized")
        words = message.text.strip().split()[1:]
        if not words:
            return await message.reply_text("❌ Usage: `/addmany word1 word2 ...`")
        success, fail = [], []
        for word in words:
            added = await abuse_words_db.add_abuse_word(word, "high", [], message.from_user.id)
            (success if added else fail).append(word)
        t = ""
        if success:
            t += f"✅ Added: {', '.join(success)}\n"
        if fail:
            t += f"❌ Already existed: {', '.join(fail)}"
        await message.reply_text(t)
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")

@app.on_message(filters.command("listabuse") & filters.group, group=4)
async def listabuse_command(client: Client, message: Message):
    try:
        if not abuse_words_db:
            return await message.reply_text("❌ Not initialized")
        words = await abuse_words_db.get_all_abuse_words()
        if not words:
            return await message.reply_text("❌ None configured")
        word_list = [f"{i+1}. `{w['word']}` ({w.get('severity', 'high')})" for i, w in enumerate(words[:40])]
        text = f"📋 **Word List** ({len(words)})\n\n" + "\n".join(word_list)
        if len(words) > 40:
            text += f"\n... and {len(words)-40} more"
        await message.reply_text(text)
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")

@app.on_message(filters.command("clearabuse") & filters.group, group=4)
async def clearabuse_command(client: Client, message: Message):
    try:
        if not abuse_words_db:
            return await message.reply_text("❌ Not initialized")
        if not (await anti_abuse_manager.is_admin(message.chat.id, message.from_user.id)):
            return await message.reply_text("❌ Admin only")
        if message.reply_to_message and message.reply_to_message.from_user:
            user_id = message.reply_to_message.from_user.id
            username = message.reply_to_message.from_user.first_name
            await abuse_words_db.clear_warnings(message.chat.id, user_id)
            await message.reply_text(f"✅ Cleared warnings for {username}")
        else:
            await message.reply_text("❌ Reply to a user's message")
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")

__all__ = [
    "handle_message_abuse",
    "antiabuse_command",
    "addabuse_command",
    "addmanyabuse_command",
    "listabuse_command",
    "clearabuse_command",
    "AntiAbuseManager"
]
