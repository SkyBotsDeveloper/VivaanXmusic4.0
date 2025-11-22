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
    """
    Returns True only for real text/caption edits by a human, not for:
    - reactions (emoji add/remove)
    - bot replies
    - system/service/forward/media/album/game edits
    """
    if not message or not message.from_user:
        return False
    # Reactions/emoji edits: no change in text/caption, only edit_date changes
    original_text, original_caption = getattr(message, "text", None), getattr(message, "caption", None)
    if not (original_text or original_caption):
        return False
    # Service/system/bot/media/game/etc
    if (
        getattr(message, "service", False)
        or getattr(message, "reply_to_message", None)
        or getattr(message, "forward_from", None)
        or getattr(message, "forward_from_chat", None)
        or getattr(message, "via_bot", None)
        or getattr(message, "media_group_id", None)
        or getattr(message, "document", None)
        or getattr(message, "photo", None)
        or getattr(message, "audio", None)
        or getattr(message, "video", None)
        or getattr(message, "game", None)
        or message.from_user.is_bot
        or (hasattr(message, "new_chat_members") and message.new_chat_members)
        or (hasattr(message, "left_chat_member") and message.left_chat_member)
        or (hasattr(message, "pinned_message") and message.pinned_message)
    ):
        return False
    # If only text/caption and from human: allow through for checking
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
    if not (await anti_edit_manager.is_admin_or_owner(message.chat.id, message.from_user.id)):
        return await message.reply_text("❌ **Admin only**", quote=True)
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.reply_text("❌ **Reply to user's message**")
    chat_id = message.chat.id
    target_user = message.reply_to_message.from_user.id
    AntiEditManager.edit_exempt_users.setdefault(chat_id, set()).add(target_user)
    await message.reply_text("✅ User is now allowed to edit messages in this group (immune to anti-edit locks).")

@app.on_message(filters.command(["deleditauth", "editauthremove", "editauthdel"]) & filters.group)
async def editauth_remove_command(client: Client, message: Message):
    if not (await anti_edit_manager.is_admin_or_owner(message.chat.id, message.from_user.id)):
        return await message.reply_text("❌ **Admin only**", quote=True)
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.reply_text("❌ **Reply to user's message**")
    chat_id = message.chat.id
    target_user = message.reply_to_message.from_user.id
    AntiEditManager.edit_exempt_users.setdefault(chat_id, set()).discard(target_user)
    await message.reply_text("❎ User is no longer bypassing anti-edit.")

@app.on_message(filters.command("editauthlist") & filters.group)
async def editauth_list_command(client: Client, message: Message):
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
