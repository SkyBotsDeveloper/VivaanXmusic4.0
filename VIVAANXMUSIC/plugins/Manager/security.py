"""
-------------------------------------------------------------------------
Group Security Manager - Bio checking, warnings, and user whitelisting.

• /security     – configure bio checking settings (warning limit & action)
• /trust        – whitelist a user from bio checks
• /untrust      – remove user from whitelist
• /trusted      – show all whitelisted users
• /forgive      – clear user warnings
• /bioscan      – manually scan a user's bio
• /secstats     – show security statistics for the group

Auto bio-check runs on every message, warning users with links in bios.
All commands accept reply, @username, or user-ID with graceful handling.
-------------------------------------------------------------------------
"""

import asyncio
from typing import Optional, Dict

from pyrogram import filters, enums
from pyrogram.errors import ChatAdminRequired, UserAdminInvalid, RPCError
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from datetime import datetime, timedelta

from VIVAANXMUSIC import app
from VIVAANXMUSIC.misc import SUDOERS
from VIVAANXMUSIC.utils.decorator import admin_required
from VIVAANXMUSIC.utils.security_check import check_bio, get_target_user, clean_bio_preview, format_links_list, check_bio_detailed
from VIVAANXMUSIC.utils.permissions import mention
from VIVAANXMUSIC.mongo.group_security_db import gsdb


# ────────────────────────────────────────────────────────────
# Constants & Configuration Cache
# ────────────────────────────────────────────────────────────
_config_cache: Dict[int, dict] = {}

_USAGES = {
    "security":  "/security — configure bio checking settings",
    "trust":     "/trust @user — or reply with /trust",
    "untrust":   "/untrust @user — or reply with /untrust",
    "trusted":   "/trusted — show whitelisted users",
    "forgive":   "/forgive @user — or reply with /forgive",
    "bioscan":   "/bioscan @user — or reply with /bioscan",
    "secstats":  "/secstats — show security statistics",
}

def _usage(cmd: str) -> str:
    return _USAGES.get(cmd, "Invalid usage.")

async def _info(msg: Message, text: str):
    await msg.reply_text(text)

def _format_success(action: str, msg: Message, uid: int, name: str, extra: Optional[str] = None) -> str:
    chat_name = msg.chat.title
    user_m    = mention(uid, name)
    admin_m   = mention(msg.from_user.id, msg.from_user.first_name)
    text = (
        f"» {action} ɪɴ {chat_name}\n"
        f" ᴜsᴇʀ  : {user_m}\n"
        f" ᴀᴅᴍɪɴ : {admin_m}"
    )
    if extra:
        text += f"\n{extra}"
    return text


# ────────────────────────────────────────────────────────────
# /security - Configure bio checking
# ────────────────────────────────────────────────────────────
@app.on_message(filters.command(["security", "biosecurity"]) & filters.group)
@admin_required("can_restrict_members")
async def security_settings(client, message: Message):
    """Configure group security settings"""
    chat_id = message.chat.id
    config = await gsdb.get_config(chat_id)
    bio_config = config.get("bio_check", {})
    
    # Build keyboard
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("5 ᴡᴀʀɴɪɴɢs", callback_data="sec_limit_5"),
            InlineKeyboardButton("10 ᴡᴀʀɴɪɴɢs", callback_data="sec_limit_10"),
        ],
        [
            InlineKeyboardButton("15 ᴡᴀʀɴɪɴɢs", callback_data="sec_limit_15"),
        ],
        [
            InlineKeyboardButton("🔇 ᴍᴜᴛᴇ", callback_data="sec_action_mute"),
            InlineKeyboardButton("🚫 ʙᴀɴ", callback_data="sec_action_ban"),
        ],
        [
            InlineKeyboardButton("✅ sᴀᴠᴇ", callback_data="sec_save"),
            InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="sec_cancel"),
        ]
    ])
    
    status = "ᴇɴᴀʙʟᴇᴅ ✅" if bio_config.get("enabled", True) else "ᴅɪsᴀʙʟᴇᴅ ❌"
    
    await message.reply_text(
        f"🛡️ **ɢʀᴏᴜᴘ sᴇᴄᴜʀɪᴛʏ sᴇᴛᴛɪɴɢs**\n\n"
        f"**ʙɪᴏ ᴄʜᴇᴄᴋɪɴɢ:** {status}\n"
        f"**ᴡᴀʀɴɪɴɢ ʟɪᴍɪᴛ:** `{bio_config.get('warning_limit', 5)}`\n"
        f"**ᴀᴄᴛɪᴏɴ:** `{bio_config.get('action', 'mute').upper()}`\n\n"
        f"**ᴄᴏɴғɪɢᴜʀᴇ ɴᴇᴡ sᴇᴛᴛɪɴɢs ʙᴇʟᴏᴡ:**",
        reply_markup=keyboard
    )


@app.on_callback_query(filters.regex(r"^sec_"))
async def security_callback(client, callback: CallbackQuery):
    """Handle security configuration callbacks"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    
    # Verify admin
    try:
        member = await callback.message.chat.get_member(user_id)
        if member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
            if user_id not in SUDOERS:
                return await callback.answer("❌ ᴀᴅᴍɪɴ ᴏɴʟʏ!", show_alert=True)
    except Exception:
        return await callback.answer("❌ ᴇʀʀᴏʀ ᴄʜᴇᴄᴋɪɴɢ ᴘᴇʀᴍɪssɪᴏɴs", show_alert=True)
    
    # Initialize cache
    if chat_id not in _config_cache:
        config = await gsdb.get_config(chat_id)
        bio_cfg = config.get("bio_check", {})
        _config_cache[chat_id] = {
            "warning_limit": bio_cfg.get("warning_limit", 5),
            "action": bio_cfg.get("action", "mute")
        }
    
    action = callback.data.split("_")[1]
    
    if action == "limit":
        limit = int(callback.data.split("_")[2])
        _config_cache[chat_id]["warning_limit"] = limit
        await callback.answer(f"✅ sᴇᴛ ᴛᴏ {limit} ᴡᴀʀɴɪɴɢs")
    
    elif action == "action":
        act = callback.data.split("_")[2]
        _config_cache[chat_id]["action"] = act
        await callback.answer(f"✅ ᴀᴄᴛɪᴏɴ: {act.upper()}")
    
    elif action == "save":
        # Save to database
        await gsdb.update_bio_config(
            chat_id,
            _config_cache[chat_id]["warning_limit"],
            _config_cache[chat_id]["action"]
        )
        
        await callback.message.edit_text(
            f"✅ **sᴇᴄᴜʀɪᴛʏ sᴇᴛᴛɪɴɢs sᴀᴠᴇᴅ**\n\n"
            f"**ᴡᴀʀɴɪɴɢ ʟɪᴍɪᴛ:** `{_config_cache[chat_id]['warning_limit']}`\n"
            f"**ᴀᴄᴛɪᴏɴ:** `{_config_cache[chat_id]['action'].upper()}`\n\n"
            f"ʙɪᴏ ᴄʜᴇᴄᴋɪɴɢ ɪs ɴᴏᴡ ᴀᴄᴛɪᴠᴇ."
        )
        
        del _config_cache[chat_id]
        return await callback.answer("✅ ᴄᴏɴғɪɢᴜʀᴀᴛɪᴏɴ sᴀᴠᴇᴅ!", show_alert=True)
    
    elif action == "cancel":
        if chat_id in _config_cache:
            del _config_cache[chat_id]
        await callback.message.delete()
        return await callback.answer("❌ ᴄᴀɴᴄᴇʟʟᴇᴅ")
    
    # Update display
    await callback.message.edit_text(
        f"🛡️ **ɢʀᴏᴜᴘ sᴇᴄᴜʀɪᴛʏ sᴇᴛᴛɪɴɢs**\n\n"
        f"**ᴡᴀʀɴɪɴɢ ʟɪᴍɪᴛ:** `{_config_cache[chat_id]['warning_limit']}`\n"
        f"**ᴀᴄᴛɪᴏɴ:** `{_config_cache[chat_id]['action'].upper()}`\n\n"
        f"**ᴄᴏɴғɪɢᴜʀᴇ ᴏʀ sᴀᴠᴇ:**",
        reply_markup=callback.message.reply_markup
    )


# ────────────────────────────────────────────────────────────
# /trust - Whitelist user
# ────────────────────────────────────────────────────────────
@app.on_message(filters.command(["trust", "whitelist"]) & filters.group)
@admin_required("can_restrict_members")
async def trust_user(client, message: Message):
    """Whitelist a user from bio checks"""
    if len(message.command) == 1 and not message.reply_to_message:
        return await _info(message, _usage("trust"))
    
    target = await get_target_user(message)
    
    if not target:
        return await message.reply_text(
            "❌ **ᴜsᴀɢᴇ:** ʀᴇᴘʟʏ ᴛᴏ ᴜsᴇʀ ᴏʀ ᴜsᴇ:\n"
            "`/trust @username` ᴏʀ `/trust user_id`"
        )
    
    # Check if already whitelisted
    if await gsdb.is_whitelisted(message.chat.id, target.id):
        return await _info(message, "ᴜsᴇʀ ɪs ᴀʟʀᴇᴀᴅʏ ᴛʀᴜsᴛᴇᴅ.")
    
    await gsdb.add_whitelist(message.chat.id, target.id, target.username)
    await gsdb.clear_warnings(message.chat.id, target.id)
    
    await message.reply_text(
        _format_success(
            "ᴛʀᴜsᴛᴇᴅ ᴜsᴇʀ",
            message,
            target.id,
            target.first_name,
            "sᴛᴀᴛᴜs: ᴇxᴇᴍᴘᴛ ғʀᴏᴍ ʙɪᴏ ᴄʜᴇᴄᴋs\n_ᴘʀᴇᴠɪᴏᴜs ᴡᴀʀɴɪɴɢs ᴄʟᴇᴀʀᴇᴅ_"
        )
    )


# ────────────────────────────────────────────────────────────
# /untrust - Remove from whitelist
# ────────────────────────────────────────────────────────────
@app.on_message(filters.command(["untrust", "unwhitelist"]) & filters.group)
@admin_required("can_restrict_members")
async def untrust_user(client, message: Message):
    """Remove user from whitelist"""
    if len(message.command) == 1 and not message.reply_to_message:
        return await _info(message, _usage("untrust"))
    
    target = await get_target_user(message)
    
    if not target:
        return await message.reply_text(
            "❌ **ᴜsᴀɢᴇ:** ʀᴇᴘʟʏ ᴛᴏ ᴜsᴇʀ ᴏʀ ᴜsᴇ:\n"
            "`/untrust @username` ᴏʀ `/untrust user_id`"
        )
    
    # Check if whitelisted
    if not await gsdb.is_whitelisted(message.chat.id, target.id):
        return await _info(message, "ᴜsᴇʀ ɪs ɴᴏᴛ ɪɴ ᴛʜᴇ ᴛʀᴜsᴛᴇᴅ ʟɪsᴛ.")
    
    await gsdb.remove_whitelist(message.chat.id, target.id)
    
    await message.reply_text(
        _format_success(
            "ᴛʀᴜsᴛ ʀᴇᴍᴏᴠᴇᴅ",
            message,
            target.id,
            target.first_name,
            "sᴛᴀᴛᴜs: ɴᴏᴡ sᴜʙᴊᴇᴄᴛ ᴛᴏ ʙɪᴏ ᴄʜᴇᴄᴋs"
        )
    )


# ────────────────────────────────────────────────────────────
# /trusted - Show whitelist
# ────────────────────────────────────────────────────────────
@app.on_message(filters.command(["trusted", "trustlist"]) & filters.group)
async def show_trusted(client, message: Message):
    """Show all trusted users"""
    users = await gsdb.get_whitelisted_users(message.chat.id)
    
    if not users:
        return await message.reply_text(
            "📋 **ɴᴏ ᴛʀᴜsᴛᴇᴅ ᴜsᴇʀs**\n\n"
            "ᴜsᴇ `/trust @username` ᴛᴏ ᴀᴅᴅ ᴜsᴇʀs ᴛᴏ ᴛʜᴇ ᴡʜɪᴛᴇʟɪsᴛ."
        )
    
    text = "📋 **ᴛʀᴜsᴛᴇᴅ ᴜsᴇʀs**\n\n"
    for idx, user in enumerate(users, 1):
        username = f"@{user.get('username')}" if user.get('username') else "ɴᴏ ᴜsᴇʀɴᴀᴍᴇ"
        text += f"`{idx}.` `{user['user_id']}` - {username}\n"
    
    text += f"\n**ᴛᴏᴛᴀʟ:** {len(users)} ᴜsᴇʀs"
    await message.reply_text(text)


# ────────────────────────────────────────────────────────────
# /forgive - Clear warnings
# ────────────────────────────────────────────────────────────
@app.on_message(filters.command(["forgive", "clearwarns"]) & filters.group)
@admin_required("can_restrict_members")
async def forgive_user(client, message: Message):
    """Clear user warnings"""
    if len(message.command) == 1 and not message.reply_to_message:
        return await _info(message, _usage("forgive"))
    
    target = await get_target_user(message)
    
    if not target:
        return await message.reply_text(
            "❌ **ᴜsᴀɢᴇ:** ʀᴇᴘʟʏ ᴛᴏ ᴜsᴇʀ ᴏʀ ᴜsᴇ:\n"
            "`/forgive @username` ᴏʀ `/forgive user_id`"
        )
    
    warnings = await gsdb.get_warnings(message.chat.id, target.id)
    
    if warnings == 0:
        return await _info(message, f"ℹ️ {mention(target.id, target.first_name)} ʜᴀs ɴᴏ ᴡᴀʀɴɪɴɢs.")
    
    await gsdb.clear_warnings(message.chat.id, target.id)
    
    await message.reply_text(
        _format_success(
            "ᴡᴀʀɴɪɴɢs ᴄʟᴇᴀʀᴇᴅ",
            message,
            target.id,
            target.first_name,
            f"ᴄʟᴇᴀʀᴇᴅ: `{warnings}` ᴡᴀʀɴɪɴɢs"
        )
    )


# ────────────────────────────────────────────────────────────
# /bioscan - Manual bio scan
# ────────────────────────────────────────────────────────────
@app.on_message(filters.command("bioscan") & filters.group)
@admin_required("can_restrict_members")
async def bioscan_command(client, message: Message):
    """Manually scan a user's bio"""
    if len(message.command) == 1 and not message.reply_to_message:
        return await _info(message, _usage("bioscan"))
    
    target = await get_target_user(message)
    
    if not target:
        return await message.reply_text(
            "❌ **ᴜsᴀɢᴇ:** ʀᴇᴘʟʏ ᴛᴏ ᴜsᴇʀ ᴏʀ ᴜsᴇ:\n"
            "`/bioscan @username` ᴏʀ `/bioscan user_id`"
        )
    
    # Detailed scan
    result = await check_bio_detailed(client, target.id)
    
    status_emoji = "🚨" if result["has_link"] else "✅"
    status_text = "ʟɪɴᴋs ғᴏᴜɴᴅ" if result["has_link"] else "ɴᴏ ʟɪɴᴋs"
    
    text = (
        f"{status_emoji} **ʙɪᴏ sᴄᴀɴ ʀᴇsᴜʟᴛ**\n\n"
        f"**ᴜsᴇʀ:** {mention(result['user_id'], result['first_name'])}\n"
        f"**sᴛᴀᴛᴜs:** {status_text}\n"
    )
    
    if result["has_link"]:
        warnings = await gsdb.get_warnings(message.chat.id, target.id)
        text += f"**ᴡᴀʀɴɪɴɢs:** `{warnings}`\n"
        text += f"\n**ʟɪɴᴋs ᴅᴇᴛᴇᴄᴛᴇᴅ:**\n{format_links_list(result['links'])}\n"
    
    text += f"\n**ʙɪᴏ:**\n`{clean_bio_preview(result['bio'], 200)}`"
    
    await message.reply_text(text, disable_web_page_preview=True)


# ────────────────────────────────────────────────────────────
# /secstats - Security statistics
# ────────────────────────────────────────────────────────────
@app.on_message(filters.command("secstats") & filters.group)
async def security_stats(client, message: Message):
    """Show security statistics"""
    config = await gsdb.get_config(message.chat.id)
    bio_config = config.get("bio_check", {})
    
    trusted_users = await gsdb.get_whitelisted_users(message.chat.id)
    warned_users = await gsdb.get_all_warned_users(message.chat.id)
    
    status = "ᴇɴᴀʙʟᴇᴅ ✅" if bio_config.get("enabled", True) else "ᴅɪsᴀʙʟᴇᴅ ❌"
    
    text = (
        f"📊 **sᴇᴄᴜʀɪᴛʏ sᴛᴀᴛɪsᴛɪᴄs**\n\n"
        f"**ɢʀᴏᴜᴘ:** {message.chat.title}\n\n"
        f"**ʙɪᴏ ᴄʜᴇᴄᴋɪɴɢ:** {status}\n"
        f"**ᴡᴀʀɴɪɴɢ ʟɪᴍɪᴛ:** `{bio_config.get('warning_limit', 5)}`\n"
        f"**ᴀᴄᴛɪᴏɴ:** `{bio_config.get('action', 'mute').upper()}`\n\n"
        f"**ᴛʀᴜsᴛᴇᴅ ᴜsᴇʀs:** `{len(trusted_users)}`\n"
        f"**ᴜsᴇʀs ᴡɪᴛʜ ᴡᴀʀɴɪɴɢs:** `{len(warned_users)}`"
    )
    
    await message.reply_text(text)


# ────────────────────────────────────────────────────────────
# AUTO BIO CHECKING (on every message)
# ────────────────────────────────────────────────────────────
@app.on_message(filters.group & ~filters.service & ~filters.bot, group=15)
async def auto_bio_check(client, message: Message):
    """Automatically check user bios when they message"""
    # Skip if no user
    if not message.from_user:
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Skip sudo users
    if user_id in SUDOERS:
        return
    
    # Skip admins
    try:
        member = await message.chat.get_member(user_id)
        if member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
            return
    except Exception:
        return
    
    # Check if whitelisted
    if await gsdb.is_whitelisted(chat_id, user_id):
        return
    
    # Get config
    config = await gsdb.get_config(chat_id)
    bio_config = config.get("bio_check", {})
    
    if not bio_config.get("enabled", True):
        return
    
    # Check bio
    has_link, bio = await check_bio(client, user_id)
    
    if not has_link:
        return
    
    # Add warning
    warn_count = await gsdb.add_warning(chat_id, user_id)
    limit = bio_config.get("warning_limit", 5)
    action = bio_config.get("action", "mute")
    
    # Check if limit reached
    if warn_count >= limit:
        try:
            if action == "ban":
                await message.chat.ban_member(user_id)
                action_emoji = "🚫"
                action_text = "ʙᴀɴɴᴇᴅ"
            else:
                await message.chat.restrict_member(
                    user_id,
                    ChatPermissions(),
                    until_date=datetime.now() + timedelta(days=366)
                )
                action_emoji = "🔇"
                action_text = "ᴍᴜᴛᴇᴅ"
            
            # Delete offending message
            try:
                await message.delete()
            except Exception:
                pass
            
            await message.reply_text(
                f"{action_emoji} **{action_text}**\n\n"
                f"**ᴜsᴇʀ:** {message.from_user.mention}\n"
                f"**ʀᴇᴀsᴏɴ:** ʟɪɴᴋ ɪɴ ʙɪᴏ\n"
                f"**ᴡᴀʀɴɪɴɢs:** `{warn_count}/{limit}`\n\n"
                f"_ʙɪᴏ ᴘʀᴇᴠɪᴇᴡ: {clean_bio_preview(bio, 80)}_",
                disable_web_page_preview=True
            )
        
        except ChatAdminRequired:
            await message.reply_text(
                "⚠️ **ᴘᴇʀᴍɪssɪᴏɴ ᴇʀʀᴏʀ**\n\n"
                "ɪ ɴᴇᴇᴅ ᴀᴅᴍɪɴ ʀɪɢʜᴛs ᴛᴏ ʀᴇsᴛʀɪᴄᴛ ᴜsᴇʀs!"
            )
        except UserAdminInvalid:
            pass  # User is admin, skip silently
        except Exception as e:
            print(f"[Security] Action error: {e}")
    
    else:
        # Issue warning
        await message.reply_text(
            f"⚠️ **ᴡᴀʀɴɪɴɢ {warn_count}/{limit}**\n\n"
            f"**ᴜsᴇʀ:** {message.from_user.mention}\n"
            f"**ʀᴇᴀsᴏɴ:** ʟɪɴᴋ ᴅᴇᴛᴇᴄᴛᴇᴅ ɪɴ ʙɪᴏ\n\n"
            f"ʀᴇᴍᴏᴠᴇ ʟɪɴᴋs ғʀᴏᴍ ʏᴏᴜʀ ʙɪᴏ ᴏʀ ғᴀᴄᴇ {action}.\n"
            f"_ʙɪᴏ ᴘʀᴇᴠɪᴇᴡ: {clean_bio_preview(bio, 80)}_",
            disable_web_page_preview=True
        )
