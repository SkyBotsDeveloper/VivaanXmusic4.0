"""
Edit Tracker Database Module for VivaanXMusic Bot
Handles MongoDB operations for anti-edit functionality.

Collections:
- antiedit_config: Stores enable/disable status per group
- authorized_users: Stores users authorized to edit per group
- edit_logs: Logs all edit actions for analytics

Author: Vivaan Devs
Version: 4.0
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo.errors import PyMongoError, DuplicateKeyError

from config import MONGO_DB_URI

# Logger setup
logger = logging.getLogger(__name__)


class EditTrackerDB:
    """
    MongoDB handler for anti-edit functionality.
    Manages configuration, authorized users, and edit logs.
    """
    
    def __init__(self):
        """Initialize MongoDB connection and collections."""
        try:
            self.client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_DB_URI)
            self.db: AsyncIOMotorDatabase = self.client.VivaanXMusic
            
            # Collections
            self.config_collection: AsyncIOMotorCollection = self.db.antiedit_config
            self.authorized_collection: AsyncIOMotorCollection = self.db.authorized_users
            self.logs_collection: AsyncIOMotorCollection = self.db.edit_logs
            
            logger.info("EditTrackerDB initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize EditTrackerDB: {e}", exc_info=True)
            raise
    
    async def create_indexes(self):
        """
        Create MongoDB indexes for optimal query performance.
        Should be called once during bot startup.
        """
        try:
            # Index for config collection
            await self.config_collection.create_index("chat_id", unique=True)
            
            # Compound index for authorized users
            await self.authorized_collection.create_index(
                [("chat_id", 1), ("user_id", 1)],
                unique=True
            )
            await self.authorized_collection.create_index("chat_id")
            
            # Indexes for logs collection
            await self.logs_collection.create_index(
                [("chat_id", 1), ("timestamp", -1)]
            )
            await self.logs_collection.create_index("timestamp", expireAfterSeconds=2592000)  # 30 days TTL
            
            logger.info("MongoDB indexes created successfully")
            
        except Exception as e:
            logger.error(f"Error creating indexes: {e}", exc_info=True)
    
    # ==================== CONFIG OPERATIONS ====================
    
    async def enable_antiedit(self, chat_id: int) -> bool:
        """
        Enable anti-edit feature for a group.
        
        Args:
            chat_id: Telegram chat ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            await self.config_collection.update_one(
                {"chat_id": chat_id},
                {
                    "$set": {
                        "enabled": True,
                        "updated_at": datetime.utcnow()
                    },
                    "$setOnInsert": {
                        "chat_id": chat_id,
                        "created_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            logger.info(f"Anti-edit enabled for chat {chat_id}")
            return True
            
        except PyMongoError as e:
            logger.error(f"Error enabling anti-edit for chat {chat_id}: {e}")
            return False
    
    async def disable_antiedit(self, chat_id: int) -> bool:
        """
        Disable anti-edit feature for a group.
        
        Args:
            chat_id: Telegram chat ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            await self.config_collection.update_one(
                {"chat_id": chat_id},
                {
                    "$set": {
                        "enabled": False,
                        "updated_at": datetime.utcnow()
                    },
                    "$setOnInsert": {
                        "chat_id": chat_id,
                        "created_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            logger.info(f"Anti-edit disabled for chat {chat_id}")
            return True
            
        except PyMongoError as e:
            logger.error(f"Error disabling anti-edit for chat {chat_id}: {e}")
            return False
    
    async def is_antiedit_enabled(self, chat_id: int) -> bool:
        """
        Check if anti-edit is enabled for a group.
        
        Args:
            chat_id: Telegram chat ID
            
        Returns:
            bool: True if enabled, False if disabled or not configured
        """
        try:
            config = await self.config_collection.find_one({"chat_id": chat_id})
            
            if config is None:
                # Default: disabled if not configured
                return False
            
            return config.get("enabled", False)
            
        except PyMongoError as e:
            logger.error(f"Error checking anti-edit status for chat {chat_id}: {e}")
            return False
    
    async def get_config(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """
        Get full configuration for a group.
        
        Args:
            chat_id: Telegram chat ID
            
        Returns:
            Optional[Dict]: Configuration dict or None if not found
        """
        try:
            config = await self.config_collection.find_one({"chat_id": chat_id})
            return config
            
        except PyMongoError as e:
            logger.error(f"Error getting config for chat {chat_id}: {e}")
            return None
    
    # ==================== AUTHORIZED USERS OPERATIONS ====================
    
    async def add_authorized_user(self, chat_id: int, user_id: int) -> bool:
        """
        Add a user to the authorized list for a group.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID to authorize
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            await self.authorized_collection.insert_one({
                "chat_id": chat_id,
                "user_id": user_id,
                "authorized_at": datetime.utcnow()
            })
            logger.info(f"User {user_id} authorized in chat {chat_id}")
            return True
            
        except DuplicateKeyError:
            logger.debug(f"User {user_id} already authorized in chat {chat_id}")
            return True  # Already authorized, still success
            
        except PyMongoError as e:
            logger.error(f"Error authorizing user {user_id} in chat {chat_id}: {e}")
            return False
    
    async def remove_authorized_user(self, chat_id: int, user_id: int) -> bool:
        """
        Remove a user from the authorized list for a group.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID to deauthorize
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            result = await self.authorized_collection.delete_one({
                "chat_id": chat_id,
                "user_id": user_id
            })
            
            if result.deleted_count > 0:
                logger.info(f"User {user_id} deauthorized from chat {chat_id}")
            else:
                logger.debug(f"User {user_id} was not in authorized list for chat {chat_id}")
            
            return True
            
        except PyMongoError as e:
            logger.error(f"Error deauthorizing user {user_id} from chat {chat_id}: {e}")
            return False
    
    async def is_authorized_user(self, chat_id: int, user_id: int) -> bool:
        """
        Check if a user is authorized to edit messages in a group.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID to check
            
        Returns:
            bool: True if authorized, False otherwise
        """
        try:
            authorized = await self.authorized_collection.find_one({
                "chat_id": chat_id,
                "user_id": user_id
            })
            
            return authorized is not None
            
        except PyMongoError as e:
            logger.error(f"Error checking authorization for user {user_id} in chat {chat_id}: {e}")
            return False
    
    async def get_authorized_users(self, chat_id: int) -> List[int]:
        """
        Get list of all authorized users in a group.
        
        Args:
            chat_id: Telegram chat ID
            
        Returns:
            List[int]: List of authorized user IDs
        """
        try:
            cursor = self.authorized_collection.find({"chat_id": chat_id})
            authorized_users = []
            
            async for doc in cursor:
                authorized_users.append(doc["user_id"])
            
            return authorized_users
            
        except PyMongoError as e:
            logger.error(f"Error getting authorized users for chat {chat_id}: {e}")
            return []
    
    async def clear_authorized_users(self, chat_id: int) -> bool:
        """
        Remove all authorized users from a group.
        
        Args:
            chat_id: Telegram chat ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            result = await self.authorized_collection.delete_many({"chat_id": chat_id})
            logger.info(f"Cleared {result.deleted_count} authorized users from chat {chat_id}")
            return True
            
        except PyMongoError as e:
            logger.error(f"Error clearing authorized users for chat {chat_id}: {e}")
            return False
    
    # ==================== LOGGING OPERATIONS ====================
    
    async def log_edit_action(
        self,
        chat_id: int,
        user_id: int,
        message_id: int,
        action: str,
        timestamp: Optional[datetime] = None
    ) -> bool:
        """
        Log an edit action to the database.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID who edited
            message_id: Message ID that was edited
            action: Action taken (e.g., "deleted", "allowed")
            timestamp: Optional timestamp (defaults to now)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            log_entry = {
                "chat_id": chat_id,
                "user_id": user_id,
                "message_id": message_id,
                "action": action,
                "timestamp": timestamp or datetime.utcnow()
            }
            
            await self.logs_collection.insert_one(log_entry)
            logger.debug(f"Logged edit action: {action} for message {message_id} in chat {chat_id}")
            return True
            
        except PyMongoError as e:
            logger.error(f"Error logging edit action: {e}")
            return False
    
    async def get_edit_logs(
        self,
        chat_id: int,
        limit: int = 100,
        days: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get edit logs for a group.
        
        Args:
            chat_id: Telegram chat ID
            limit: Maximum number of logs to return
            days: Optional filter for logs within last N days
            
        Returns:
            List[Dict]: List of log entries
        """
        try:
            query = {"chat_id": chat_id}
            
            # Add time filter if specified
            if days:
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                query["timestamp"] = {"$gte": cutoff_date}
            
            cursor = self.logs_collection.find(query).sort("timestamp", -1).limit(limit)
            
            logs = []
            async for log in cursor:
                logs.append(log)
            
            return logs
            
        except PyMongoError as e:
            logger.error(f"Error getting edit logs for chat {chat_id}: {e}")
            return []
    
    async def get_user_edit_count(self, chat_id: int, user_id: int, days: int = 7) -> int:
        """
        Get count of edits by a user in last N days.
        
        Args:
            chat_id: Telegram chat ID
            user_id: Telegram user ID
            days: Number of days to look back
            
        Returns:
            int: Number of edits
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            count = await self.logs_collection.count_documents({
                "chat_id": chat_id,
                "user_id": user_id,
                "timestamp": {"$gte": cutoff_date}
            })
            
            return count
            
        except PyMongoError as e:
            logger.error(f"Error getting edit count for user {user_id} in chat {chat_id}: {e}")
            return 0
    
    # ==================== CLEANUP OPERATIONS ====================
    
    async def cleanup_chat_data(self, chat_id: int) -> bool:
        """
        Remove all data for a chat (when bot leaves group).
        
        Args:
            chat_id: Telegram chat ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Remove config
            await self.config_collection.delete_one({"chat_id": chat_id})
            
            # Remove authorized users
            await self.authorized_collection.delete_many({"chat_id": chat_id})
            
            # Note: Logs are kept for analytics (will expire via TTL index)
            
            logger.info(f"Cleaned up data for chat {chat_id}")
            return True
            
        except PyMongoError as e:
            logger.error(f"Error cleaning up data for chat {chat_id}: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get global statistics for anti-edit feature.
        
        Returns:
            Dict: Statistics including total groups, authorized users, etc.
        """
        try:
            total_groups = await self.config_collection.count_documents({})
            enabled_groups = await self.config_collection.count_documents({"enabled": True})
            total_authorized = await self.authorized_collection.count_documents({})
            
            # Get recent activity (last 24 hours)
            yesterday = datetime.utcnow() - timedelta(days=1)
            recent_edits = await self.logs_collection.count_documents({
                "timestamp": {"$gte": yesterday}
            })
            
            return {
                "total_groups": total_groups,
                "enabled_groups": enabled_groups,
                "disabled_groups": total_groups - enabled_groups,
                "total_authorized_users": total_authorized,
                "recent_edits_24h": recent_edits
            }
            
        except PyMongoError as e:
            logger.error(f"Error getting stats: {e}")
            return {}
    
    async def close(self):
        """Close MongoDB connection."""
        try:
            self.client.close()
            logger.info("EditTrackerDB connection closed")
        except Exception as e:
            logger.error(f"Error closing EditTrackerDB connection: {e}")


# ==================== GLOBAL INSTANCE ====================

# Create global instance
_edit_tracker_db: Optional[EditTrackerDB] = None


def get_edit_tracker_db() -> EditTrackerDB:
    """
    Get or create the global EditTrackerDB instance.
    
    Returns:
        EditTrackerDB: Global database instance
    """
    global _edit_tracker_db
    
    if _edit_tracker_db is None:
        _edit_tracker_db = EditTrackerDB()
    
    return _edit_tracker_db


# ==================== CONVENIENCE FUNCTIONS ====================

async def enable_antiedit(chat_id: int) -> bool:
    """Enable anti-edit for a group."""
    db = get_edit_tracker_db()
    return await db.enable_antiedit(chat_id)


async def disable_antiedit(chat_id: int) -> bool:
    """Disable anti-edit for a group."""
    db = get_edit_tracker_db()
    return await db.disable_antiedit(chat_id)


async def is_antiedit_enabled(chat_id: int) -> bool:
    """Check if anti-edit is enabled."""
    db = get_edit_tracker_db()
    return await db.is_antiedit_enabled(chat_id)


async def add_authorized_user(chat_id: int, user_id: int) -> bool:
    """Add authorized user."""
    db = get_edit_tracker_db()
    return await db.add_authorized_user(chat_id, user_id)


async def remove_authorized_user(chat_id: int, user_id: int) -> bool:
    """Remove authorized user."""
    db = get_edit_tracker_db()
    return await db.remove_authorized_user(chat_id, user_id)


async def is_authorized_user(chat_id: int, user_id: int) -> bool:
    """Check if user is authorized."""
    db = get_edit_tracker_db()
    return await db.is_authorized_user(chat_id, user_id)


async def get_authorized_users(chat_id: int) -> List[int]:
    """Get list of authorized users."""
    db = get_edit_tracker_db()
    return await db.get_authorized_users(chat_id)


async def log_edit_action(
    chat_id: int,
    user_id: int,
    message_id: int,
    action: str,
    timestamp: Optional[datetime] = None
) -> bool:
    """Log an edit action."""
    db = get_edit_tracker_db()
    return await db.log_edit_action(chat_id, user_id, message_id, action, timestamp)


async def cleanup_chat_data(chat_id: int) -> bool:
    """Cleanup all data for a chat."""
    db = get_edit_tracker_db()
    return await db.cleanup_chat_data(chat_id)


async def get_stats() -> Dict[str, Any]:
    """Get global statistics."""
    db = get_edit_tracker_db()
    return await db.get_stats()


async def initialize_database():
    """
    Initialize database and create indexes.
    Should be called during bot startup.
    """
    db = get_edit_tracker_db()
    await db.create_indexes()
    logger.info("Edit tracker database initialized and indexed")


logger.info("Edit tracker database module loaded successfully")
