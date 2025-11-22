import asyncio
import logging
from typing import Optional, Dict, Set
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
    # edit_exempt_users is a dict mapping chat_id to set of exempt user_ids
    edit_exempt_users: Dict[int, Set[int]] = {}

    def __init__(self):
        self.pending_tasks: Dict[str, asyncio.Task] = {}

    async def is_admin_or_owner(self, chat_id: int, user_id: int) -> bool:
        if user_id == OWNER_ID:
            return True
        try:
            member = await app.get_chat_member(chat_id, user_id)
            return str(getattr(member, "status", "")).lower() in ("administrator", "creator")
        except (UserNotParticipant, Exception):
            return False

    async def should_delete_edit(self, chat_id: int, user_id: int) -> bool:
        if not edit_tracker_db:
            return False
        config = await edit_tracker_db.get_config(chat_id)
        if not config.get("enabled", True):
            return False
        # Exempt if in per-group-authorized set
        exempt = AntiEditManager.edit_exempt_users.get(chat_id, set())
        if user_id in exempt:
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
                    edited_text=text
                )
        except Exception as e:
            logger.error(f"[AntiEdit] Error logging edit: {e}")

anti_edit_manager = AntiEditManager()

def is_real_edit(message: Message) -> bool:
    if not message or not message.from_user:
        return False
    has_content = bool(message.text or message.caption)
    is_service = getattr(message, "service", False)
    is_reply = getattr(message, "reply_to_message", None)
    is_forward = getattr(message, "forward_from", None) or getattr(message, "forward_from_chat", None)
    is_via_bot = getattr(message, "via_bot", None)
    is_media = getattr(message, "media_group_id", None) or message.document or message.photo or message.audio or message.video
    is_game = message.game if hasattr(message, 'game') else False
    # If editing a bot message, is_bot is True
    is_bot_edit = message.from_user.is_bot
    if (not has_content or is_service or is_reply or is_forward or is_via_bot
        or is_media or is_game or is_bot_edit):
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

@app.on_message(filters.command("editauth") & filters.group)
async def editauth_command(client: Client, message: Message):
    """Reply with /editauth to bypass anti-edit for a user."""
    if not (await anti_edit_manager.is_admin_or_owner(message.chat.id, message.from_user.id)):
        return await message.reply_text("❌ **Admin only**", quote=True)
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.reply_text("❌ **Reply to a user's message**")
    chat_id = message.chat.id
    target_user = message.reply_to_message.from_user.id
    # Add to exempt list for this group
    AntiEditManager.edit_exempt_users.setdefault(chat_id, set()).add(target_user)
    await message.reply_text("✅ User is now authorized to edit messages in this group and will no longer be deleted.")

@app.on_message(filters.command(["deleditauth", "editauthremove", "editauthdel"]) & filters.group)
async def editauth_remove_command(client: Client, message: Message):
    """Remove anti-edit bypass (reply to user)."""
    if not (await anti_edit_manager.is_admin_or_owner(message.chat.id, message.from_user.id)):
        return await message.reply_text("❌ **Admin only**", quote=True)
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.reply_text("❌ **Reply to a user's message**")
    chat_id = message.chat.id
    target_user = message.reply_to_message.from_user.id
    AntiEditManager.edit_exempt_users.setdefault(chat_id, set()).discard(target_user)
    await message.reply_text("❎ User is no longer authorized to edit in this group.")

@app.on_message(filters.command("editauthlist") & filters.group)
async def editauth_list_command(client: Client, message: Message):
    """Show all edit-authorized users in the current group."""
    if not (await anti_edit_manager.is_admin_or_owner(message.chat.id, message.from_user.id)):
        return await message.reply_text("❌ **Admin only**", quote=True)
    chat_id = message.chat.id
    user_ids = AntiEditManager.edit_exempt_users.get(chat_id, set())
    if not user_ids:
        return await message.reply_text("❌ No users are authorized to edit in this group.")
    users_mention = []
    for uid in user_ids:
        users_mention.append(f"[{uid}](tg://user?id={uid})")
    await message.reply_text("📝 **Authorized editors:**\n" + "\n".join(users_mention))

__all__ = [
    "handle_edited_message",
    "editauth_command",
    "editauth_remove_command",
    "editauth_list_command",
    "AntiEditManager"
]
