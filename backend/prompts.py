DECK_JSON_SHAPE = """{
  "deck_id": "unique_string",
  "title": "Presentation title",
  "topic": "optional short topic",
  "theme": "professional",
  "slides": [
    {
      "slide_id": 1,
      "layout": "title",
      "content": { "heading": "Main title", "subheading": "Subtitle" },
      "speaker_notes": "What to say aloud",
      "visual_hint": "Short visual note",
      "transition": "fade"
    },
    {
      "slide_id": 2,
      "layout": "bullet",
      "content": {
        "heading": "Section title",
        "bullets": [{ "text": "Point one", "detail": "optional" }]
      },
      "speaker_notes": "...",
      "visual_hint": "...",
      "transition": "push"
    }
  ]
}"""

SYSTEM_PROMPT = f"""You are a professional presentation designer.
Return ONE JSON object only (not an array). No markdown fences, no commentary.

Required top-level keys: deck_id, title, theme, slides.
theme must be one of: professional, minimal, bold, dark (not "slate" or other names).

Each slide must use:
- slide_id (integer, 1-based)
- layout: title | bullet | two_column | image_text | quote | closing
- content.heading (not "title"); content.subheading (not "subtitle")
- two_column: content.left_column and content.right_column (plain text, use bullet lines)
- bullet: content.bullets as array of {{"text": "...", "detail": "optional"}}
- quote: content.quote and content.author
- closing: content.heading, content.subheading, content.cta

Rules:
- First slide: layout = "title"; last slide: layout = "closing"
- Prefer image_text when SOURCE IMAGES exist; set content.image_id exactly from the list
- 3-5 bullets per bullet slide; no markdown bold (**)
- transition: fade | push | wipe
- Summarize source content; do not paste long paragraphs
- Escape " inside string values; avoid raw line breaks inside JSON strings
- Keep each speaker_notes under 400 characters to prevent truncated JSON

Example shape (follow field names exactly):
{DECK_JSON_SHAPE}
"""

USER_PROMPT_TEMPLATE = """Create a {num_slides}-slide presentation on: "{topic}"
Target audience: {audience}
Tone: {tone}

IMPORTANT: Generate all output text in the same language as the topic.

Return ONLY the JSON object matching the schema in the system prompt. No extra text."""

FILE_PROMPT_TEMPLATE = """Create a {num_slides}-slide presentation based on the document content below.
Target audience: {audience}
Tone: {tone}

Requirements:
- Infer a clear deck title from the content.
- Convert the text into a logical presentation structure.
- Keep slides concise; do not paste long paragraphs directly.
- Use speaker_notes to explain what the presenter should say.
- If SOURCE IMAGES are listed, use them in relevant slides by setting content.image_id to one of the listed ids.
- Use layout = "image_text" for slides where the image supports the text.
- Add transition field for every slide: "fade", "push", or "wipe".
- IMPORTANT: Generate all output text (headings, bullets, quotes, speaker_notes, etc.) in the SAME LANGUAGE as the SOURCE TEXT.

SOURCE IMAGES:
{image_summary}

SOURCE TEXT:
{text_content}

Return ONLY the JSON object (deck_id, title, theme, slides). Use slide_id and content.heading — not slide_number or content.title."""
