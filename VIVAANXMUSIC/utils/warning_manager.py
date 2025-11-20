"""
Warning Manager Module
Centralized warning system for abuse detection
Handles user warnings, actions, and notifications
Part of VivaanXMusic4.0 Anti-Abuse System
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class WarningAction(Enum):
    """Warning action types"""
    MUTE = "mute"
    BAN = "ban"
    DELETE_ONLY = "delete_only"
    WARN_ONLY = "warn_only"


class WarningMessage:
    """Warning message templates"""
    
    @staticmethod
    def get_warning_message(
        warnings: int,
        limit: int,
        action: str,
        username: str = "User"
    ) -> str:
        """
        Get warning message based on status
        
        Args:
            warnings: Current warning count
            limit: Warning limit
            action: Action type (mute, ban, delete_only, warn_only)
            username: Username of offender
            
        Returns:
            str: Warning message
        """
        if action == "warn_only":
            return (
                f"⚠️ **Warning**\n\n"
                f"{username}, your message was deleted for containing abusive language.\n\n"
                f"Please maintain respectful communication in this group."
            )
        
        elif action == "delete_only":
            if limit == 0:
                # Unlimited warnings
                return (
                    f"⚠️ **Warning**\n\n"
                    f"{username}, your message was deleted for containing abusive language.\n\n"
                    f"Please stop using such language. Messages will continue to be deleted if they contain abusive content."
                )
            
            remaining = limit - warnings
            
            if remaining <= 0:
                return (
                    f"⚠️ **Final Warning**\n\n"
                    f"{username}, you have reached the warning limit ({limit}/{limit}).\n\n"
                    f"Your messages will continue to be deleted if they contain abusive language."
                )
            
            elif remaining == 1:
                return (
                    f"🚨 **LAST WARNING**\n\n"
                    f"{username}, you have 1 warning left ({warnings}/{limit}).\n\n"
                    f"Your next violation will result in automatic deletion of all subsequent abusive messages."
                )
            
            else:
                return (
                    f"⚠️ **Warning {warnings}/{limit}**\n\n"
                    f"{username}, your message was deleted for containing abusive language.\n\n"
                    f"You have {remaining} warning(s) remaining before further action is taken."
                )
        
        elif action == "mute":
            if limit == 0:
                # Unlimited warnings
                return (
                    f"⚠️ **Warning**\n\n"
                    f"{username}, your message was deleted for containing abusive language.\n\n"
                    f"Continued violations may result in a mute."
                )
            
            remaining = limit - warnings
            
            if remaining <= 0:
                return (
                    f"🔇 **User Muted**\n\n"
                    f"{username} has been muted for {limit} warnings of abusive language.\n\n"
                    f"Please respect group rules and maintain appropriate language."
                )
            
            elif remaining == 1:
                return (
                    f"🚨 **FINAL WARNING**\n\n"
                    f"{username}, you have 1 warning left ({warnings}/{limit}).\n\n"
                    f"Your next violation will result in a **MUTE**."
                )
            
            else:
                return (
                    f"⚠️ **Warning {warnings}/{limit}**\n\n"
                    f"{username}, your message was deleted for containing abusive language.\n\n"
                    f"You have {remaining} warning(s) remaining before you are muted."
                )
        
        elif action == "ban":
            if limit == 0:
                # Unlimited warnings
                return (
                    f"⚠️ **Warning**\n\n"
                    f"{username}, your message was deleted for containing abusive language.\n\n"
                    f"Continued violations may result in a ban."
                )
            
            remaining = limit - warnings
            
            if remaining <= 0:
                return (
                    f"🚫 **User Banned**\n\n"
                    f"{username} has been permanently banned for repeated abusive language violations.\n\n"
                    f"Contact admins if you believe this was an error."
                )
            
            elif remaining == 1:
                return (
                    f"🚨 **FINAL WARNING**\n\n"
                    f"{username}, you have 1 warning left ({warnings}/{limit}).\n\n"
                    f"Your next violation will result in a **BAN**."
                )
            
            else:
                return (
                    f"⚠️ **Warning {warnings}/{limit}**\n\n"
                    f"{username}, your message was deleted for containing abusive language.\n\n"
                    f"You have {remaining} warning(s) remaining before you are banned."
                )
        
        return "⚠️ **Message Deleted** - Abusive language detected."
    
    @staticmethod
    def get_action_message(
        action: str,
        username: str = "User",
        duration: Optional[int] = None
    ) -> str:
        """
        Get action execution message
        
        Args:
            action: Action type (mute, ban, delete_only, warn_only)
            username: Username of offender
            duration: Duration for mute (minutes)
            
        Returns:
            str: Action message
        """
        if action == "mute":
            hours = duration / 60 if duration else 24
            return (
                f"🔇 **User Muted**\n\n"
                f"{username} has been muted for {hours:.1f} hours.\n\n"
                f"**Reason:** Repeated abusive language violations\n\n"
                f"This is a temporary measure."
            )
        
        elif action == "ban":
            return (
                f"🚫 **User Banned**\n\n"
                f"{username} has been permanently banned from this group.\n\n"
                f"**Reason:** Repeated abusive language violations\n\n"
                f"**Action:** Permanent ban"
            )
        
        elif action == "delete_only":
            return (
                f"❌ **Message Deleted**\n\n"
                f"{username}, your message contained abusive language and has been removed.\n\n"
                f"**Status:** Message deleted only (no penalty)"
            )
        
        elif action == "warn_only":
            return (
                f"⚠️ **Message Deleted**\n\n"
                f"{username}, your message contained abusive language.\n\n"
                f"Please maintain respectful communication."
            )
        
        return f"⚠️ **Action Taken**\n\nMessage deleted for policy violation."


class WarningManager:
    """Centralized warning management system"""
    
    def __init__(self):
        """Initialize warning manager"""
        self.pending_actions = {}  # Track pending user actions
    
    # ────────────────────────────────────────────────────────────
    # Warning Decision Logic
    # ────────────────────────────────────────────────────────────
    
    def should_take_action(
        self,
        warnings: int,
        warning_limit: int,
        action: str
    ) -> Dict[str, Any]:
        """
        Determine if action should be taken
        
        Args:
            warnings: Current warning count
            warning_limit: Warning limit (0 = unlimited)
            action: Action type
            
        Returns:
            dict: Action decision
        """
        result = {
            "should_act": False,
            "action": None,
            "reason": None,
            "message": None
        }
        
        # If limit is 0 (unlimited), never take action
        if warning_limit == 0:
            result["reason"] = "Unlimited warnings (no action)"
            return result
        
        # Check if limit reached
        if warnings >= warning_limit:
            result["should_act"] = True
            result["action"] = action
            
            if action == "mute":
                result["reason"] = "Warning limit reached - muting user"
            elif action == "ban":
                result["reason"] = "Warning limit reached - banning user"
            elif action == "delete_only":
                result["reason"] = "Delete only mode - no punishment"
            elif action == "warn_only":
                result["reason"] = "Warn only mode - no punishment"
        
        return result
    
    def get_action_info(
        self,
        action: str,
        warnings: int = 0,
        limit: int = 0,
        duration_minutes: int = 1440
    ) -> Dict[str, Any]:
        """
        Get detailed action information
        
        Args:
            action: Action type
            warnings: Current warnings
            limit: Warning limit
            duration_minutes: Mute duration
            
        Returns:
            dict: Action information
        """
        return {
            "action_type": action,
            "is_punitive": action in ["mute", "ban"],
            "current_warnings": warnings,
            "warning_limit": limit,
            "warnings_remaining": max(0, limit - warnings),
            "duration_minutes": duration_minutes if action == "mute" else None,
            "is_permanent": action == "ban",
            "allows_continuation": action in ["delete_only", "warn_only"],
            "timestamp": datetime.now().isoformat()
        }
    
    # ────────────────────────────────────────────────────────────
    # Message Generation
    # ────────────────────────────────────────────────────────────
    
    def generate_warning_message(
        self,
        warnings: int,
        limit: int,
        action: str,
        username: str = "User",
        detected_word: Optional[str] = None
    ) -> str:
        """
        Generate appropriate warning message
        
        Args:
            warnings: Current warning count
            limit: Warning limit
            action: Action type
            username: Username of offender
            detected_word: Detected abusive word
            
        Returns:
            str: Formatted warning message
        """
        return WarningMessage.get_warning_message(
            warnings,
            limit,
            action,
            username
        )
    
    def generate_action_message(
        self,
        action: str,
        username: str = "User",
        duration: Optional[int] = None
    ) -> str:
        """
        Generate action execution message
        
        Args:
            action: Action type
            username: Username
            duration: Duration (for mute)
            
        Returns:
            str: Formatted action message
        """
        return WarningMessage.get_action_message(
            action,
            username,
            duration
        )
    
    # ────────────────────────────────────────────────────────────
    # Warning Status Methods
    # ────────────────────────────────────────────────────────────
    
    def is_warning_critical(
        self,
        warnings: int,
        limit: int
    ) -> bool:
        """
        Check if warning is critical (near limit)
        
        Args:
            warnings: Current warnings
            limit: Warning limit
            
        Returns:
            bool: True if critical
        """
        if limit == 0:
            return False
        
        return warnings >= limit - 1
    
    def get_warning_percentage(
        self,
        warnings: int,
        limit: int
    ) -> float:
        """
        Get warning percentage
        
        Args:
            warnings: Current warnings
            limit: Warning limit
            
        Returns:
            float: Percentage (0-100)
        """
        if limit == 0:
            return 0.0
        
        return min(100.0, (warnings / limit) * 100)
    
    def get_warning_status(
        self,
        warnings: int,
        limit: int,
        action: str
    ) -> Dict[str, Any]:
        """
        Get comprehensive warning status
        
        Args:
            warnings: Current warnings
            limit: Warning limit
            action: Action type
            
        Returns:
            dict: Status information
        """
        if limit == 0:
            return {
                "status": "unlimited_warnings",
                "warnings": warnings,
                "limit": limit,
                "percentage": 0.0,
                "is_critical": False,
                "action_at_limit": action,
                "action_imminent": False
            }
        
        return {
            "status": "limited_warnings",
            "warnings": warnings,
            "limit": limit,
            "remaining": max(0, limit - warnings),
            "percentage": self.get_warning_percentage(warnings, limit),
            "is_critical": self.is_warning_critical(warnings, limit),
            "action_at_limit": action,
            "action_imminent": warnings >= limit - 1
        }
    
    # ────────────────────────────────────────────────────────────
    # Action Type Helpers
    # ────────────────────────────────────────────────────────────
    
    def is_punitive_action(self, action: str) -> bool:
        """
        Check if action is punitive (removes user)
        
        Args:
            action: Action type
            
        Returns:
            bool: True if punitive
        """
        return action in ["mute", "ban"]
    
    def is_non_punitive_action(self, action: str) -> bool:
        """
        Check if action is non-punitive (only deletes messages)
        
        Args:
            action: Action type
            
        Returns:
            bool: True if non-punitive
        """
        return action in ["delete_only", "warn_only"]
    
    def get_action_severity(self, action: str) -> int:
        """
        Get action severity score
        
        Args:
            action: Action type
            
        Returns:
            int: Severity (0-3)
        """
        severity_map = {
            "warn_only": 0,
            "delete_only": 1,
            "mute": 2,
            "ban": 3
        }
        return severity_map.get(action, 0)
    
    def compare_actions(self, action1: str, action2: str) -> int:
        """
        Compare two actions
        
        Args:
            action1: First action
            action2: Second action
            
        Returns:
            int: -1 if action1 < action2, 0 if equal, 1 if action1 > action2
        """
        sev1 = self.get_action_severity(action1)
        sev2 = self.get_action_severity(action2)
        
        if sev1 < sev2:
            return -1
        elif sev1 > sev2:
            return 1
        else:
            return 0
    
    # ────────────────────────────────────────────────────────────
    # Validation Methods
    # ────────────────────────────────────────────────────────────
    
    def validate_action(self, action: str) -> bool:
        """
        Validate action type
        
        Args:
            action: Action to validate
            
        Returns:
            bool: True if valid
        """
        valid_actions = ["mute", "ban", "delete_only", "warn_only"]
        return action in valid_actions
    
    def validate_warning_limit(self, limit: int) -> bool:
        """
        Validate warning limit
        
        Args:
            limit: Limit to validate
            
        Returns:
            bool: True if valid
        """
        return limit >= 0 and limit <= 100
    
    def validate_mute_duration(self, minutes: int) -> bool:
        """
        Validate mute duration
        
        Args:
            minutes: Duration in minutes
            
        Returns:
            bool: True if valid
        """
        return 1 <= minutes <= 525600  # 1 minute to 1 year
    
    # ────────────────────────────────────────────────────────────
    # Utility Methods
    # ────────────────────────────────────────────────────────────
    
    def format_mute_duration(self, minutes: int) -> str:
        """
        Format mute duration as human-readable string
        
        Args:
            minutes: Duration in minutes
            
        Returns:
            str: Formatted duration
        """
        if minutes < 60:
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        elif minutes < 1440:
            hours = minutes // 60
            return f"{hours} hour{'s' if hours != 1 else ''}"
        elif minutes < 525600:
            days = minutes // 1440
            return f"{days} day{'s' if days != 1 else ''}"
        else:
            return "permanent"
    
    def get_next_action(self, current_action: str) -> Optional[str]:
        """
        Get next escalation action
        
        Args:
            current_action: Current action type
            
        Returns:
            str: Next action or None
        """
        escalation = {
            "warn_only": "delete_only",
            "delete_only": "mute",
            "mute": "ban",
            "ban": None
        }
        return escalation.get(current_action)
    
    def get_previous_action(self, current_action: str) -> Optional[str]:
        """
        Get previous action in escalation
        
        Args:
            current_action: Current action type
            
        Returns:
            str: Previous action or None
        """
        deescalation = {
            "delete_only": "warn_only",
            "mute": "delete_only",
            "ban": "mute",
            "warn_only": None
        }
        return deescalation.get(current_action)
    
    # ────────────────────────────────────────────────────────────
    # Statistics & Analytics
    # ────────────────────────────────────────────────────────────
    
    def get_escalation_tree(self) -> Dict[str, Any]:
        """
        Get escalation action tree
        
        Returns:
            dict: Action escalation information
        """
        return {
            "levels": [
                {
                    "level": 1,
                    "action": "warn_only",
                    "description": "Message deleted, warning only"
                },
                {
                    "level": 2,
                    "action": "delete_only",
                    "description": "Message deleted, no punishment"
                },
                {
                    "level": 3,
                    "action": "mute",
                    "description": "User muted for configured duration"
                },
                {
                    "level": 4,
                    "action": "ban",
                    "description": "User permanently banned"
                }
            ]
        }


# ────────────────────────────────────────────────────────────
# Global instance
# ────────────────────────────────────────────────────────────

warning_manager: Optional[WarningManager] = None


def init_warning_manager() -> WarningManager:
    """
    Initialize the global warning manager
    
    Returns:
        WarningManager: Initialized manager instance
    """
    global warning_manager
    
    warning_manager = WarningManager()
    logger.info("[WarningManager] Initialized successfully")
    
    return warning_manager


def get_warning_manager() -> WarningManager:
    """
    Get the global warning manager instance
    
    Returns:
        WarningManager: Manager instance
    """
    global warning_manager
    
    if warning_manager is None:
        warning_manager = init_warning_manager()
    
    return warning_manager
