"""
Group Security Database Module
Handles bio checking configurations, warnings, and user whitelists
Part of VivaanXMusic Group Management System
"""

from typing import Dict, List, Optional
from VIVAANXMUSIC.core.mongo import mongodb

# Database collections
security_db = mongodb.group_security


class GroupSecurityDB:
    """Database operations for group security features"""
    
    def __init__(self):
        """Initialize database collections"""
        self.configs = security_db.configs
        self.warnings = security_db.warnings
        self.whitelist = security_db.whitelist
    
    # ==================== Configuration Management ====================
    
    async def get_config(self, chat_id: int) -> Dict:
        """
        Get security configuration for a group
        
        Args:
            chat_id (int): Chat ID
            
        Returns:
            Dict: Configuration with bio_check settings
        """
        config = await self.configs.find_one({"chat_id": chat_id})
        if not config:
            # Default configuration
            config = {
                "chat_id": chat_id,
                "bio_check": {
                    "enabled": True,
                    "warning_limit": 5,
                    "action": "mute"  # "mute" or "ban"
                }
            }
            await self.configs.insert_one(config)
        return config
    
    async def update_bio_config(self, chat_id: int, warning_limit: int, action: str):
        """
        Update bio checking configuration
        
        Args:
            chat_id (int): Chat ID
            warning_limit (int): Number of warnings before action
            action (str): Action to take ("mute" or "ban")
        """
        await self.configs.update_one(
            {"chat_id": chat_id},
            {"$set": {
                "bio_check.warning_limit": warning_limit,
                "bio_check.action": action,
                "bio_check.enabled": True
            }},
            upsert=True
        )
    
    async def toggle_bio_check(self, chat_id: int, enabled: bool):
        """
        Enable or disable bio checking for a group
        
        Args:
            chat_id (int): Chat ID
            enabled (bool): Enable/disable status
        """
        await self.configs.update_one(
            {"chat_id": chat_id},
            {"$set": {"bio_check.enabled": enabled}},
            upsert=True
        )
    
    # ==================== Warnings Management ====================
    
    async def get_warnings(self, chat_id: int, user_id: int) -> int:
        """
        Get warning count for a user in a specific chat
        
        Args:
            chat_id (int): Chat ID
            user_id (int): User ID
            
        Returns:
            int: Number of warnings
        """
        doc = await self.warnings.find_one({
            "chat_id": chat_id,
            "user_id": user_id
        })
        return doc.get("count", 0) if doc else 0
    
    async def add_warning(self, chat_id: int, user_id: int) -> int:
        """
        Add a warning to a user and return new count
        
        Args:
            chat_id (int): Chat ID
            user_id (int): User ID
            
        Returns:
            int: New warning count
        """
        await self.warnings.update_one(
            {"chat_id": chat_id, "user_id": user_id},
            {"$inc": {"count": 1}},
            upsert=True
        )
        return await self.get_warnings(chat_id, user_id)
    
    async def clear_warnings(self, chat_id: int, user_id: int):
        """
        Clear all warnings for a user
        
        Args:
            chat_id (int): Chat ID
            user_id (int): User ID
        """
        await self.warnings.delete_one({
            "chat_id": chat_id,
            "user_id": user_id
        })
    
    async def get_all_warned_users(self, chat_id: int) -> List[Dict]:
        """
        Get all users with warnings in a chat
        
        Args:
            chat_id (int): Chat ID
            
        Returns:
            List[Dict]: List of users with warnings
        """
        cursor = self.warnings.find({"chat_id": chat_id})
        return await cursor.to_list(length=None)
    
    # ==================== Whitelist Management ====================
    
    async def is_whitelisted(self, chat_id: int, user_id: int) -> bool:
        """
        Check if a user is whitelisted (trusted)
        
        Args:
            chat_id (int): Chat ID
            user_id (int): User ID
            
        Returns:
            bool: True if whitelisted
        """
        doc = await self.whitelist.find_one({
            "chat_id": chat_id,
            "user_id": user_id
        })
        return doc is not None
    
    async def add_whitelist(self, chat_id: int, user_id: int, username: str = None):
        """
        Add user to security whitelist
        
        Args:
            chat_id (int): Chat ID
            user_id (int): User ID
            username (str, optional): Username
        """
        await self.whitelist.update_one(
            {"chat_id": chat_id, "user_id": user_id},
            {"$set": {"username": username}},
            upsert=True
        )
    
    async def remove_whitelist(self, chat_id: int, user_id: int):
        """
        Remove user from whitelist
        
        Args:
            chat_id (int): Chat ID
            user_id (int): User ID
        """
        await self.whitelist.delete_one({
            "chat_id": chat_id,
            "user_id": user_id
        })
    
    async def get_whitelisted_users(self, chat_id: int) -> List[Dict]:
        """
        Get all whitelisted users in a chat
        
        Args:
            chat_id (int): Chat ID
            
        Returns:
            List[Dict]: List of whitelisted users
        """
        cursor = self.whitelist.find({"chat_id": chat_id})
        return await cursor.to_list(length=None)
    
    async def clear_all_whitelist(self, chat_id: int):
        """
        Clear entire whitelist for a chat
        
        Args:
            chat_id (int): Chat ID
        """
        await self.whitelist.delete_many({"chat_id": chat_id})


# Global database instance
gsdb = GroupSecurityDB()
