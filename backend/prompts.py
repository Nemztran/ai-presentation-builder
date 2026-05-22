SYSTEM_PROMPT = """You are a professional presentation designer.
Generate a structured presentation deck as valid JSON only.
No markdown, no explanation — pure JSON matching this schema.

Rules:
- First slide: layout = "title"
- Last slide: layout = "closing"
- Middle slides: mix of "bullet", "two_column", "image_text", "quote"
- Prefer "image_text" slides when source images are available
- If using a source image, set content.image_id to an image_id from SOURCE IMAGES exactly
- Bullets: 3-5 items per slide, concise and punchy
- speaker_notes: natural spoken language, 2-3 sentences
- visual_hint: one short image description for the designer
- transition: use "fade", "push", or "wipe"
- theme: choose best fit for the source content
- Do not copy the full source text verbatim; summarize, group, and structure it into a presentation
"""

USER_PROMPT_TEMPLATE = """Create a {num_slides}-slide presentation on: "{topic}"
Target audience: {audience}
Tone: {tone}

Return ONLY valid JSON. No extra text."""

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

SOURCE IMAGES:
{image_summary}

SOURCE TEXT:
{text_content}

Return ONLY valid JSON. No extra text."""
