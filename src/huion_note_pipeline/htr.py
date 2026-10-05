"""Handwritten Text Recognition (HTR) module.

Two conversion paths:
  1. run_ocr_tesseract()  — local, free, private. Requires tesseract-ocr + pytesseract.
  2. run_ocr_gemini()     — cloud, higher accuracy for cursive. Requires GEMINI_API_KEY.

Both rasterise the SVG to PNG in-memory via CairoSVG (already installed).
"""
from __future__ import annotations

import base64
import io
import logging
import os
import re
from pathlib import Path
from typing import Optional

log = logging.getLogger("huion.htr")


# ── SVG rasterisation ─────────────────────────────────────────────────────────

def rasterise_svg(
    svg_path: str,
    output_width: int = 1750,
    output_height: int = 2480,
    scale: Optional[float] = None,
) -> bytes:
    """Convert SVG to PNG bytes via CairoSVG at high-resolution 300 DPI A5 dimensions.

    Using explicit output dimensions prevents Cairo memory allocation errors
    (CAIRO_STATUS_INVALID_SIZE) on SVGs containing large raw tablet viewBoxes (e.g. 28200x37400).
    """
    import cairosvg
    raw_text = Path(svg_path).read_text(encoding="utf-8", errors="ignore")
    return cairosvg.svg2png(
        bytestring=raw_text.encode("utf-8"),
        output_width=output_width,
        output_height=output_height,
        background_color="white",
    )


def _enhance_for_ocr(png_bytes: bytes) -> bytes:
    """Sharpen + contrast-boost PNG for better Tesseract accuracy."""
    from PIL import Image, ImageEnhance, ImageFilter
    img = Image.open(io.BytesIO(png_bytes)).convert("L")
    img = img.filter(ImageFilter.SHARPEN)
    img = ImageEnhance.Contrast(img).enhance(2.2)
    img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── Local Deep Learning / Tesseract HTR ──────────────────────────────────────

_EASYOCR_READER = None
_TROCR_BUNDLE = None


def _get_easyocr_reader():
    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        try:
            import easyocr
            _EASYOCR_READER = easyocr.Reader(["en"], gpu=False)
        except Exception as e:
            log.warning(f"EasyOCR initialization error: {e}")
            _EASYOCR_READER = False
    return _EASYOCR_READER if _EASYOCR_READER is not False else None


def _get_trocr_bundle():
    global _TROCR_BUNDLE
    if _TROCR_BUNDLE is None:
        try:
            import torch
            from transformers import AutoImageProcessor, XLMRobertaTokenizer, TrOCRProcessor, VisionEncoderDecoderModel
            img_proc = AutoImageProcessor.from_pretrained("microsoft/trocr-small-handwritten")
            tok = XLMRobertaTokenizer.from_pretrained("microsoft/trocr-small-handwritten")
            proc = TrOCRProcessor(image_processor=img_proc, tokenizer=tok)
            model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-small-handwritten")
            model.eval()
            _TROCR_BUNDLE = (proc, tok, model)
        except Exception as e:
            log.warning(f"TrOCR initialization error: {e}")
            _TROCR_BUNDLE = False
    return _TROCR_BUNDLE if _TROCR_BUNDLE is not False else None


def run_ocr_local(svg_path: str) -> str:
    """High-accuracy offline handwriting recognition using deep learning models.

    1. Tries EasyOCR for robust handwriting & multi-line block localization.
    2. Falls back to TrOCR Transformer / Tesseract 5 LSTM if needed.
    """
    png_bytes = rasterise_svg(svg_path)

    # 1. Try EasyOCR
    reader = _get_easyocr_reader()
    if reader is not None:
        try:
            results = reader.readtext(png_bytes, detail=0, paragraph=True)
            text = "\n\n".join([r.strip() for r in results if r.strip()])
            if text:
                return text
        except Exception as e:
            log.warning(f"EasyOCR error: {e}")

    # 2. Try TrOCR
    trocr = _get_trocr_bundle()
    if trocr is not None:
        try:
            import torch
            from PIL import Image, ImageOps
            proc, tok, model = trocr
            img = Image.open(io.BytesIO(png_bytes)).convert("L")
            inv = ImageOps.invert(img)
            bbox = inv.getbbox()
            if bbox:
                w, h = img.size
                x0, y0, x1, y1 = bbox
                crop = img.crop((max(0, x0-20), max(0, y0-20), min(w, x1+20), min(h, y1+20))).convert("RGB")
                pixel_values = proc(crop, return_tensors="pt").pixel_values
                with torch.no_grad():
                    generated_ids = model.generate(pixel_values, max_new_tokens=128)
                txt = tok.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
                if txt:
                    return txt
        except Exception as e:
            log.warning(f"TrOCR error: {e}")

    # 3. Fallback: Tesseract 5
    return run_ocr_tesseract(svg_path)


def run_ocr_tesseract(svg_path: str) -> str:
    """Rasterise SVG and run Tesseract 5 LSTM OCR. Returns raw text string."""
    import pytesseract
    from PIL import Image

    png = rasterise_svg(svg_path)
    img = Image.open(io.BytesIO(_enhance_for_ocr(png)))
    cfg = "--oem 1 --psm 6"
    try:
        return pytesseract.image_to_string(img, config=cfg, lang="eng").strip()
    except Exception as e:
        log.warning(f"Tesseract error: {e}")
        return ""


# ── Gemini Vision path ────────────────────────────────────────────────────────

def run_ocr_gemini(svg_path: str, api_key: Optional[str] = None) -> str:
    """Send PNG to Gemini 1.5 Flash for HTR. Returns raw text string."""
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY not set.\n"
            "Export it with:  export GEMINI_API_KEY=your_key_here"
        )
    try:
        import google.generativeai as genai
    except ImportError:
        raise RuntimeError("pip install google-generativeai")

    genai.configure(api_key=key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    b64 = base64.b64encode(rasterise_svg(svg_path)).decode()
    prompt = (
        "This is a handwritten note scanned from a digital pen tablet. "
        "Transcribe ALL handwritten text exactly as written, preserving:\n"
        "- Headings (larger/underlined text)\n"
        "- Bullet points or numbered lists\n"
        "- Paragraph breaks\n"
        "- Diagrams: describe briefly in [square brackets]\n\n"
        "Output ONLY the transcribed text. "
        "Mark illegible sections as [illegible]. "
        "No commentary, no preamble."
    )
    resp = model.generate_content([{"mime_type": "image/png", "data": b64}, prompt])
    return resp.text.strip()


# ── Markdown post-processor ───────────────────────────────────────────────────

def to_markdown(raw: str, title: str = "Note") -> str:
    """Convert raw OCR text to structured Markdown."""
    if not raw:
        return f"# {title}\n\n*No readable text found.*\n"

    lines = raw.splitlines()
    out: list[str] = [f"# {title}\n"]
    prev_heading = False

    for line in lines:
        s = line.strip()
        if not s:
            out.append("")
            prev_heading = False
            continue

        words = s.split()

        # ALL-CAPS line >= 2 words → heading
        if s.isupper() and len(words) >= 2 and len(s) >= 3:
            out.append(f"## {s.title()}")
            prev_heading = True
            continue

        # Bullet point
        if s[0] in ("-", "*", "•", "·", "\u2022"):
            out.append(f"- {s.lstrip('-*•· ').strip()}")
            prev_heading = False
            continue

        # Numbered list
        if re.match(r"^\d+[\.\)]\s", s):
            out.append(s)
            prev_heading = False
            continue

        # Short line after heading → sub-heading
        if prev_heading and len(words) < 6 and not s.endswith("."):
            out.append(f"### {s}")
            prev_heading = False
            continue

        out.append(s)
        prev_heading = False

    # Collapse excess blank lines
    result: list[str] = []
    blanks = 0
    for ln in out:
        if ln == "":
            blanks += 1
            if blanks <= 1:
                result.append("")
        else:
            blanks = 0
            result.append(ln)

    return "\n".join(result).strip() + "\n"


# ── Public entry points ───────────────────────────────────────────────────────

def convert_local(svg_path: str, title: str = "Note") -> tuple[str, str]:
    """Returns (raw_text, markdown) using local neural HTR (EasyOCR / TrOCR / Tesseract)."""
    raw = run_ocr_local(svg_path)
    return raw, to_markdown(raw, title=title)


def convert_tesseract(svg_path: str, title: str = "Note") -> tuple[str, str]:
    """Backward compatibility alias for convert_local."""
    return convert_local(svg_path, title=title)


def convert_gemini(svg_path: str, title: str = "Note",
                   api_key: Optional[str] = None) -> tuple[str, str]:
    """Returns (raw_text, markdown) using Gemini Vision AI."""
    raw = run_ocr_gemini(svg_path, api_key=api_key)
    return raw, to_markdown(raw, title=title)
