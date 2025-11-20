import asyncio
import importlib
import json
from pathlib import Path

from pyrogram import idle
from pytgcalls.exceptions import NoActiveGroupCall

import config
from VIVAANXMUSIC import LOGGER, app, userbot
from VIVAANXMUSIC.core.call import JARVIS
from VIVAANXMUSIC.misc import sudo
from VIVAANXMUSIC.plugins import ALL_MODULES
from VIVAANXMUSIC.utils.database import get_banned_users, get_gbanned
from VIVAANXMUSIC.utils.cookie_handler import fetch_and_store_cookies
from config import BANNED_USERS

# Import security system initializer
from VIVAANXMUSIC import initialize_security_systems


async def load_default_abuse_words():
    """
    Load default abuse words from JSON on first startup
    Only loads words that don't already exist in database
    """
    try:
        from VIVAANXMUSIC.mongo.abuse_words_db import abuse_words_db
        
        json_path = Path("VIVAANXMUSIC/assets/abuse_words.json")
        
        if not json_path.exists():
            LOGGER(__name__).warning("⚠️ Default abuse_words.json not found - skipping word loading")
            return
        
        # Read JSON file
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        loaded_count = 0
        skipped_count = 0
        
        # Load each word
        for entry in data.get("default_words", []):
            word = entry.get("word")
            severity = entry.get("severity", "high")
            
            if not word:
                continue
            
            # Check if word already exists
            exists = await abuse_words_db.word_exists(word)
            
            if not exists:
                # Add word to database
                success = await abuse_words_db.add_abuse_word(
                    word=word,
                    severity=severity,
                    patterns=[],
                    added_by=0  # System added
                )
                
                if success:
                    loaded_count += 1
            else:
                skipped_count += 1
        
        total_words = len(data.get("default_words", []))
        LOGGER(__name__).info(
            f"📋 Abuse Words Loader: {loaded_count} new words added, "
            f"{skipped_count} already existed (Total: {total_words})"
        )
        
    except Exception as e:
        LOGGER(__name__).error(f"❌ Failed to load default abuse words: {e}")


async def init():
    if (
        not config.STRING1
        and not config.STRING2
        and not config.STRING3
        and not config.STRING4
        and not config.STRING5
    ):
        LOGGER(__name__).error("ᴀssɪsᴛᴀɴᴛ sᴇssɪᴏɴ ɴᴏᴛ ғɪʟʟᴇᴅ, ᴘʟᴇᴀsᴇ ғɪʟʟ ᴀ ᴘʏʀᴏɢʀᴀᴍ sᴇssɪᴏɴ...")
        exit()

    # ✅ Try to fetch cookies at startup
    try:
        await fetch_and_store_cookies()
        LOGGER("VIVAANXMUSIC").info("ʏᴏᴜᴛᴜʙᴇ ᴄᴏᴏᴋɪᴇs ʟᴏᴀᴅᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ ✅")
    except Exception as e:
        LOGGER("VIVAANXMUSIC").warning(f"⚠️ᴄᴏᴏᴋɪᴇ ᴇʀʀᴏʀ: {e}")

    # ✅ Initialize Security Systems (Anti-Edit & Anti-Abuse)
    LOGGER("VIVAANXMUSIC").info("🔒 Initializing security systems...")
    try:
        await initialize_security_systems()
        LOGGER("VIVAANXMUSIC").info("✅ Security systems initialized successfully")
    except Exception as e:
        LOGGER("VIVAANXMUSIC").error(f"❌ Security system initialization failed: {e}")
        # Continue anyway - non-critical for music bot core functionality

    # ✅ Load default abuse words
    LOGGER("VIVAANXMUSIC").info("📋 Loading default abuse words...")
    try:
        await load_default_abuse_words()
        LOGGER("VIVAANXMUSIC").info("✅ Abuse words loaded successfully")
    except Exception as e:
        LOGGER("VIVAANXMUSIC").error(f"❌ Abuse words loading failed: {e}")

    await sudo()

    try:
        users = await get_gbanned()
        for user_id in users:
            BANNED_USERS.add(user_id)
        users = await get_banned_users()
        for user_id in users:
            BANNED_USERS.add(user_id)
    except:
        pass

    await app.start()
    
    # Load all modules
    for all_module in ALL_MODULES:
        importlib.import_module("VIVAANXMUSIC.plugins" + all_module)

    LOGGER("VIVAANXMUSIC.plugins").info("ᴀɴɴɪᴇ's ᴍᴏᴅᴜʟᴇs ʟᴏᴀᴅᴇᴅ...")
    
    # ✅ Explicitly import security plugins to ensure handlers are registered
    try:
        import VIVAANXMUSIC.plugins.admins.anti_edit
        import VIVAANXMUSIC.plugins.admins.anti_abuse
        LOGGER("VIVAANXMUSIC.plugins").info("🔒 Security plugins loaded (anti-edit & anti-abuse)")
    except ImportError as e:
        LOGGER("VIVAANXMUSIC.plugins").warning(f"⚠️ Security plugins not found: {e}")
    except Exception as e:
        LOGGER("VIVAANXMUSIC.plugins").error(f"❌ Error loading security plugins: {e}")

    await userbot.start()
    await JARVIS.start()

    try:
        await JARVIS.stream_call("http://docs.evostream.com/sample_content/assets/sintel1m720p.mp4")
    except NoActiveGroupCall:
        LOGGER("VIVAANXMUSIC").error(
            "ᴘʟᴇᴀsᴇ ᴛᴜʀɴ ᴏɴ ᴛʜᴇ ᴠᴏɪᴄᴇ ᴄʜᴀᴛ ᴏғ ʏᴏᴜʀ ʟᴏɢ ɢʀᴏᴜᴘ/ᴄʜᴀɴɴᴇʟ.\n\nᴀɴɴɪᴇ ʙᴏᴛ sᴛᴏᴘᴘᴇᴅ..."
        )
        exit()
    except:
        pass

    await JARVIS.decorators()
    LOGGER("VIVAANXMUSIC").info(
        "\x41\x6e\x6e\x69\x65\x20\x4d\x75\x73\x69\x63\x20\x52\x6f\x62\x6f\x74\x20\x53\x74\x61\x72\x74\x65\x64\x20\x53\x75\x63\x63\x65\x73\x73\x66\x75\x6c\x6c\x79\x2e\x2e\x2e"
    )
    await idle()
    await app.stop()
    await userbot.stop()
    LOGGER("VIVAANXMUSIC").info("sᴛᴏᴘᴘɪɴɢ ᴀɴɴɪᴇ ᴍᴜsɪᴄ ʙᴏᴛ ...")


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(init())
