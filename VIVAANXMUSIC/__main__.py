"""
VivaanXMusic Bot - Main Entry Point
Handles bot initialization, plugin loading, and startup sequence.

Author: Vivaan Devs
Version: 4.0
"""

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


async def load_default_abuse_words():
    """
    Load default abuse words from JSON on first startup.
    Only loads words that don't already exist in database.
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
            f"📋 Abuse Words: {loaded_count} new, "
            f"{skipped_count} existing (Total: {total_words})"
        )
        
    except Exception as e:
        LOGGER(__name__).error(f"❌ Failed to load abuse words: {e}")


async def initialize_edit_tracker_database():
    """
    Initialize edit tracker database with proper indexes.
    This ensures optimal query performance for anti-edit feature.
    """
    try:
        from VIVAANXMUSIC.mongo.edit_tracker_db import initialize_database
        
        LOGGER(__name__).info("🔧 Creating database indexes for anti-edit system...")
        await initialize_database()
        LOGGER(__name__).info("✅ Edit tracker database initialized with indexes")
        
    except ImportError:
        LOGGER(__name__).warning("⚠️ Edit tracker database module not found - anti-edit may not work")
    except Exception as e:
        LOGGER(__name__).error(f"❌ Edit tracker database initialization failed: {e}")


async def initialize_security_systems():
    """
    Initialize all security systems including anti-edit and anti-abuse.
    Sets up database indexes and loads default configurations.
    """
    try:
        # Initialize edit tracker database
        await initialize_edit_tracker_database()
        
        # Load default abuse words
        await load_default_abuse_words()
        
        LOGGER(__name__).info("✅ All security systems initialized successfully")
        
    except Exception as e:
        LOGGER(__name__).error(f"❌ Security systems initialization error: {e}")
        # Non-critical, continue bot startup


async def init():
    """
    Main initialization function for VivaanXMusic Bot.
    Handles all startup tasks including:
    - Session validation
    - Cookie loading
    - Security system initialization
    - Plugin loading
    - Bot/userbot startup
    """
    
    # ==================== SESSION VALIDATION ====================
    if (
        not config.STRING1
        and not config.STRING2
        and not config.STRING3
        and not config.STRING4
        and not config.STRING5
    ):
        LOGGER(__name__).error(
            "❌ Assistant session not filled. Please provide at least one Pyrogram session string."
        )
        exit()
    
    LOGGER("VIVAANXMUSIC").info("🚀 Starting VivaanXMusic Bot...")
    
    # ==================== COOKIE HANDLER ====================
    try:
        LOGGER("VIVAANXMUSIC").info("🍪 Fetching YouTube cookies...")
        await fetch_and_store_cookies()
        LOGGER("VIVAANXMUSIC").info("✅ YouTube cookies loaded successfully")
    except Exception as e:
        LOGGER("VIVAANXMUSIC").warning(f"⚠️ Cookie error: {e}")
    
    # ==================== SECURITY SYSTEMS ====================
    LOGGER("VIVAANXMUSIC").info("🔒 Initializing security systems...")
    try:
        await initialize_security_systems()
    except Exception as e:
        LOGGER("VIVAANXMUSIC").error(f"❌ Security initialization failed: {e}")
        # Continue anyway - security is non-critical for music playback
    
    # ==================== SUDO USERS ====================
    await sudo()
    
    # ==================== BANNED USERS ====================
    try:
        LOGGER("VIVAANXMUSIC").info("📋 Loading banned users...")
        users = await get_gbanned()
        for user_id in users:
            BANNED_USERS.add(user_id)
        users = await get_banned_users()
        for user_id in users:
            BANNED_USERS.add(user_id)
        LOGGER("VIVAANXMUSIC").info(f"✅ Loaded {len(BANNED_USERS)} banned users")
    except Exception as e:
        LOGGER("VIVAANXMUSIC").warning(f"⚠️ Error loading banned users: {e}")
    
    # ==================== START BOT CLIENT ====================
    LOGGER("VIVAANXMUSIC").info("🤖 Starting bot client...")
    await app.start()
    LOGGER("VIVAANXMUSIC").info("✅ Bot client started")
    
    # ==================== LOAD PLUGINS ====================
    LOGGER("VIVAANXMUSIC.plugins").info("📦 Loading plugins...")
    for all_module in ALL_MODULES:
        try:
            importlib.import_module("VIVAANXMUSIC.plugins" + all_module)
        except Exception as e:
            LOGGER("VIVAANXMUSIC.plugins").error(f"❌ Failed to load {all_module}: {e}")
    
    LOGGER("VIVAANXMUSIC.plugins").info("✅ All modules loaded successfully")
    
    # ==================== LOAD SECURITY PLUGINS ====================
    # Explicitly import security plugins to ensure handlers are registered
    try:
        LOGGER("VIVAANXMUSIC.plugins").info("🔒 Loading security plugins...")
        
        # Import anti-edit plugin
        try:
            import VIVAANXMUSIC.plugins.admins.anti_edit
            LOGGER("VIVAANXMUSIC.plugins").info("  ✓ Anti-edit plugin loaded")
        except ImportError:
            LOGGER("VIVAANXMUSIC.plugins").warning("  ⚠️ Anti-edit plugin not found")
        except Exception as e:
            LOGGER("VIVAANXMUSIC.plugins").error(f"  ✗ Anti-edit error: {e}")
        
        # Import anti-abuse plugin
        try:
            import VIVAANXMUSIC.plugins.admins.anti_abuse
            LOGGER("VIVAANXMUSIC.plugins").info("  ✓ Anti-abuse plugin loaded")
        except ImportError:
            LOGGER("VIVAANXMUSIC.plugins").warning("  ⚠️ Anti-abuse plugin not found")
        except Exception as e:
            LOGGER("VIVAANXMUSIC.plugins").error(f"  ✗ Anti-abuse error: {e}")
        
        LOGGER("VIVAANXMUSIC.plugins").info("✅ Security plugins loaded")
        
    except Exception as e:
        LOGGER("VIVAANXMUSIC.plugins").error(f"❌ Security plugins loading failed: {e}")
    
    # ==================== START USERBOT ====================
    LOGGER("VIVAANXMUSIC").info("👤 Starting userbot client...")
    await userbot.start()
    LOGGER("VIVAANXMUSIC").info("✅ Userbot client started")
    
    # ==================== START PYTGCALLS ====================
    LOGGER("VIVAANXMUSIC").info("📞 Starting PyTgCalls...")
    await JARVIS.start()
    
    # Test voice chat connection
    try:
        await JARVIS.stream_call(
            "http://docs.evostream.com/sample_content/assets/sintel1m720p.mp4"
        )
    except NoActiveGroupCall:
        LOGGER("VIVAANXMUSIC").error(
            "❌ Please turn on the voice chat in your log group/channel.\n"
            "VivaanXMusic Bot stopped."
        )
        exit()
    except Exception as e:
        LOGGER("VIVAANXMUSIC").warning(f"⚠️ Voice chat test warning: {e}")
    
    # ==================== FINALIZE STARTUP ====================
    await JARVIS.decorators()
    
    LOGGER("VIVAANXMUSIC").info(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ VivaanXMusic Bot Started Successfully!\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    # ==================== IDLE STATE ====================
    await idle()
    
    # ==================== SHUTDOWN ====================
    LOGGER("VIVAANXMUSIC").info("🛑 Shutting down VivaanXMusic Bot...")
    await app.stop()
    await userbot.stop()
    LOGGER("VIVAANXMUSIC").info("👋 VivaanXMusic Bot stopped. Goodbye!")


if __name__ == "__main__":
    """Entry point for the bot."""
    try:
        asyncio.get_event_loop().run_until_complete(init())
    except KeyboardInterrupt:
        LOGGER("VIVAANXMUSIC").info("🛑 Bot stopped by user (Ctrl+C)")
    except Exception as e:
        LOGGER("VIVAANXMUSIC").critical(f"💥 Fatal error during startup: {e}", exc_info=True)
