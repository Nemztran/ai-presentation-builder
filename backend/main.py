import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import jsonschema
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from deck_normalize import normalize_llm_deck
from document_reader import read_uploaded_document
from json_utils import parse_llm_json, strip_markdown_fence
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
    api_key: str = ""


class ExportRequest(BaseModel):
    deck: dict[str, Any]
    enable_transitions: bool = True


@app.get("/health")
def health():
    provider = resolve_llm_provider()
    return {
        "status": "ok",
        "llm_configured": provider is not None,
        "llm_provider": provider,
        "llm_model": _llm_model_name(provider),
    }


@app.post("/generate-deck")
async def generate_deck(req: GenerateRequest):
    """Old topic-based endpoint. Kept for compatibility."""
    prompt = USER_PROMPT_TEMPLATE.format(
        num_slides=req.num_slides,
        topic=req.topic,
        audience=req.audience,
        tone=req.tone,
    )

    deck, generation = call_ai_with_retry(prompt, max_retries=3, client_api_key=req.api_key)

    if deck.get("deck_id") == "fallback_deck":
        deck = patch_fallback_deck(deck, req.topic)
        if generation["source"] == "no_api_key":
            generation["source"] = "demo_no_key"
        else:
            generation["source"] = "demo_llm_error"

    return {"success": True, "deck": deck, "generation": generation}


@app.post("/generate-deck-from-file")
async def generate_deck_from_file(
    file: UploadFile = File(...),
    num_slides: int = Form(default=6),
    audience: str = Form(default="general"),
    tone: str = Form(default="professional"),
    api_key: str = Form(default=""),
):
    """Upload .txt/.md/.docx and generate a deck. DOCX images are extracted and reused in preview/PPTX."""
    if num_slides < 3 or num_slides > 15:
        raise HTTPException(status_code=422, detail="num_slides must be between 3 and 15")

    try:
        extracted = await read_uploaded_document(file, ASSET_ROOT, static_prefix="/assets")
    except HTTPException as exc:
        name = file.filename or "(no filename)"
        print(f"[WARN] Upload rejected ({name}): {exc.status_code} {exc.detail}")
        raise

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

    deck, generation = call_ai_with_retry(prompt, max_retries=3, client_api_key=api_key)

    if deck.get("deck_id") == "fallback_deck":
        title = infer_title_from_text(extracted.text, extracted.filename)
        deck = build_demo_deck_from_document(title, extracted.text, extracted.images, num_slides)
        if generation["source"] == "no_api_key":
            generation["source"] = "demo_document_no_key"
        else:
            generation["source"] = "demo_document_llm_error"
    else:
        deck = attach_source_assets(deck, extracted.images, extracted.filename)

    return {
        "success": True,
        "deck": deck,
        "generation": generation,
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
    build_pptx(
        req.deck,
        str(output_path),
        enable_transitions=req.enable_transitions,
    )

    return FileResponse(
        str(output_path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=f"{safe_title}.pptx",
    )


def resolve_llm_provider(client_api_key: str = "") -> str | None:
    """Returns 'gemini', 'anthropic', or None if no API key is configured."""
    if client_api_key:
        if client_api_key.startswith("sk-ant"):
            return "anthropic"
        return "gemini"

    explicit = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if explicit in {"gemini", "google"}:
        return "gemini" if google_key else None
    if explicit == "anthropic":
        return "anthropic" if anthropic_key else None
    if explicit:
        return None

    if google_key:
        return "gemini"
    if anthropic_key:
        return "anthropic"
    return None


# Match names from Google AI Studio (see ai.dev/rate-limit). Many accounts have 0 quota on 2.0-* models.
DEFAULT_GEMINI_MODEL = "gemini-3.1-pro"
# Only models that typically have free-tier quota (see ai.dev/rate-limit). 404 → try next.
GEMINI_MODEL_FALLBACKS = (
    "gemini-3.1-pro",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
)
# Common typos / deprecated ids from tutorials.
GEMINI_MODEL_ALIASES = {
    "gemini-3.0-flash": "gemini-3.5-flash",
    "gemini-3-flash": "gemini-3.5-flash",
}


def _llm_model_name(provider: str | None) -> str | None:
    if provider == "gemini":
        return os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    if provider == "anthropic":
        return os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
    return None


def _generation_meta(source: str, provider: str | None = None, error: str | None = None) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "used_llm": source == "llm",
        "llm_configured": provider is not None,
        "provider": provider,
        "model": _llm_model_name(provider),
        "source": source,
    }
    if error:
        meta["error"] = error[:500]
    return meta


def call_ai_with_retry(prompt: str, max_retries: int = 3, client_api_key: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Uses Gemini (Google AI Studio) or Claude if an API key is set.
    Priority: Client key, then LLM_PROVIDER env, else GOOGLE_API_KEY / GEMINI_API_KEY, else ANTHROPIC_API_KEY.
    Without any key, returns fallback deck so the app can still demo end-to-end.
  Returns (deck, generation) where generation describes whether the LLM API was used.
    """
    provider = resolve_llm_provider(client_api_key)
    if not provider:
        return FALLBACK_DECK, _generation_meta("no_api_key")

    if provider == "gemini":
        deck, source, err = _call_gemini_with_retry(prompt, max_retries, client_api_key)
    else:
        deck, source, err = _call_anthropic_with_retry(prompt, max_retries, client_api_key)

    if source == "llm":
        return deck, _generation_meta("llm", provider)
    return deck, _generation_meta("llm_failed", provider, err)


def _normalize_gemini_model(name: str) -> str:
    key = name.strip().lower()
    if key in GEMINI_MODEL_ALIASES:
        mapped = GEMINI_MODEL_ALIASES[key]
        print(f"[INFO] GEMINI_MODEL '{name}' → '{mapped}'")
        return mapped
    return name.strip()


def _gemini_models_to_try() -> list[str]:
    configured = _normalize_gemini_model(os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL)
    models = [configured]
    for name in GEMINI_MODEL_FALLBACKS:
        if name not in models:
            models.append(name)
    return models


def _is_gemini_model_not_found(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "404" in msg or ("not found" in msg and "model" in msg)


def _is_gemini_rate_limited(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "quota" in msg or "rate" in msg


def _parse_and_validate_deck(raw: str) -> dict[str, Any]:
    parsed = parse_llm_json(raw)
    deck = normalize_llm_deck(parsed)
    jsonschema.validate(deck, DECK_SCHEMA)
    return deck


def _json_retry_hint(attempt: int) -> str:
    if attempt <= 0:
        return ""
    return (
        "\n\nIMPORTANT: Your previous reply was not valid JSON. "
        "Return ONE compact JSON object only. "
        "Escape double quotes inside strings. "
        "No markdown fences, no comments, no trailing commas. "
        "Keep speaker_notes under 400 characters each."
    )


def _call_gemini_with_retry(prompt: str, max_retries: int, client_api_key: str = "") -> tuple[dict[str, Any], str, str | None]:
    api_key = client_api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return FALLBACK_DECK, "llm_failed", "Missing GOOGLE_API_KEY"

    try:
        import google.generativeai as genai
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Missing package: google-generativeai. Run: pip install -r requirements.txt",
        )

    genai.configure(api_key=api_key)
    last_error: Exception | None = None
    models_to_try = _gemini_models_to_try()

    for model_name in models_to_try:
        model = genai.GenerativeModel(model_name=model_name, system_instruction=SYSTEM_PROMPT)
        try_next_model = False

        for attempt in range(max_retries):
            try:
                response = model.generate_content(
                    prompt + _json_retry_hint(attempt),
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=8192,
                        temperature=0.3 if attempt else 0.4,
                        response_mime_type="application/json",
                    ),
                )
                raw = (response.text or "").strip()
                if not raw:
                    raise ValueError("Gemini returned empty response")
                if model_name != models_to_try[0]:
                    print(f"[INFO] Gemini used fallback model: {model_name}")
                return _parse_and_validate_deck(raw), "llm", None
            except Exception as e:
                last_error = e
                if _is_gemini_model_not_found(e):
                    print(f"[WARN] Gemini model not available: {model_name}")
                    try_next_model = True
                    break
                if _is_gemini_rate_limited(e):
                    # Do not hop models on 429 — burns RPM/RPD on every model. Retry same model only.
                    if attempt < max_retries - 1:
                        wait_s = 8
                        print(f"[WARN] Gemini rate limit on {model_name}, retry in {wait_s}s...")
                        time.sleep(wait_s)
                        continue
                    print(
                        f"[WARN] Gemini quota/rate limit on {model_name}. "
                        "Wait ~1 minute or check https://ai.dev/rate-limit — do not spam Generate."
                    )
                    break

        if not try_next_model:
            break

    err_msg = str(last_error) if last_error else "Unknown error"
    print(f"[WARN] Gemini generation failed after retries: {last_error}")
    return FALLBACK_DECK, "llm_failed", err_msg


def _call_anthropic_with_retry(prompt: str, max_retries: int, client_api_key: str = "") -> tuple[dict[str, Any], str, str | None]:
    api_key = client_api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return FALLBACK_DECK, "llm_failed", "Missing ANTHROPIC_API_KEY"

    try:
        import anthropic
    except ImportError:
        raise HTTPException(status_code=500, detail="Missing package: anthropic. Run: pip install -r requirements.txt")

    client = anthropic.Anthropic(api_key=api_key)
    last_error = None

    for attempt in range(max_retries):
        try:
            msg = client.messages.create(
                model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt + _json_retry_hint(attempt)}],
            )

            raw = msg.content[0].text.strip()
            return _parse_and_validate_deck(raw), "llm", None
        except Exception as e:
            last_error = e

    err_msg = str(last_error) if last_error else "Unknown error"
    print(f"[WARN] Claude generation failed after retries: {last_error}")
    return FALLBACK_DECK, "llm_failed", err_msg


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
            "subheading": "\n".join(f"• {item[:120]}" for item in chunk[:4]),
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
