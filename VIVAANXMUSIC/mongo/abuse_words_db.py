"""
Abuse Words Database Module
Manages abusive word detection, patterns, and user warnings
Part of VivaanXMusic4.0 Anti-Abuse System

Functions:
- Store and manage abusive words with patterns
- Track user warnings and offenses
- Handle abuse detection configuration per group
- Pattern generation and management
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo import ASCENDING, DESCENDING
from bson import ObjectId

logger = logging.getLogger(__name__)


class AbuseWordsDB:
    """MongoDB database handler for abuse word detection and warnings"""
    
    def __init__(self, mongo_db: AsyncIOMotorDatabase):
        """
        Initialize AbuseWordsDB
        
        Args:
            mongo_db: Motor AsyncIO MongoDB database instance
        """
        self.db = mongo_db
        self.abuse_config_collection: AsyncIOMotorCollection = mongo_db["abuse_config"]
        self.abuse_words_collection: AsyncIOMotorCollection = mongo_db["abuse_words"]
        self.user_warnings_collection: AsyncIOMotorCollection = mongo_db["abuse_warnings"]
        self.abuse_history_collection: AsyncIOMotorCollection = mongo_db["abuse_history"]
    
    async def create_indexes(self):
        """Create required MongoDB indexes for performance"""
        try:
            # Config indexes
            await self.abuse_config_collection.create_index("chat_id", unique=True)
            
            # Abuse words indexes
            await self.abuse_words_collection.create_index("word", unique=True)
            await self.abuse_words_collection.create_index("severity")
            await self.abuse_words_collection.create_index("patterns")
            
            # User warnings indexes
            await self.user_warnings_collection.create_index([("chat_id", ASCENDING), ("user_id", ASCENDING)])
            await self.user_warnings_collection.create_index("chat_id")
            await self.user_warnings_collection.create_index("user_id")
            
            # Abuse history indexes
            await self.abuse_history_collection.create_index("chat_id")
            await self.abuse_history_collection.create_index("user_id")
            await self.abuse_history_collection.create_index("timestamp")
            
            # Try to create TTL index, ignore if it already exists with different options
            try:
                await self.abuse_history_collection.create_index(
                    "timestamp",
                    expireAfterSeconds=604800  # Auto-delete after 7 days
                )
            except Exception as idx_err:
                logger.warning(f"[AbuseWordsDB] TTL index already exists or error: {idx_err}")
            
            logger.info("[AbuseWordsDB] Indexes created successfully")
        except Exception as e:
            logger.error(f"[AbuseWordsDB] Error creating indexes: {e}")
    
    # ────────────────────────────────────────────────────────────
    # Configuration Management
    # ────────────────────────────────────────────────────────────
    
    async def get_config(self, chat_id: int) -> Dict[str, Any]:
        """
        Get abuse detection configuration for a chat
        
        Args:
            chat_id: Telegram group ID
            
        Returns:
            dict: Configuration dictionary with defaults
        """
        try:
            config = await self.abuse_config_collection.find_one({"chat_id": chat_id})
            
            if config:
                config.pop("_id", None)
                return config
            
            return {
                "chat_id": chat_id,
                "enabled": True,
                "strict_mode": False,
                "warning_limit": 3,
                "action": "delete_only",
                "mute_duration": 1440,
                "delete_warning": True,
                "warning_delete_time": 10,
                "exclude_admins": True,
                "notify_admins": False,
                "log_channel": None,
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
        except Exception as e:
            logger.error(f"[AbuseWordsDB] Error getting config for {chat_id}: {e}")
            return {
                "chat_id": chat_id,
                "enabled": True,
                "strict_mode": False,
                "exclude_admins": True
            }
    
    async def set_config(self, chat_id: int, config: Dict[str, Any]) -> bool:
        """
        Set or update abuse detection configuration
        
        Args:
            chat_id: Telegram group ID
            config: Configuration dictionary
            
        Returns:
            bool: True if successful
        """
        try:
            config["chat_id"] = chat_id
            config["updated_at"] = datetime.now()
            
            await self.abuse_config_collection.update_one(
                {"chat_id": chat_id},
                {"$set": config},
                upsert=True
            )
            logger.info(f"[AbuseWordsDB] Config updated for chat {chat_id}")
            return True
        except Exception as e:
            logger.error(f"[AbuseWordsDB] Error setting config for {chat_id}: {e}")
            return False
    
    async def set_action(self, chat_id: int, action: str) -> bool:
        """
        Set action type for abuse detection
        
        Args:
            chat_id: Telegram group ID
            action: Action type (mute, ban, delete_only, warn_only)
            
        Returns:
            bool: True if successful
        """
        try:
            valid_actions = ["mute", "ban", "delete_only", "warn_only"]
            
            if action not in valid_actions:
                logger.warning(f"[AbuseWordsDB] Invalid action: {action}")
                return False
            
            await self.abuse_config_collection.update_one(
                {"chat_id": chat_id},
                {
                    "$set": {
                        "action": action,
                        "updated_at": datetime.now()
                    }
                },
                upsert=True
            )
            logger.info(f"[AbuseWordsDB] Action set to {action} for {chat_id}")
            return True
        except Exception as e:
            logger.error(f"[AbuseWordsDB] Error setting action: {e}")
            return False
    
    async def set_warning_limit(self, chat_id: int, limit: int) -> bool:
        """
        Set warning limit before action
        
        Args:
            chat_id: Telegram group ID
            limit: Warning limit (0 = unlimited)
            
        Returns:
            bool: True if successful
        """
        try:
            if limit < 0:
                logger.warning(f"[AbuseWordsDB] Invalid limit: {limit}")
                return False
            
            await self.abuse_config_collection.update_one(
                {"chat_id": chat_id},
                {
                    "$set": {
                        "warning_limit": limit,
                        "updated_at": datetime.now()
                    }
                },
                upsert=True
            )
            logger.info(f"[AbuseWordsDB] Warning limit set to {limit} for {chat_id}")
            return True
        except Exception as e:
            logger.error(f"[AbuseWordsDB] Error setting warning limit: {e}")
            return False
    
    async def toggle_enabled(self, chat_id: int, enabled: bool) -> bool:
        """
        Toggle abuse detection on/off
        
        Args:
            chat_id: Telegram group ID
            enabled: Enable or disable
            
        Returns:
            bool: True if successful
        """
        try:
            await self.abuse_config_collection.update_one(
                {"chat_id": chat_id},
                {
                    "$set": {
                        "enabled": enabled,
                        "updated_at": datetime.now()
                    }
                },
                upsert=True
            )
            logger.info(f"[AbuseWordsDB] Abuse detection {'enabled' if enabled else 'disabled'} for {chat_id}")
            return True
        except Exception as e:
            logger.error(f"[AbuseWordsDB] Error toggling: {e}")
            return False
    
    # ────────────────────────────────────────────────────────────
    # Abuse Words Management
    # ────────────────────────────────────────────────────────────
    
    async def add_abuse_word(
        self,
        word: str,
        severity: str = "high",
        patterns: Optional[List[str]] = None,
        added_by: int = 0
    ) -> bool:
        """
        Add an abusive word to the database
        
        Args:
            word: The abusive word (base form)
            severity: Severity level (low, medium, high)
            patterns: List of pattern variations
            added_by: User ID who added the word
            
        Returns:
            bool: True if successful
        """
        try:
            word_lower = word.lower().strip()
            
            if not word_lower:
                logger.warning("[AbuseWordsDB] Empty word provided")
                return False
            
            existing = await self.abuse_words_collection.find_one({"word": word_lower})
            if existing:
                logger.warning(f"[AbuseWordsDB] Word already exists: {word_lower}")
                return False
            
            abuse_word = {
                "word": word_lower,
                "severity": severity,
                "patterns": patterns or [],
                "added_by": added_by,
                "added_at": datetime.now(),
                "updated_at": datetime.now()
            }
            
            await self.abuse_words_collection.insert_one(abuse_word)
            logger.info(f"[AbuseWordsDB] Abuse word added: {word_lower}")
            return True
        except Exception as e:
            logger.error(f"[AbuseWordsDB] Error adding abuse word: {e}")
            return False
    
    async def remove_abuse_word(self, word: str) -> bool:
        """
        Remove an abusive word from the database
        
        Args:
            word: The word to remove
            
        Returns:
            bool: True if successful
        """
        try:
            result = await self.abuse_words_collection.delete_one(
                {"word": word.lower().strip()}
            )
            
            if result.deleted_count > 0:
                logger.info(f"[AbuseWordsDB] Abuse word removed: {word}")
                return True
            
            logger.warning(f"[AbuseWordsDB] Word not found: {word}")
            return False
        except Exception as e:
            logger.error(f"[AbuseWordsDB] Error removing abuse word: {e}")
            return False
    
    async def get_all_abuse_words(self) -> List[Dict[str, Any]]:
        """
        Get all abusive words from database
        
        Returns:
            list: List of abuse word documents
        """
        try:
            words = await self.abuse_words_collection.find({}).to_list(length=None)
            
            for word in words:
                word.pop("_id", None)
            
            return words
        except Exception as e:
            logger.error(f"[AbuseWordsDB] Error getting abuse words: {e}")
            return []
    
    async def word_exists(self, word: str) -> bool:
        """
        Check if a word exists in abuse list
        
        Args:
            word: The word to check
            
        Returns:
            bool: True if word exists
        """
        try:
            exists = await self.abuse_words_collection.find_one(
                {"word": word.lower().strip()}
            )
            return exists is not None
        except Exception as e:
            logger.error(f"[AbuseWordsDB] Error checking word: {e}")
            return False
    
    # ────────────────────────────────────────────────────────────
    # User Warnings Management
    # ────────────────────────────────────────────────────────────
    
    async def add_warning(
        self,
        chat_id: int,
        user_id: int,
        abusive_word: str,
        message_content: str
    ) -> int:
        """
        Add warning to user and increment count
        
        Args:
            chat_id: Telegram group ID
            user_id: User ID
            abusive_word: The abusive word detected
            message_content: Full message content
            
        Returns:
            int: Total warning count for user
        """
        try:
            user_warns = await self.user_warnings_collection.find_one({
                "chat_id": chat_id,
                "user_id": user_id
            })
            
            offense = {
                "word": abusive_word,
                "message": message_content[:200],
                "timestamp": datetime.now()
            }
            
            if user_warns:
                warnings = user_warns.get("warnings", 0) + 1
                offenses = user_warns.get("offenses", [])
                offenses.append(offense)
                
                if len(offenses) > 10:
                    offenses = offenses[-10:]
                
                await self.user_warnings_collection.update_one(
                    {"chat_id": chat_id, "user_id": user_id},
                    {
                        "$set": {
                            "warnings": warnings,
                            "offenses": offenses,
                            "last_offense": datetime.now()
                        }
                    }
                )
            else:
                warnings = 1
                await self.user_warnings_collection.insert_one({
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "warnings": warnings,
                    "offenses": [offense],
                    "first_offense": datetime.now(),
                    "last_offense": datetime.now(),
                    "created_at": datetime.now()
                })
            
            logger.info(f"[AbuseWordsDB] Warning added for {user_id} in {chat_id}: {warnings}")
            return warnings
        except Exception as e:
            logger.error(f"[AbuseWordsDB] Error adding warning: {e}")
            return 0
    
    async def get_warnings(self, chat_id: int, user_id: int) -> int:
        """
        Get warning count for a user
        
        Args:
            chat_id: Telegram group ID
            user_id: User ID
            
        Returns:
            int: Warning count
        """
        try:
            user_warns = await self.user_warnings_collection.find_one({
                "chat_id": chat_id,
                "user_id": user_id
            })
            
            return user_warns.get("warnings", 0) if user_warns else 0
        except Exception as e:
            logger.error(f"[AbuseWordsDB] Error getting warnings: {e}")
            return 0
    
    async def clear_warnings(self, chat_id: int, user_id: int) -> bool:
        """
        Clear all warnings for a user
        
        Args:
            chat_id: Telegram group ID
            user_id: User ID
            
        Returns:
            bool: True if successful
        """
        try:
            result = await self.user_warnings_collection.delete_one({
                "chat_id": chat_id,
                "user_id": user_id
            })
            
            if result.deleted_count > 0:
                logger.info(f"[AbuseWordsDB] Warnings cleared for {user_id} in {chat_id}")
                return True
            
            return False
        except Exception as e:
            logger.error(f"[AbuseWordsDB] Error clearing warnings: {e}")
            return False
    
    async def clear_user_warnings(self, chat_id: int, user_id: int) -> bool:
        """
        Clear warnings for a specific user (alias for clear_warnings)
        
        Args:
            chat_id: Telegram group ID
            user_id: User ID
            
        Returns:
            bool: True if successful
        """
        return await self.clear_warnings(chat_id, user_id)
    
    async def get_user_history(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """
        Get warning history for a user
        
        Args:
            chat_id: Telegram group ID
            user_id: User ID
            
        Returns:
            dict: User warning history
        """
        try:
            user_warns = await self.user_warnings_collection.find_one({
                "chat_id": chat_id,
                "user_id": user_id
            })
            
            if user_warns:
                user_warns.pop("_id", None)
                return user_warns
            
            return {}
        except Exception as e:
            logger.error(f"[AbuseWordsDB] Error getting user history: {e}")
            return {}
    
    # ────────────────────────────────────────────────────────────
    # Abuse History / Audit Trail
    # ────────────────────────────────────────────────────────────
    
    async def log_abuse_detection(
        self,
        chat_id: int,
        user_id: int,
        detected_word: str,
        message: str,
        action_taken: Optional[str] = None
    ) -> bool:
        """
        Log abuse detection for audit trail
        
        Args:
            chat_id: Telegram group ID
            user_id: User ID
            detected_word: The detected abusive word
            message: Full message content
            action_taken: Action taken (mute, ban, delete, etc.)
            
        Returns:
            bool: True if successful
        """
        try:
            log_entry = {
                "chat_id": chat_id,
                "user_id": user_id,
                "detected_word": detected_word,
                "message": message[:300],
                "action_taken": action_taken,
                "timestamp": datetime.now()
            }
            
            await self.abuse_history_collection.insert_one(log_entry)
            logger.debug(f"[AbuseWordsDB] Abuse logged: {detected_word} by {user_id}")
            return True
        except Exception as e:
            logger.error(f"[AbuseWordsDB] Error logging abuse: {e}")
            return False
    
    async def get_recent_abuses(self, chat_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent abuse detections in a chat
        
        Args:
            chat_id: Telegram group ID
            limit: Maximum records to return
            
        Returns:
            list: Recent abuse logs
        """
        try:
            logs = await self.abuse_history_collection.find(
                {"chat_id": chat_id}
            ).sort("timestamp", -1).limit(limit).to_list(length=limit)
            
            for log in logs:
                log.pop("_id", None)
            
            return logs
        except Exception as e:
            logger.error(f"[AbuseWordsDB] Error getting recent abuses: {e}")
            return []
    
    # ────────────────────────────────────────────────────────────
    # Statistics & Analytics
    # ────────────────────────────────────────────────────────────
    
    async def get_abuse_stats(self, chat_id: int) -> Dict[str, Any]:
        """
        Get abuse detection statistics for a chat
        
        Args:
            chat_id: Telegram group ID
            
        Returns:
            dict: Statistics
        """
        try:
            config = await self.get_config(chat_id)
            
            total_words = await self.abuse_words_collection.count_documents({})
            total_violations = await self.abuse_history_collection.count_documents({"chat_id": chat_id})
            
            warned_users = await self.user_warnings_collection.count_documents({
                "chat_id": chat_id
            })
            
            pipeline = [
                {"$match": {"chat_id": chat_id}},
                {"$group": {"_id": "$detected_word", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 5}
            ]
            
            most_common = await self.abuse_history_collection.aggregate(pipeline).to_list(length=5)
            
            return {
                "enabled": config.get("enabled", True),
                "action": config.get("action", "delete_only"),
                "warning_limit": config.get("warning_limit", 3),
                "total_abuse_words": total_words,
                "total_violations": total_violations,
                "users_with_warnings": warned_users,
                "most_common_violations": most_common
            }
        except Exception as e:
            logger.error(f"[AbuseWordsDB] Error getting stats: {e}")
            return {
                "total_abuse_words": 0,
                "total_violations": 0,
                "users_with_warnings": 0
            }
    
    # ────────────────────────────────────────────────────────────
    # Cleanup & Maintenance
    # ────────────────────────────────────────────────────────────
    
    async def cleanup_old_history(self, days: int = 7) -> bool:
        """
        Clean up old abuse history
        
        Args:
            days: Delete records older than N days
            
        Returns:
            bool: True if successful
        """
        try:
            cutoff = datetime.now() - timedelta(days=days)
            
            result = await self.abuse_history_collection.delete_many({
                "timestamp": {"$lt": cutoff}
            })
            
            logger.info(f"[AbuseWordsDB] Deleted {result.deleted_count} old history records")
            return True
        except Exception as e:
            logger.error(f"[AbuseWordsDB] Error cleaning up history: {e}")
            return False
    
    async def reset_chat_warnings(self, chat_id: int) -> bool:
        """
        Reset all warnings for a chat
        
        Args:
            chat_id: Telegram group ID
            
        Returns:
            bool: True if successful
        """
        try:
            result = await self.user_warnings_collection.delete_many({
                "chat_id": chat_id
            })
            
            logger.info(f"[AbuseWordsDB] Reset {result.deleted_count} warnings for {chat_id}")
            return True
        except Exception as e:
            logger.error(f"[AbuseWordsDB] Error resetting warnings: {e}")
            return False


# ────────────────────────────────────────────────────────────
# Global instance
# ────────────────────────────────────────────────────────────

abuse_words_db: Optional[AbuseWordsDB] = None


async def init_abuse_words_db(mongo_db: AsyncIOMotorDatabase) -> AbuseWordsDB:
    """
    Initialize the abuse words database
    
    Args:
        mongo_db: Motor AsyncIO MongoDB database instance
        
    Returns:
        AbuseWordsDB: Initialized database handler
    """
    global abuse_words_db
    
    abuse_words_db = AbuseWordsDB(mongo_db)
    await abuse_words_db.create_indexes()
    logger.info("[AbuseWordsDB] Initialized successfully")
    
    return abuse_words_db
