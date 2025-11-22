import re
import logging
from typing import List, Dict, Tuple, Optional
import unicodedata

logger = logging.getLogger(__name__)

class AbuseDetector:
    """Safe and robust abuse detector."""

    def normalize_text(self, text: str) -> str:
        if not text:
            return ""
        text = text.lower()
        text = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)
        text = unicodedata.normalize('NFKD', text)
        text = text.encode('ascii', 'ignore').decode('ascii')
        text = ' '.join(text.split())
        return text

    def remove_separators(self, text: str) -> str:
        return re.sub(r'[\s\.\,\-_\*\|/]+', '', text)

    # Replace this detect_abuse method with the one below:
    def detect_abuse(self, text: str, abuse_words: List[str], strict_mode: bool = False) -> Tuple[bool, Optional[str]]:
        if not text or not abuse_words:
            return False, None

        # Always normalize input text
        normalized_text = self.normalize_text(text)
        text_no_sep = self.remove_separators(normalized_text)

        for word in abuse_words:
            word_lower = word.lower().strip()

            # 1. Require safe, whole-word match (no accidental substring matches)
            if re.search(rf"\b{re.escape(word_lower)}\b", normalized_text):
                logger.debug(f"[AbuseDetector] Word boundary match: {word_lower}")
                return True, word_lower

            # 2. STRICT mode: enable aggressive matching—pattern, leet, etc.
            if strict_mode:
                # Separated and leetspeak patterns, repeated chars, etc.
                # Pattern: word with separators between every letter
                sep_pattern = r"\b"
                for c in word_lower:
                    char = re.escape(c)
                    sep_pattern += f"{char}[.\s,_\-*|/]*"
                sep_pattern = sep_pattern.rstrip("[.\s,_\-*|/]*") + r"\b"
                try:
                    if re.search(sep_pattern, normalized_text):
                        logger.debug(f"[AbuseDetector] Pattern/sep match ({sep_pattern}): {word_lower}")
                        return True, word_lower
                except re.error as e:
                    logger.warning(f"[AbuseDetector] Regex error in strict mode: {e}")

                # Fuzzy match (optional, strict only)
                if self.fuzzy_match(normalized_text, word_lower, threshold=0.85):
                    logger.debug(f"[AbuseDetector] Fuzzy (strict) match: {word_lower}")
                    return True, word_lower

        return False, None

    def fuzzy_match(self, text: str, word: str, threshold: float = 0.85) -> bool:
        try:
            from difflib import SequenceMatcher
            text_words = re.findall(r'\b\w+\b', text.lower())
            for text_word in text_words:
                ratio = SequenceMatcher(None, text_word, word).ratio()
                if ratio >= threshold:
                    return True
            return False
        except Exception as e:
            logger.error(f"[AbuseDetector] Fuzzy match error: {e}")
            return False

    def split_words(self, text: str) -> List[str]:
        words = re.split(r'[\s\.\,\-_\*\|/]+', text.lower())
        words = [w for w in words if w]
        return words

# Global singleton
abuse_detector: Optional[AbuseDetector] = None

def init_abuse_detector() -> AbuseDetector:
    global abuse_detector
    abuse_detector = AbuseDetector()
    logger.info("[AbuseDetector] Initialized successfully (zero false positives mode)")
    return abuse_detector

def get_detector() -> AbuseDetector:
    global abuse_detector
    if abuse_detector is None:
        abuse_detector = init_abuse_detector()
    return abuse_detector
