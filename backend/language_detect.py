"""Lightweight language detection using Unicode character-range heuristics.

No external dependencies required. Covers the most common languages that
users are likely to upload: Vietnamese, Chinese, Japanese, Korean, Arabic,
Thai, Russian/Cyrillic, and falls back to English.
"""

from __future__ import annotations
import re


# Each entry: (language_name, regex_pattern_for_script_characters)
_SCRIPT_RULES: list[tuple[str, str]] = [
    # Vietnamese: Latin + diacritics unique to Vietnamese
    ("Vietnamese", r"[àáâãèéêìíòóôõùúýăđơư]"),
    # Chinese (CJK Unified Ideographs)
    ("Chinese", r"[\u4e00-\u9fff\u3400-\u4dbf]"),
    # Japanese: Hiragana or Katakana
    ("Japanese", r"[\u3040-\u309f\u30a0-\u30ff]"),
    # Korean: Hangul
    ("Korean", r"[\uac00-\ud7af\u1100-\u11ff]"),
    # Arabic
    ("Arabic", r"[\u0600-\u06ff\u0750-\u077f]"),
    # Thai
    ("Thai", r"[\u0e00-\u0e7f]"),
    # Cyrillic (Russian, Ukrainian, etc.)
    ("Russian", r"[\u0400-\u04ff]"),
    # Hebrew
    ("Hebrew", r"[\u0590-\u05ff]"),
    # Devanagari (Hindi, Sanskrit, etc.)
    ("Hindi", r"[\u0900-\u097f]"),
    # Greek
    ("Greek", r"[\u0370-\u03ff]"),
]

# Minimum fraction of chars that must match a script to be considered that language
_THRESHOLD = 0.04  # 4 % of sampled characters


def detect_language(text: str, sample_size: int = 2000) -> str:
    """Return a human-readable language name (e.g. 'Vietnamese', 'English').

    Uses a sample of the text for speed. Falls back to 'English' when no
    script-specific characters are found above the threshold.
    """
    if not text or not text.strip():
        return "English"

    sample = text[:sample_size]
    total = max(len(sample), 1)

    for lang, pattern in _SCRIPT_RULES:
        matches = len(re.findall(pattern, sample, re.IGNORECASE))
        if matches / total >= _THRESHOLD:
            return lang

    return "English"
