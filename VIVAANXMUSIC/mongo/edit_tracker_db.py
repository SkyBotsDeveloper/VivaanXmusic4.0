"""
Edit Tracker Database Module
Manages edited message detection and scheduled deletion
Part of VivaanXMusic4.0 Anti-Edit System

Functions:
- Store edit detection configurations per group
- Track pending message deletions
- Manage admin exemptions
- Handle deletion scheduling
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo import ASCENDING, DESCENDING

logger = logging.getLogger(__name__)


class EditTrackerDB:
    """MongoDB database handler for edit message tracking"""
    
    def __init__(self, mongo_db: AsyncIOMotorDatabase):
        """
        Initialize EditTrackerDB
        
        Args:
            mongo_db: Motor AsyncIO MongoDB database instance
        """
        self.db = mongo_db
        self.edit_config_collection: AsyncIOMotorCollection = mongo_db["edit_tracker_config"]
        self.pending_deletions_collection: AsyncIOMotorCollection = mongo_db["pending_edits"]
        self.edit_history_collection: AsyncIOMotorCollection = mongo_db["edit_history"]
    
    async def create_indexes(self):
        """Create required MongoDB indexes for performance"""
        try:
            # Config indexes
            await self.edit_config_collection.create_index("chat_id", unique=True)
            
            # Pending deletions indexes
            await self.pending_deletions_collection.create_index("chat_id")
            await self.pending_deletions_collection.create_index("user_id")
            await self.pending_deletions_collection.create_index("scheduled_at")
            await self.pending_deletions_collection.create_index(
                "scheduled_at",
                expireAfterSeconds=3600  # Auto-delete after 1 hour
            )
            
            # Edit history indexes
            await self.edit_history_collection.create_index("chat_id")
            await self.edit_history_collection.create_index("user_id")
            await self.edit_history_collection.create_index("timestamp", expireAfterSeconds=86400)
            
            logger.info("[EditTrackerDB] Indexes created successfully")
        except Exception as e:
            logger.error(f"[EditTrackerDB] Error creating indexes: {e}")
    
    # ────────────────────────────────────────────────────────────
    # Configuration Management
    # ────────────────────────────────────────────────────────────
    
    async def get_config(self, chat_id: int) -> Dict[str, Any]:
        """
        Get edit detection configuration for a chat
        
        Args:
            chat_id: Telegram group ID
            
        Returns:
            dict: Configuration dictionary with defaults
        """
        try:
            config = await self.edit_config_collection.find_one({"chat_id": chat_id})
            
            if config:
                return config
            
            # Return default config if not found
            return {
                "chat_id": chat_id,
                "enabled": True,
                "warning_time": 60,  # seconds
                "exclude_admins": True,
                "exclude_owner": True,
                "delete_warning_msg": True,
                "warning_delete_delay": 5,  # seconds
                "notify_channel": None,
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
        except Exception as e:
            logger.error(f"[EditTrackerDB] Error getting config for {chat_id}: {e}")
            return {}
    
    async def set_config(self, chat_id: int, config: Dict[str, Any]) -> bool:
        """
        Set or update edit detection configuration
        
        Args:
            chat_id: Telegram group ID
            config: Configuration dictionary
            
        Returns:
            bool: True if successful
        """
        try:
            config["chat_id"] = chat_id
            config["updated_at"] = datetime.now()
            
            await self.edit_config_collection.update_one(
                {"chat_id": chat_id},
                {"$set": config},
                upsert=True
            )
            logger.info(f"[EditTrackerDB] Config updated for chat {chat_id}")
            return True
        except Exception as e:
            logger.error(f"[EditTrackerDB] Error setting config for {chat_id}: {e}")
            return False
    
    async def toggle_enabled(self, chat_id: int, enabled: bool) -> bool:
        """
        Toggle edit detection on/off for a chat
        
        Args:
            chat_id: Telegram group ID
            enabled: Enable or disable
            
        Returns:
            bool: True if successful
        """
        try:
            await self.edit_config_collection.update_one(
                {"chat_id": chat_id},
                {
                    "$set": {
                        "enabled": enabled,
                        "updated_at": datetime.now()
                    }
                },
                upsert=True
            )
            logger.info(f"[EditTrackerDB] Edit detection {'enabled' if enabled else 'disabled'} for {chat_id}")
            return True
        except Exception as e:
            logger.error(f"[EditTrackerDB] Error toggling for {chat_id}: {e}")
            return False
    
    async def set_warning_time(self, chat_id: int, seconds: int) -> bool:
        """
        Set warning countdown time before deletion
        
        Args:
            chat_id: Telegram group ID
            seconds: Countdown time in seconds (min: 10, max: 300)
            
        Returns:
            bool: True if successful
        """
        try:
            # Validate range
            if not (10 <= seconds <= 300):
                logger.warning(f"[EditTrackerDB] Invalid warning time: {seconds}. Using default 60s")
                seconds = 60
            
            await self.edit_config_collection.update_one(
                {"chat_id": chat_id},
                {
                    "$set": {
                        "warning_time": seconds,
                        "updated_at": datetime.now()
                    }
                },
                upsert=True
            )
            logger.info(f"[EditTrackerDB] Warning time set to {seconds}s for {chat_id}")
            return True
        except Exception as e:
            logger.error(f"[EditTrackerDB] Error setting warning time: {e}")
            return False
    
    async def set_admin_exemption(self, chat_id: int, exempt: bool) -> bool:
        """
        Set whether admins are exempt from edit detection
        
        Args:
            chat_id: Telegram group ID
            exempt: Exempt admins or not
            
        Returns:
            bool: True if successful
        """
        try:
            await self.edit_config_collection.update_one(
                {"chat_id": chat_id},
                {
                    "$set": {
                        "exclude_admins": exempt,
                        "updated_at": datetime.now()
                    }
                },
                upsert=True
            )
            logger.info(f"[EditTrackerDB] Admin exemption set to {exempt} for {chat_id}")
            return True
        except Exception as e:
            logger.error(f"[EditTrackerDB] Error setting admin exemption: {e}")
            return False
    
    # ────────────────────────────────────────────────────────────
    # Pending Deletion Management
    # ────────────────────────────────────────────────────────────
    
    async def add_pending_deletion(
        self,
        chat_id: int,
        message_id: int,
        user_id: int,
        warning_msg_id: Optional[int] = None,
        delete_in_seconds: int = 60
    ) -> bool:
        """
        Add a message to pending deletions queue
        
        Args:
            chat_id: Telegram group ID
            message_id: Message ID to delete
            user_id: User who edited the message
            warning_msg_id: Warning message ID (for cleanup)
            delete_in_seconds: Seconds until deletion
            
        Returns:
            bool: True if successful
        """
        try:
            scheduled_at = datetime.now() + timedelta(seconds=delete_in_seconds)
            
            pending = {
                "chat_id": chat_id,
                "message_id": message_id,
                "user_id": user_id,
                "warning_msg_id": warning_msg_id,
                "scheduled_at": scheduled_at,
                "created_at": datetime.now(),
                "status": "pending"
            }
            
            await self.pending_deletions_collection.insert_one(pending)
            logger.info(f"[EditTrackerDB] Pending deletion added: {chat_id}/{message_id}")
            return True
        except Exception as e:
            logger.error(f"[EditTrackerDB] Error adding pending deletion: {e}")
            return False
    
    async def get_pending_deletions(self, limit: int = 100) -> list:
        """
        Get all pending deletions that are ready
        
        Args:
            limit: Maximum number of deletions to retrieve
            
        Returns:
            list: List of pending deletion documents
        """
        try:
            pending = await self.pending_deletions_collection.find(
                {
                    "scheduled_at": {"$lte": datetime.now()},
                    "status": "pending"
                }
            ).limit(limit).to_list(length=limit)
            
            return pending
        except Exception as e:
            logger.error(f"[EditTrackerDB] Error getting pending deletions: {e}")
            return []
    
    async def mark_deletion_done(self, deletion_id: str) -> bool:
        """
        Mark a deletion as completed
        
        Args:
            deletion_id: MongoDB object ID of the deletion record
            
        Returns:
            bool: True if successful
        """
        try:
            from bson import ObjectId
            
            await self.pending_deletions_collection.update_one(
                {"_id": ObjectId(deletion_id)},
                {
                    "$set": {
                        "status": "done",
                        "completed_at": datetime.now()
                    }
                }
            )
            logger.info(f"[EditTrackerDB] Deletion marked as done: {deletion_id}")
            return True
        except Exception as e:
            logger.error(f"[EditTrackerDB] Error marking deletion done: {e}")
            return False
    
    async def remove_pending_deletion(self, deletion_id: str) -> bool:
        """
        Remove a pending deletion record
        
        Args:
            deletion_id: MongoDB object ID of the deletion record
            
        Returns:
            bool: True if successful
        """
        try:
            from bson import ObjectId
            
            await self.pending_deletions_collection.delete_one(
                {"_id": ObjectId(deletion_id)}
            )
            logger.info(f"[EditTrackerDB] Deletion removed: {deletion_id}")
            return True
        except Exception as e:
            logger.error(f"[EditTrackerDB] Error removing deletion: {e}")
            return False
    
    # ────────────────────────────────────────────────────────────
    # Edit History Management
    # ────────────────────────────────────────────────────────────
    
    async def log_edit(
        self,
        chat_id: int,
        user_id: int,
        message_id: int,
        original_text: str,
        edited_text: str
    ) -> bool:
        """
        Log an edited message for history/audit trail
        
        Args:
            chat_id: Telegram group ID
            user_id: User who edited
            message_id: Message ID
            original_text: Original message text
            edited_text: Edited message text
            
        Returns:
            bool: True if successful
        """
        try:
            history = {
                "chat_id": chat_id,
                "user_id": user_id,
                "message_id": message_id,
                "original_text": original_text[:500],  # Store only first 500 chars
                "edited_text": edited_text[:500],
                "timestamp": datetime.now()
            }
            
            await self.edit_history_collection.insert_one(history)
            logger.debug(f"[EditTrackerDB] Edit logged: {chat_id}/{message_id}")
            return True
        except Exception as e:
            logger.error(f"[EditTrackerDB] Error logging edit: {e}")
            return False
    
    async def get_user_edit_count(self, chat_id: int, user_id: int, hours: int = 24) -> int:
        """
        Get number of edits by user in the last N hours
        
        Args:
            chat_id: Telegram group ID
            user_id: User ID
            hours: Number of hours to check
            
        Returns:
            int: Number of edits
        """
        try:
            since = datetime.now() - timedelta(hours=hours)
            
            count = await self.edit_history_collection.count_documents({
                "chat_id": chat_id,
                "user_id": user_id,
                "timestamp": {"$gte": since}
            })
            
            return count
        except Exception as e:
            logger.error(f"[EditTrackerDB] Error getting edit count: {e}")
            return 0
    
    # ────────────────────────────────────────────────────────────
    # Cleanup & Maintenance
    # ────────────────────────────────────────────────────────────
    
    async def cleanup_old_data(self, days: int = 7) -> bool:
        """
        Clean up old edit history data
        
        Args:
            days: Delete records older than N days
            
        Returns:
            bool: True if successful
        """
        try:
            cutoff = datetime.now() - timedelta(days=days)
            
            result = await self.edit_history_collection.delete_many({
                "timestamp": {"$lt": cutoff}
            })
            
            logger.info(f"[EditTrackerDB] Deleted {result.deleted_count} old records")
            return True
        except Exception as e:
            logger.error(f"[EditTrackerDB] Error cleaning up data: {e}")
            return False
    
    async def get_stats(self, chat_id: int) -> Dict[str, Any]:
        """
        Get statistics for a chat
        
        Args:
            chat_id: Telegram group ID
            
        Returns:
            dict: Statistics
        """
        try:
            config = await self.get_config(chat_id)
            
            pending = await self.pending_deletions_collection.count_documents({
                "chat_id": chat_id,
                "status": "pending"
            })
            
            completed = await self.pending_deletions_collection.count_documents({
                "chat_id": chat_id,
                "status": "done"
            })
            
            total_edits = await self.edit_history_collection.count_documents({
                "chat_id": chat_id
            })
            
            return {
                "enabled": config.get("enabled", True),
                "warning_time": config.get("warning_time", 60),
                "pending_deletions": pending,
                "completed_deletions": completed,
                "total_edits_logged": total_edits
            }
        except Exception as e:
            logger.error(f"[EditTrackerDB] Error getting stats: {e}")
            return {}


# ────────────────────────────────────────────────────────────
# Global instance
# ────────────────────────────────────────────────────────────

edit_tracker_db: Optional[EditTrackerDB] = None


async def init_edit_tracker_db(mongo_db: AsyncIOMotorDatabase) -> EditTrackerDB:
    """
    Initialize the edit tracker database
    
    Args:
        mongo_db: Motor AsyncIO MongoDB database instance
        
    Returns:
        EditTrackerDB: Initialized database handler
    """
    global edit_tracker_db
    
    edit_tracker_db = EditTrackerDB(mongo_db)
    await edit_tracker_db.create_indexes()
    logger.info("[EditTrackerDB] Initialized successfully")
    
    return edit_tracker_db
