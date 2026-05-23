"""Parse and repair JSON returned by LLMs."""

from __future__ import annotations

import json
import re
from typing import Any


def strip_markdown_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def extract_json_block(text: str) -> str:
    """Prefer a top-level object; fall back to array of slides."""
    text = text.strip()
    obj_start = text.find("{")
    arr_start = text.find("[")
    if obj_start == -1 and arr_start == -1:
        return text
    if obj_start != -1 and (arr_start == -1 or obj_start < arr_start):
        start = obj_start
        end = text.rfind("}")
    else:
        start = arr_start
        end = text.rfind("]")
    if end > start:
        return text[start : end + 1]
    return text


def repair_json_text(text: str) -> str:
    try:
        import json_repair

        return json_repair.repair_json(text)
    except ImportError:
        return text


def parse_llm_json(raw: str) -> Any:
    """
    Parse LLM output as JSON with repair fallbacks.
    Raises json.JSONDecodeError or ValueError if unrecoverable.
    """
    cleaned = strip_markdown_fence(raw)
    candidates: list[str] = []

    for piece in (cleaned, extract_json_block(cleaned)):
        if piece and piece not in candidates:
            candidates.append(piece)

    last_error: Exception | None = None
    for text in candidates:
        for use_repair in (False, True):
            try:
                payload = repair_json_text(text) if use_repair else text
                return json.loads(payload)
            except Exception as e:
                last_error = e
                continue

    if last_error:
        raise last_error
    raise ValueError("Empty LLM response")
