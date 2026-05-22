from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN, MSO_AUTO_SIZE
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt


THEMES = {
    "professional": {
        "bg": RGBColor(0xFF, 0xFF, 0xFF),
        "title": RGBColor(0x1A, 0x1A, 0x2E),
        "accent": RGBColor(0x16, 0x21, 0x3E),
        "muted": RGBColor(0xF3, 0xF4, 0xF6),
    },
    "dark": {
        "bg": RGBColor(0x1A, 0x1A, 0x2E),
        "title": RGBColor(0xFF, 0xFF, 0xFF),
        "accent": RGBColor(0x90, 0xCA, 0xF9),
        "muted": RGBColor(0x26, 0x2A, 0x44),
    },
    "bold": {
        "bg": RGBColor(0xF0, 0xF4, 0xFF),
        "title": RGBColor(0x2D, 0x00, 0xF8),
        "accent": RGBColor(0x6A, 0x0D, 0xFF),
        "muted": RGBColor(0xE0, 0xE7, 0xFF),
    },
    "minimal": {
        "bg": RGBColor(0xFA, 0xFA, 0xFA),
        "title": RGBColor(0x2C, 0x2C, 0x2C),
        "accent": RGBColor(0x88, 0x88, 0x88),
        "muted": RGBColor(0xF1, 0xF1, 0xF1),
    },
}


def build_pptx(deck: dict[str, Any], output_path: str, enable_transitions: bool = True):
    prs = Presentation()
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)

    theme = THEMES.get(deck.get("theme", "professional"), THEMES["professional"])
    blank = prs.slide_layouts[6]

    for slide_index, slide_data in enumerate(deck.get("slides", [])):
        slide = prs.slides.add_slide(blank)
        _set_bg(slide, theme["bg"])

        layout = slide_data.get("layout", "bullet")
        content = slide_data.get("content", {})
        image_path = _resolve_slide_image_path(deck, slide_data)

        if layout == "title":
            if image_path:
                _add_image_cover(slide, image_path, 0, 0, 13.33, 7.5)
                _add_overlay(slide, 0, 0, 13.33, 7.5, RGBColor(0x00, 0x00, 0x00), transparency=45)
                title_color = RGBColor(0xFF, 0xFF, 0xFF)
                accent_color = RGBColor(0xEA, 0xEE, 0xFF)
            else:
                title_color = theme["title"]
                accent_color = theme["accent"]
            _add_text(slide, content.get("heading", ""), 1.0, 2.1, 11.3, 1.3, Pt(44), True, title_color, PP_ALIGN.CENTER)
            _add_text(slide, content.get("subheading", ""), 1.0, 3.75, 11.3, 0.8, Pt(24), False, accent_color, PP_ALIGN.CENTER)

        elif layout == "bullet":
            _add_title(slide, content, theme)
            _add_accent_bar(slide, theme)
            bullets = content.get("bullets", [])
            for i, b in enumerate(bullets[:6]):
                line = b.get("text", "")
                detail = b.get("detail")
                if detail:
                    line = f"{line} — {detail}"
                _add_text(slide, f"• {line}", 0.9, 1.55 + i * 0.78, 11.5, 0.65, Pt(19), False, theme["title"])
            if image_path:
                _add_image_box(slide, image_path, 8.55, 4.95, 3.85, 1.85)

        elif layout == "two_column":
            _add_title(slide, content, theme)
            _add_column_card(slide, 0.65, 1.55, 5.85, 5.25, theme)
            _add_column_card(slide, 6.85, 1.55, 5.85, 5.25, theme)
            _add_text(slide, content.get("left_column", ""), 0.9, 1.85, 5.35, 4.75, Pt(17), False, theme["title"])
            _add_text(slide, content.get("right_column", ""), 7.1, 1.85, 5.35, 4.75, Pt(17), False, theme["title"])

        elif layout == "image_text":
            _add_title(slide, content, theme)
            body = content.get("subheading") or content.get("left_column") or _bullets_to_text(content.get("bullets", []))
            _add_text(slide, body, 0.75, 1.55, 5.75, 5.35, Pt(18), False, theme["title"])
            if image_path:
                _add_image_box(slide, image_path, 7.05, 1.55, 5.55, 5.35)
            else:
                _add_placeholder(slide, slide_data.get("visual_hint", "Image from DOCX"), 7.05, 1.55, 5.55, 5.35, theme)

        elif layout == "quote":
            image_path = image_path or _first_deck_image_path(deck)
            if image_path:
                _add_image_cover(slide, image_path, 0, 0, 13.33, 7.5)
                _add_overlay(slide, 0, 0, 13.33, 7.5, RGBColor(0x00, 0x00, 0x00), transparency=50)
                quote_color = RGBColor(0xFF, 0xFF, 0xFF)
                author_color = RGBColor(0xEA, 0xEE, 0xFF)
            else:
                quote_color = theme["accent"]
                author_color = theme["title"]
            quote = content.get("quote", "")
            author = content.get("author", "")
            _add_text(slide, f"“{quote}”", 1.15, 2.0, 11.05, 2.2, Pt(30), True, quote_color, PP_ALIGN.CENTER)
            _add_text(slide, f"— {author}" if author else "", 1.15, 4.6, 11.05, 0.6, Pt(18), False, author_color, PP_ALIGN.CENTER)

        elif layout == "closing":
            _add_text(slide, content.get("heading", ""), 1.0, 2.0, 11.3, 1.1, Pt(40), True, theme["title"], PP_ALIGN.CENTER)
            _add_text(slide, content.get("subheading", ""), 1.0, 3.25, 11.3, 0.7, Pt(22), False, theme["title"], PP_ALIGN.CENTER)
            _add_text(slide, content.get("cta", ""), 1.0, 4.35, 11.3, 0.7, Pt(22), True, theme["accent"], PP_ALIGN.CENTER)

        else:
            _add_title(slide, content, theme)
            _add_text(slide, "Unsupported layout", 0.8, 1.6, 11.5, 0.8, Pt(20), False, theme["title"])

        if slide_data.get("speaker_notes"):
            notes_tf = slide.notes_slide.notes_text_frame
            notes_tf.text = slide_data["speaker_notes"]

        if enable_transitions:
            # PowerPoint will show these as slide-transition effects.
            effect = slide_data.get("transition") or ("fade" if slide_index % 2 == 0 else "push")
            _add_slide_transition(slide, effect=effect, speed="med")

    prs.save(output_path)


def _resolve_slide_image_path(deck: dict[str, Any], slide_data: dict[str, Any]) -> str | None:
    content = slide_data.get("content", {})
    direct = content.get("image_path") or slide_data.get("image_path")
    if direct and Path(str(direct)).exists():
        return str(direct)
    image_id = content.get("image_id") or slide_data.get("image_id")
    assets = deck.get("assets", {}) or {}
    if image_id and image_id in assets:
        path = assets[image_id].get("path")
        if path and Path(path).exists():
            return path
    return None


def _first_deck_image_path(deck: dict[str, Any]) -> str | None:
    for meta in (deck.get("assets", {}) or {}).values():
        path = meta.get("path")
        if path and Path(path).exists():
            return path
    return None


def _add_title(slide, content, theme):
    _add_text(slide, content.get("heading", ""), 0.65, 0.42, 12.0, 0.85, Pt(31), True, theme["title"])


def _add_text(slide, text, left, top, width, height, size, bold, color, align=PP_ALIGN.LEFT):
    tx_box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tx_box.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    tf.clear()

    for idx, line in enumerate(str(text or "").splitlines() or [""]):
        p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        p.alignment = align
        run = p.add_run()
        run.text = line
        run.font.size = size
        run.font.bold = bold
        run.font.color.rgb = color


def _add_placeholder(slide, text, left, top, width, height, theme):
    shape = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
    shape.fill.solid()
    shape.fill.fore_color.rgb = theme["accent"]
    shape.line.color.rgb = theme["accent"]
    tf = shape.text_frame
    tf.text = text
    tf.paragraphs[0].alignment = PP_ALIGN.CENTER
    tf.paragraphs[0].runs[0].font.size = Pt(18)
    tf.paragraphs[0].runs[0].font.bold = True
    tf.paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)


def _add_image_box(slide, image_path: str, left, top, width, height):
    box = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
    box.fill.solid()
    box.fill.fore_color.rgb = RGBColor(0xF3, 0xF4, 0xF6)
    box.line.color.rgb = RGBColor(0xE5, 0xE7, 0xEB)
    slide.shapes.add_picture(image_path, Inches(left + 0.12), Inches(top + 0.12), width=Inches(width - 0.24), height=Inches(height - 0.24))


def _add_image_cover(slide, image_path: str, left, top, width, height):
    slide.shapes.add_picture(image_path, Inches(left), Inches(top), width=Inches(width), height=Inches(height))


def _add_overlay(slide, left, top, width, height, color, transparency=40):
    shape = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.fill.transparency = transparency
    shape.line.fill.background()


def _add_accent_bar(slide, theme):
    shape = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, Inches(0), Inches(0), Inches(0.16), Inches(7.5))
    shape.fill.solid()
    shape.fill.fore_color.rgb = theme["accent"]
    shape.line.fill.background()


def _add_column_card(slide, left, top, width, height, theme):
    shape = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
    shape.fill.solid()
    shape.fill.fore_color.rgb = theme["muted"]
    shape.line.color.rgb = theme["muted"]


def _bullets_to_text(bullets):
    if not bullets:
        return ""
    return "\n".join(f"• {b.get('text', '')}" for b in bullets[:5])


def _set_bg(slide, color):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def _add_slide_transition(slide, effect: str = "fade", speed: str = "med"):
    # Remove existing transition nodes to keep the XML clean.
    sld = slide._element
    for child in list(sld):
        if child.tag.endswith("}transition"):
            sld.remove(child)

    transition = OxmlElement("p:transition")
    transition.set("spd", speed)

    if effect == "push":
        child = OxmlElement("p:push")
        child.set("dir", "l")
    elif effect == "wipe":
        child = OxmlElement("p:wipe")
        child.set("dir", "l")
    else:
        child = OxmlElement("p:fade")

    transition.append(child)

    # Put transition after cSld/clrMapOvr and before timing/extLst when present.
    insert_at = 1
    for idx, child in enumerate(list(sld)):
        if child.tag.endswith("}clrMapOvr"):
            insert_at = idx + 1
    sld.insert(insert_at, transition)
