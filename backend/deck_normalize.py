"""Map common LLM JSON shapes into the app's deck schema before validation."""

from __future__ import annotations

import re
import uuid
from typing import Any

VALID_LAYOUTS = {"title", "bullet", "two_column", "image_text", "quote", "closing"}
VALID_THEMES = {"professional", "minimal", "bold", "dark"}
VALID_TRANSITIONS = {"fade", "push", "wipe"}

THEME_ALIASES = {
    "slate": "dark",
    "corporate": "professional",
    "business": "professional",
    "modern": "professional",
    "clean": "minimal",
    "light": "minimal",
    "vibrant": "bold",
    "night": "dark",
}


def normalize_llm_deck(raw: Any) -> dict[str, Any]:
    if isinstance(raw, list):
        raw = {"slides": raw}

    if not isinstance(raw, dict):
        raise ValueError("Deck must be a JSON object or array of slides")

    slides_raw = raw.get("slides")
    if slides_raw is None and isinstance(raw.get("deck"), dict):
        raw = raw["deck"]
        slides_raw = raw.get("slides")

    slides_in = slides_raw if isinstance(slides_raw, list) else []
    slides = [_normalize_slide(slide, index) for index, slide in enumerate(slides_in, start=1)]

    title = _first_str(raw, "title", "deck_title", "name") or _slide_heading(slides[0]) if slides else "Presentation"
    theme = _normalize_theme(raw.get("theme") or _first_slide_theme(slides_in))

    deck: dict[str, Any] = {
        "deck_id": _first_str(raw, "deck_id", "id") or f"deck_{uuid.uuid4().hex[:10]}",
        "title": _truncate(title, 80),
        "theme": theme,
        "slides": slides,
    }

    topic = _first_str(raw, "topic", "subject")
    if topic:
        deck["topic"] = _truncate(topic, 200)

    return deck


def _normalize_slide(slide: Any, index: int) -> dict[str, Any]:
    if not isinstance(slide, dict):
        slide = {"content": {"heading": str(slide)}}

    layout = _normalize_layout(slide.get("layout"), slide)
    content = _normalize_content(slide.get("content") or slide, layout)

    out: dict[str, Any] = {
        "slide_id": _normalize_slide_id(slide, index),
        "layout": layout,
        "content": content,
    }

    for key in ("speaker_notes", "visual_hint", "image_id", "image_path"):
        val = slide.get(key)
        if val:
            out[key] = _truncate(str(val), 500 if key == "speaker_notes" else 100)

    transition = slide.get("transition")
    if transition in VALID_TRANSITIONS:
        out["transition"] = transition
    elif transition:
        out["transition"] = "fade"

    return out


def _normalize_slide_id(slide: dict[str, Any], index: int) -> int:
    for key in ("slide_id", "slide_number", "number", "id"):
        val = slide.get(key)
        if isinstance(val, int):
            return val
        if isinstance(val, str) and val.isdigit():
            return int(val)
    return index


def _normalize_layout(layout: Any, slide: dict[str, Any]) -> str:
    if isinstance(layout, str):
        key = layout.strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "two_columns": "two_column",
            "2_column": "two_column",
            "image_and_text": "image_text",
            "title_slide": "title",
            "end": "closing",
            "conclusion": "closing",
            "closing_slide": "closing",
        }
        key = aliases.get(key, key)
        if key in VALID_LAYOUTS:
            return key

    content = slide.get("content") if isinstance(slide.get("content"), dict) else slide
    if isinstance(content, dict) and content.get("quote"):
        return "quote"
    if isinstance(content, dict) and (
        content.get("left_column")
        or content.get("right_column")
        or content.get("col_1_bullets")
        or content.get("col_2_bullets")
    ):
        return "two_column"
    return "bullet"


def _normalize_content(content: Any, layout: str) -> dict[str, Any]:
    if not isinstance(content, dict):
        return {"heading": _truncate(str(content), 80)}

    out: dict[str, Any] = {}

    heading = _first_str(
        content,
        "heading",
        "title",
        "headline",
        "slide_title",
    )
    subheading = _first_str(
        content,
        "subheading",
        "subtitle",
        "tagline",
        "description",
    )

    if layout == "title":
        out["heading"] = _truncate(heading or "Presentation", 80)
        out["subheading"] = _truncate(
            subheading or _first_str(content, "presenter_info", "presenter") or "",
            120,
        )
    elif layout == "closing":
        out["heading"] = _truncate(heading or "Thank you", 80)
        out["subheading"] = _truncate(subheading or "", 120)
        cta = _first_str(content, "cta", "contact_info", "call_to_action", "contact")
        if cta:
            out["cta"] = _truncate(cta, 80)
    elif layout == "quote":
        quote = _first_str(content, "quote", "text", "body")
        if quote:
            out["quote"] = _truncate(_strip_md(quote), 300)
        author = _first_str(content, "author", "attribution", "source")
        if author:
            out["author"] = _truncate(author, 80)
        if not out.get("quote") and heading:
            out["quote"] = _truncate(_strip_md(heading), 300)
    elif layout == "two_column":
        out["heading"] = _truncate(heading or "", 80)
        out["left_column"] = _format_column(content, side=1)
        out["right_column"] = _format_column(content, side=2)
    else:
        if heading:
            out["heading"] = _truncate(heading, 80)
        if subheading:
            out["subheading"] = _truncate(subheading, 120)
        bullets = _normalize_bullets(content)
        if bullets:
            out["bullets"] = bullets
        elif subheading and layout == "bullet":
            out["bullets"] = [{"text": _truncate(_strip_md(subheading), 150)}]

    for key in ("image_id", "image_url", "image_caption", "image_path"):
        val = content.get(key)
        if val:
            out[key] = str(val)

    if not out and heading:
        out["heading"] = _truncate(heading, 80)

    return out or {"heading": "Slide"}


def _format_column(content: dict[str, Any], side: int) -> str:
    prefix = f"col_{side}"
    title = _first_str(
        content,
        f"{prefix}_title",
        f"column_{side}_title",
        "left_column_title" if side == 1 else "right_column_title",
    )
    bullets = (
        content.get(f"{prefix}_bullets")
        or content.get(f"column_{side}_bullets")
        or content.get("left_column" if side == 1 else "right_column")
    )

    if isinstance(bullets, str):
        return _truncate(bullets, 800)

    lines: list[str] = []
    if title:
        lines.append(title)
    if isinstance(bullets, list):
        for item in bullets:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
            else:
                text = str(item)
            text = _strip_md(text).strip()
            if text:
                lines.append(f"• {text}")

    if lines:
        return _truncate("\n".join(lines), 800)

    return _truncate(_first_str(content, "left_column" if side == 1 else "right_column") or "", 800)


def _normalize_bullets(content: dict[str, Any]) -> list[dict[str, str]]:
    raw = content.get("bullets") or content.get("points") or content.get("items")
    if not isinstance(raw, list):
        return []

    bullets: list[dict[str, str]] = []
    for item in raw[:6]:
        if isinstance(item, dict):
            text = item.get("text") or item.get("content") or item.get("bullet") or ""
            detail = item.get("detail") or item.get("subtext") or ""
        else:
            text = str(item)
            detail = ""

        text = _strip_md(text).strip()
        if not text:
            continue
        entry: dict[str, str] = {"text": _truncate(text, 150)}
        if detail:
            entry["detail"] = _truncate(_strip_md(str(detail)), 200)
        bullets.append(entry)

    return bullets


def _normalize_theme(theme: Any) -> str:
    if not theme:
        return "professional"
    key = str(theme).strip().lower()
    if key in VALID_THEMES:
        return key
    return THEME_ALIASES.get(key, "professional")


def _first_slide_theme(slides: list[Any]) -> Any:
    for slide in slides:
        if isinstance(slide, dict) and slide.get("theme"):
            return slide.get("theme")
    return None


def _slide_heading(slide: dict[str, Any]) -> str:
    content = slide.get("content")
    if isinstance(content, dict):
        return _first_str(content, "heading", "title") or ""
    return ""


def _first_str(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        val = data.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _strip_md(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    return text.strip()


def _truncate(text: str, max_len: int) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"
