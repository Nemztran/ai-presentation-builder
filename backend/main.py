import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

import jsonschema
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from document_reader import read_uploaded_document
from prompts import FILE_PROMPT_TEMPLATE, SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from pptx_exporter import build_pptx


BASE_DIR = Path(__file__).resolve().parent
DECK_SCHEMA = json.loads((BASE_DIR / "deck_schema.json").read_text(encoding="utf-8"))
FALLBACK_DECK = json.loads((BASE_DIR / "fallback_deck.json").read_text(encoding="utf-8"))
ASSET_ROOT = Path(tempfile.gettempdir()) / "ai_presentation_builder_assets"
ASSET_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AI Presentation Builder API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/assets", StaticFiles(directory=str(ASSET_ROOT)), name="assets")


class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    num_slides: int = Field(default=6, ge=3, le=15)
    audience: str = "general"
    tone: str = "professional"


class ExportRequest(BaseModel):
    deck: dict[str, Any]
    enable_transitions: bool = True


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate-deck")
async def generate_deck(req: GenerateRequest):
    """Old topic-based endpoint. Kept for compatibility."""
    prompt = USER_PROMPT_TEMPLATE.format(
        num_slides=req.num_slides,
        topic=req.topic,
        audience=req.audience,
        tone=req.tone,
    )

    deck = call_ai_with_retry(prompt, max_retries=3)

    if deck.get("deck_id") == "fallback_deck":
        deck = patch_fallback_deck(deck, req.topic)

    return {"success": True, "deck": deck}


@app.post("/generate-deck-from-file")
async def generate_deck_from_file(
    file: UploadFile = File(...),
    num_slides: int = Form(default=6),
    audience: str = Form(default="general"),
    tone: str = Form(default="professional"),
):
    """Upload .txt/.md/.docx and generate a deck. DOCX images are extracted and reused in preview/PPTX."""
    if num_slides < 3 or num_slides > 15:
        raise HTTPException(status_code=422, detail="num_slides must be between 3 and 15")

    extracted = await read_uploaded_document(file, ASSET_ROOT, static_prefix="/assets")

    image_summary = "\n".join(
        f"- {img['image_id']}: {img['caption']} ({img['filename']})" for img in extracted.images[:12]
    ) or "No embedded images found."

    prompt = FILE_PROMPT_TEMPLATE.format(
        num_slides=num_slides,
        audience=audience,
        tone=tone,
        text_content=extracted.text[:12000],
        image_summary=image_summary,
    )

    deck = call_ai_with_retry(prompt, max_retries=3)

    if deck.get("deck_id") == "fallback_deck":
        title = infer_title_from_text(extracted.text, extracted.filename)
        deck = build_demo_deck_from_document(title, extracted.text, extracted.images, num_slides)
    else:
        deck = attach_source_assets(deck, extracted.images, extracted.filename)

    return {
        "success": True,
        "deck": deck,
        "source_filename": extracted.filename,
        "image_count": len(extracted.images),
        "images": [{k: img[k] for k in ("image_id", "filename", "url", "caption") if k in img} for img in extracted.images],
    }


@app.post("/export-pptx")
async def export_pptx(req: ExportRequest):
    try:
        jsonschema.validate(req.deck, DECK_SCHEMA)
    except jsonschema.ValidationError as e:
        raise HTTPException(status_code=422, detail=f"Invalid deck JSON: {e.message}")

    safe_title = re.sub(r"[^a-zA-Z0-9_-]+", "_", req.deck.get("title", "deck")).strip("_") or "deck"
    output_path = Path(tempfile.gettempdir()) / f"{safe_title}_{uuid.uuid4().hex[:8]}.pptx"
    build_pptx(req.deck, str(output_path), enable_transitions=req.enable_transitions)

    return FileResponse(
        str(output_path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=f"{safe_title}.pptx",
    )


def call_ai_with_retry(prompt: str, max_retries: int = 3) -> dict[str, Any]:
    """
    Uses Claude API if ANTHROPIC_API_KEY is set.
    Without the key, returns fallback deck so the app can still demo end-to-end.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return FALLBACK_DECK

    try:
        import anthropic
    except ImportError:
        raise HTTPException(status_code=500, detail="Missing package: anthropic. Run: pip install -r requirements.txt")

    client = anthropic.Anthropic(api_key=api_key)
    last_error = None

    for _ in range(max_retries):
        try:
            msg = client.messages.create(
                model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            raw = msg.content[0].text.strip()
            raw = strip_markdown_fence(raw)
            deck = json.loads(raw)
            jsonschema.validate(deck, DECK_SCHEMA)
            return deck
        except Exception as e:
            last_error = e

    print(f"[WARN] AI generation failed after retries: {last_error}")
    return FALLBACK_DECK


def strip_markdown_fence(text: str) -> str:
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return text


def infer_title_from_text(text: str, filename: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip().lstrip("#").strip()
        if len(cleaned) >= 5:
            return cleaned[:80]
    return Path(filename).stem[:80] or "Uploaded Document Presentation"


def patch_fallback_deck(deck: dict[str, Any], topic: str) -> dict[str, Any]:
    patched = json.loads(json.dumps(deck))
    patched["deck_id"] = f"demo_{uuid.uuid4().hex[:8]}"
    patched["title"] = topic[:80]
    patched["topic"] = topic
    patched["slides"][0]["content"]["heading"] = topic[:80]
    patched["slides"][0]["content"]["subheading"] = "Demo deck generated without API key"
    return patched


def attach_source_assets(deck: dict[str, Any], images: list[dict[str, Any]], filename: str) -> dict[str, Any]:
    deck = json.loads(json.dumps(deck))
    deck["source_filename"] = filename
    deck["assets"] = {img["image_id"]: img for img in images}

    image_cursor = 0
    attachable = [s for s in deck.get("slides", []) if s.get("layout") not in {"closing"}]
    image_text_slides = [s for s in attachable if s.get("layout") == "image_text"]

    # Prefer explicit image_text slides, then fill other content slides.
    target_slides = image_text_slides or [s for s in attachable if s.get("layout") != "title"]
    for slide in target_slides:
        if image_cursor >= len(images):
            break
        slide.setdefault("content", {})["image_id"] = images[image_cursor]["image_id"]
        slide.setdefault("content", {})["image_url"] = images[image_cursor]["url"]
        slide.setdefault("content", {})["image_caption"] = images[image_cursor]["caption"]
        if slide.get("layout") in {"bullet", "two_column"} and image_cursor < max(1, len(images)):
            slide["layout"] = "image_text"
        image_cursor += 1

    # Make title slide visually richer if the document contains images.
    if images and deck.get("slides"):
        first = deck["slides"][0]
        first.setdefault("content", {})["image_id"] = images[0]["image_id"]
        first.setdefault("content", {})["image_url"] = images[0]["url"]

    for idx, slide in enumerate(deck.get("slides", [])):
        slide.setdefault("transition", "fade" if idx % 2 == 0 else "push")

    return deck


def build_demo_deck_from_document(title: str, text: str, images: list[dict[str, Any]], num_slides: int) -> dict[str, Any]:
    lines = [line.strip(" #\t") for line in text.splitlines() if len(line.strip()) > 3]
    bullets = []
    for line in lines[1:]:
        cleaned = re.sub(r"^[-•*\d.)\s]+", "", line).strip()
        if 8 <= len(cleaned) <= 180:
            bullets.append(cleaned)
        if len(bullets) >= 18:
            break

    if not bullets:
        words = text.split()
        bullets = [" ".join(words[i:i + 18]) for i in range(0, min(len(words), 90), 18)]

    slide_count = max(3, min(num_slides, 15))
    deck = {
        "deck_id": f"demo_docx_{uuid.uuid4().hex[:8]}",
        "title": title[:80],
        "topic": f"Generated from uploaded document",
        "theme": "professional",
        "source_filename": title,
        "assets": {img["image_id"]: img for img in images},
        "slides": [],
    }

    first_image = images[0] if images else None
    title_slide = {
        "slide_id": 1,
        "layout": "title",
        "content": {
            "heading": title[:80],
            "subheading": "Auto-generated demo deck from DOCX content and embedded images",
        },
        "speaker_notes": "Introduce the document topic and explain that this deck was generated from the uploaded source file.",
        "visual_hint": "Source document hero image",
        "transition": "fade",
    }
    if first_image:
        title_slide["content"]["image_id"] = first_image["image_id"]
        title_slide["content"]["image_url"] = first_image["url"]
    deck["slides"].append(title_slide)

    middle_slots = max(1, slide_count - 2)
    bullet_index = 0
    for i in range(middle_slots):
        chunk = bullets[bullet_index:bullet_index + 4]
        bullet_index += 4
        if not chunk:
            chunk = bullets[:4] or ["Key information extracted from the uploaded document"]
        image = images[i % len(images)] if images else None
        layout = "image_text" if image else ("two_column" if i % 3 == 1 else "bullet")
        content: dict[str, Any] = {
            "heading": chunk[0][:80],
            "bullets": [{"text": item[:130]} for item in chunk[:4]],
        }
        if layout == "two_column":
            left = chunk[:2]
            right = chunk[2:4] or chunk[:2]
            content["left_column"] = "\n".join(f"• {item}" for item in left)
            content["right_column"] = "\n".join(f"• {item}" for item in right)
        if image:
            content["image_id"] = image["image_id"]
            content["image_url"] = image["url"]
            content["image_caption"] = image["caption"]

        deck["slides"].append({
            "slide_id": len(deck["slides"]) + 1,
            "layout": layout,
            "content": content,
            "speaker_notes": "Explain this slide by summarizing the extracted points instead of reading every bullet word-for-word.",
            "visual_hint": image["caption"] if image else "Clean infographic based on document content",
            "transition": "push" if i % 2 else "fade",
        })

    deck["slides"].append({
        "slide_id": len(deck["slides"]) + 1,
        "layout": "closing",
        "content": {
            "heading": "Key Takeaway",
            "subheading": "The uploaded document has been transformed into a concise visual presentation.",
            "cta": "Export the complete PPTX",
        },
        "speaker_notes": "Close by highlighting the most important takeaway and invite questions.",
        "visual_hint": "Simple conclusion slide",
        "transition": "fade",
    })
    return deck
