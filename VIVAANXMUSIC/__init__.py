from VIVAANXMUSIC.core.bot import JARVIS
from VIVAANXMUSIC.core.dir import dirr
from VIVAANXMUSIC.core.git import git
from VIVAANXMUSIC.core.userbot import Userbot
from VIVAANXMUSIC.misc import dbb, heroku

from .logging import LOGGER

dirr()
git()
dbb()
heroku()

app = JARVIS()
userbot = Userbot()


from .platforms import *

Apple = AppleAPI()
Carbon = CarbonAPI()
SoundCloud = SoundAPI()
Spotify = SpotifyAPI()
Resso = RessoAPI()
Telegram = TeleAPI()
YouTube = YouTubeAPI()


# ────────────────────────────────────────────────────────────
# Anti-Edit & Anti-Abuse System Initialization
# ────────────────────────────────────────────────────────────

import motor.motor_asyncio
import config

# MongoDB client and database
MONGO_CLIENT = motor.motor_asyncio.AsyncIOMotorClient(config.MONGO_DB_URI)
MONGO_DB = MONGO_CLIENT["VivaanXMusic"]  # ✅ Database name specified


async def initialize_security_systems():
    """
    Initialize anti-edit and anti-abuse security systems
    Must be called during bot startup
    """
    try:
        from VIVAANXMUSIC.mongo.edit_tracker_db import init_edit_tracker_db
        from VIVAANXMUSIC.mongo.abuse_words_db import init_abuse_words_db
        from VIVAANXMUSIC.utils.abuse_detector import init_abuse_detector
        from VIVAANXMUSIC.utils.warning_manager import init_warning_manager
        
        # Initialize databases
        await init_edit_tracker_db(MONGO_DB)
        LOGGER(__name__).info("✅ Edit Tracker DB initialized")
        
        await init_abuse_words_db(MONGO_DB)
        LOGGER(__name__).info("✅ Abuse Words DB initialized")
        
        # Initialize detectors and managers
        init_abuse_detector()
        LOGGER(__name__).info("✅ Abuse Detector initialized")
        
        init_warning_manager()
        LOGGER(__name__).info("✅ Warning Manager initialized")
        
        LOGGER(__name__).info("🔒 Security systems initialized successfully")
        
    except Exception as e:
        LOGGER(__name__).error(f"❌ Failed to initialize security systems: {e}")
        raise
