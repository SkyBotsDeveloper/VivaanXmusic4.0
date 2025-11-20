"""
Smart Abuse Detector Module
Pattern-based detection of abusive language with multiple variations
Part of VivaanXMusic4.0 Anti-Abuse System

Handles:
- Exact word matching
- Space/dot/comma separation (f.u,c k)
- Leetspeak variations (f4ck, fuk)
- Unicode tricks
- Zero-width characters
- Repeated characters
"""

import re
import logging
from typing import List, Dict, Tuple, Optional
import unicodedata

logger = logging.getLogger(__name__)


class AbuseDetector:
    """Smart abuse detector with pattern generation and matching"""
    
    def __init__(self):
        """Initialize the abuse detector"""
        self.cache = {}  # Cache for compiled regex patterns
        
        # Leetspeak mappings
        self.leetspeak_map = {
            'a': ['@', '4', '/-\\', '4', 'ａ'],
            'e': ['3', 'ə', 'ё', 'е', 'ｅ'],
            'i': ['1', '!', '|', 'ɪ', 'ｉ'],
            'o': ['0', '()', 'ο', 'о', 'ｏ'],
            's': ['5', '$', '§', 'ѕ', 'ｓ'],
            't': ['7', '+', 'ţ', 'т', 'ｔ'],
            'l': ['1', '|', '!', 'ł', 'ｌ'],
            'z': ['2', 'ž', 'з', 'ｚ'],
            'g': ['9', '&', 'ɡ', 'г', 'ｇ'],
            'b': ['8', 'ḃ', 'б', 'ｂ'],
        }
        
        # Common separators to try
        self.separators = [
            '',           # No separation (fuck)
            ' ',          # Space (f u c k)
            '.',          # Dot (f.u.c.k)
            ',',          # Comma (f,u,c,k)
            '_',          # Underscore (f_u_c_k)
            '-',          # Dash (f-u-c-k)
            '*',          # Asterisk (f*u*c*k)
            '|',          # Pipe (f|u|c|k)
            '/',          # Slash (f/u/c/k)
        ]
    
    # ────────────────────────────────────────────────────────────
    # Text Normalization
    # ────────────────────────────────────────────────────────────
    
    def normalize_text(self, text: str) -> str:
        """
        Normalize text for abuse detection
        
        Args:
            text: Input text
            
        Returns:
            str: Normalized text
        """
        if not text:
            return ""
        
        # Convert to lowercase
        text = text.lower()
        
        # Remove zero-width characters
        text = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)
        
        # Convert unicode to ASCII (normalize)
        text = unicodedata.normalize('NFKD', text)
        text = text.encode('ascii', 'ignore').decode('ascii')
        
        # Remove extra spaces
        text = ' '.join(text.split())
        
        return text
    
    def remove_separators(self, text: str) -> str:
        """
        Remove common separators from text
        
        Args:
            text: Input text
            
        Returns:
            str: Text without separators
        """
        # Remove common separators
        text = re.sub(r'[\s\.\,\-_\*\|/]+', '', text)
        return text
    
    # ────────────────────────────────────────────────────────────
    # Pattern Generation
    # ────────────────────────────────────────────────────────────
    
    def generate_patterns(self, word: str) -> List[str]:
        """
        Generate multiple pattern variations of a word
        
        Args:
            word: Base abusive word
            
        Returns:
            list: List of pattern variations
        """
        patterns = []
        word = word.lower().strip()
        
        if not word:
            return patterns
        
        # 1. Exact word
        patterns.append(word)
        
        # 2. Separated characters (f u c k)
        patterns.append(' '.join(word))
        
        # 3. Dot separated (f.u.c.k)
        patterns.append('.'.join(word))
        
        # 4. Comma separated (f,u,c,k)
        patterns.append(','.join(word))
        
        # 5. Underscore separated (f_u_c_k)
        patterns.append('_'.join(word))
        
        # 6. Dash separated (f-u-c-k)
        patterns.append('-'.join(word))
        
        # 7. Asterisk separated (f*u*c*k)
        patterns.append('*'.join(word))
        
        # 8. Pipe separated (f|u|c|k)
        patterns.append('|'.join(word))
        
        # 9. Repeated characters (fuuuck, fuccck)
        for i, char in enumerate(word):
            # Replace each character with doubled version
            repeated = word[:i] + char * 2 + word[i+1:]
            if repeated != word:
                patterns.append(repeated)
        
        # 10. Leetspeak variations
        leetspeak_vars = self.generate_leetspeak(word)
        patterns.extend(leetspeak_vars)
        
        # Remove duplicates
        patterns = list(set(patterns))
        
        logger.debug(f"[AbuseDetector] Generated {len(patterns)} patterns for '{word}'")
        return patterns
    
    def generate_leetspeak(self, word: str) -> List[str]:
        """
        Generate leetspeak variations
        
        Args:
            word: Base word
            
        Returns:
            list: Leetspeak variations
        """
        variations = [word]
        
        # Find all characters that have leetspeak alternatives
        char_positions = {}
        for i, char in enumerate(word):
            if char in self.leetspeak_map:
                char_positions[i] = char
        
        # Generate combinations (limit to avoid explosion)
        if len(char_positions) > 3:
            # Too many variations, just do simple substitutions
            for pos, char in list(char_positions.items())[:3]:
                for replacement in self.leetspeak_map[char][:2]:
                    var = word[:pos] + replacement + word[pos+1:]
                    variations.append(var)
        else:
            # Generate all combinations
            positions = list(char_positions.keys())
            
            for pos in positions:
                char = char_positions[pos]
                for replacement in self.leetspeak_map[char]:
                    var = word[:pos] + replacement + word[pos+1:]
                    variations.append(var)
        
        return variations
    
    # ────────────────────────────────────────────────────────────
    # Detection Methods
    # ────────────────────────────────────────────────────────────
    
    def create_regex_pattern(self, word: str) -> str:
        """
        Create a flexible regex pattern for a word
        
        Args:
            word: Base word
            
        Returns:
            str: Regex pattern
        """
        # Escape special regex characters
        word = re.escape(word)
        
        # Allow optional separators between characters
        # e.g., f[.\s,_-]*u[.\s,_-]*c[.\s,_-]*k
        pattern = r'[.\s,_\-*|/]*'.join(word)
        
        # Add word boundaries
        pattern = r'\b' + pattern + r'\b'
        
        return pattern
    
    def detect_abuse(self, text: str, abuse_words: List[str], strict_mode: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Detect if text contains abusive language
        
        Args:
            text: Text to check
            abuse_words: List of abusive words
            strict_mode: Enable strict pattern matching
            
        Returns:
            tuple: (detected, matched_word)
        """
        if not text or not abuse_words:
            return False, None
        
        # Normalize text
        normalized_text = self.normalize_text(text)
        text_no_sep = self.remove_separators(normalized_text)
        
        for word in abuse_words:
            word_lower = word.lower().strip()
            
            # 1. Exact match in normalized text
            if word_lower in normalized_text:
                logger.debug(f"[AbuseDetector] Exact match found: {word_lower}")
                return True, word_lower
            
            # 2. Match without separators
            if word_lower in text_no_sep:
                logger.debug(f"[AbuseDetector] No-sep match found: {word_lower}")
                return True, word_lower
            
            # 3. Pattern-based matching
            patterns = self.generate_patterns(word_lower)
            
            for pattern in patterns:
                # Create regex
                regex_pattern = self.create_regex_pattern(pattern)
                
                try:
                    if re.search(regex_pattern, normalized_text, re.IGNORECASE):
                        logger.debug(f"[AbuseDetector] Pattern match found: {word_lower}")
                        return True, word_lower
                except re.error as e:
                    logger.warning(f"[AbuseDetector] Regex error: {e}")
                    continue
            
            # 4. Fuzzy matching (if strict mode)
            if strict_mode:
                # Check for partial matches
                if self.fuzzy_match(normalized_text, word_lower):
                    logger.debug(f"[AbuseDetector] Fuzzy match found: {word_lower}")
                    return True, word_lower
        
        return False, None
    
    def fuzzy_match(self, text: str, word: str, threshold: float = 0.75) -> bool:
        """
        Fuzzy matching for similar words
        
        Args:
            text: Text to search in
            word: Word to match
            threshold: Match threshold (0-1)
            
        Returns:
            bool: True if fuzzy match found
        """
        try:
            from difflib import SequenceMatcher
            
            # Split text into words
            text_words = re.findall(r'\b\w+\b', text.lower())
            
            for text_word in text_words:
                # Calculate similarity
                ratio = SequenceMatcher(None, text_word, word).ratio()
                
                if ratio >= threshold:
                    return True
            
            return False
        except Exception as e:
            logger.error(f"[AbuseDetector] Fuzzy match error: {e}")
            return False
    
    # ────────────────────────────────────────────────────────────
    # Batch Detection
    # ────────────────────────────────────────────────────────────
    
    def detect_multiple(self, text: str, abuse_words: List[str]) -> List[str]:
        """
        Detect all abusive words in text
        
        Args:
            text: Text to check
            abuse_words: List of abusive words
            
        Returns:
            list: List of detected words
        """
        detected = []
        
        for word in abuse_words:
            is_detected, matched = self.detect_abuse(text, [word])
            if is_detected:
                detected.append(matched)
        
        return detected
    
    # ────────────────────────────────────────────────────────────
    # Caching & Performance
    # ────────────────────────────────────────────────────────────
    
    def clear_cache(self):
        """Clear pattern cache"""
        self.cache.clear()
        logger.info("[AbuseDetector] Cache cleared")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics"""
        return {
            "cached_patterns": len(self.cache),
            "cache_size_bytes": sum(
                len(str(k)) + len(str(v))
                for k, v in self.cache.items()
            )
        }
    
    # ────────────────────────────────────────────────────────────
    # Utility Methods
    # ────────────────────────────────────────────────────────────
    
    def split_words(self, text: str) -> List[str]:
        """
        Split text into words intelligently
        
        Args:
            text: Input text
            
        Returns:
            list: List of words
        """
        # Split by common separators
        words = re.split(r'[\s\.\,\-_\*\|/]+', text.lower())
        # Remove empty strings
        words = [w for w in words if w]
        return words
    
    def get_detection_confidence(self, text: str, word: str) -> float:
        """
        Get confidence score for detection
        
        Args:
            text: Text to check
            word: Word to match
            
        Returns:
            float: Confidence score (0-1)
        """
        try:
            normalized = self.normalize_text(text)
            
            # Exact match = high confidence
            if word.lower() in normalized:
                return 1.0
            
            # Partial match
            if word.lower() in self.remove_separators(normalized):
                return 0.8
            
            # Pattern match
            is_detected, _ = self.detect_abuse(text, [word])
            if is_detected:
                return 0.6
            
            return 0.0
        except Exception as e:
            logger.error(f"[AbuseDetector] Confidence error: {e}")
            return 0.0


# ────────────────────────────────────────────────────────────
# Global instance
# ────────────────────────────────────────────────────────────

abuse_detector: Optional[AbuseDetector] = None


def init_abuse_detector() -> AbuseDetector:
    """
    Initialize the global abuse detector
    
    Returns:
        AbuseDetector: Initialized detector instance
    """
    global abuse_detector
    
    abuse_detector = AbuseDetector()
    logger.info("[AbuseDetector] Initialized successfully")
    
    return abuse_detector


def get_detector() -> AbuseDetector:
    """
    Get the global abuse detector instance
    
    Returns:
        AbuseDetector: Detector instance
    """
    global abuse_detector
    
    if abuse_detector is None:
        abuse_detector = init_abuse_detector()
    
    return abuse_detector
