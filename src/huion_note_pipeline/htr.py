"""Handwriting recognition through local TrOCR or explicit Gemini cloud OCR."""
from __future__ import annotations

import base64
import io
import logging
import os
import importlib.util
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

_TROCR_BUNDLE = None
TROCR_MODEL = "microsoft/trocr-small-handwritten"
TROCR_REVISION = "55eb2010aeaaa246defc329d42939e0253d55c99"


def local_handwriting_available() -> bool:
    return all(importlib.util.find_spec(name) for name in ("torch", "transformers", "sentencepiece", "google.protobuf"))


def _get_trocr_bundle():
    global _TROCR_BUNDLE
    if _TROCR_BUNDLE is None:
        try:
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel
            options = {"revision": TROCR_REVISION, "local_files_only": True}
            try:
                proc = TrOCRProcessor.from_pretrained(TROCR_MODEL, use_fast=False, **options)
                model = VisionEncoderDecoderModel.from_pretrained(TROCR_MODEL, **options)
            except OSError:
                proc = TrOCRProcessor.from_pretrained(TROCR_MODEL, revision=TROCR_REVISION, use_fast=False)
                model = VisionEncoderDecoderModel.from_pretrained(TROCR_MODEL, revision=TROCR_REVISION)
            model.eval()
            _TROCR_BUNDLE = (proc, model)
        except Exception as e:
            log.warning(f"TrOCR initialization error: {e}")
            _TROCR_BUNDLE = False
    return _TROCR_BUNDLE if _TROCR_BUNDLE is not False else None


def _line_crops(png_bytes: bytes) -> list:
    """Split a page into text-line images; TrOCR is trained on single lines."""
    from PIL import Image
    image = Image.open(io.BytesIO(png_bytes)).convert("L")
    width, height = image.size
    pixels = image.load()
    active = [sum(pixels[x, y] < 210 for x in range(0, width, 2)) >= 2 for y in range(height)]
    runs = []
    start = None
    for y, marked in enumerate(active + [False]):
        if marked and start is None:
            start = y
        elif not marked and start is not None:
            if runs and start - runs[-1][1] <= max(10, height // 180):
                runs[-1] = (runs[-1][0], y)
            else:
                runs.append((start, y))
            start = None
    crops = []
    for top, bottom in runs:
        top, bottom = max(0, top - 12), min(height, bottom + 12)
        columns = [x for x in range(width) if any(pixels[x, y] < 210 for y in range(top, bottom))]
        if columns and bottom - top >= 6:
            left, right = max(0, columns[0] - 16), min(width, columns[-1] + 17)
            crops.append(image.crop((left, top, right, bottom)).convert("RGB"))
    return crops


def run_ocr_local(svg_path: str) -> str:
    """Recognise a handwritten page locally with line-segmented Microsoft TrOCR."""
    trocr = _get_trocr_bundle()
    if trocr is None:
        raise RuntimeError("Enhanced local handwriting recognition is not installed. Install HuionNote's handwriting extras or choose Google Gemini.")
    import torch
    proc, model = trocr
    lines = _line_crops(rasterise_svg(svg_path))
    if not lines:
        raise RuntimeError("No handwriting was detected on this page.")
    text = []
    try:
        for line in lines:
            values = proc(images=line, return_tensors="pt").pixel_values
            with torch.inference_mode():
                ids = model.generate(values, max_new_tokens=96, num_beams=4)
            result = proc.batch_decode(ids, skip_special_tokens=True)[0].strip()
            if result:
                text.append(result)
    except Exception as exc:
        raise RuntimeError("Local handwriting recognition could not finish. Try again or choose Google Gemini.") from exc
    if not text:
        raise RuntimeError("No readable handwriting was recognised on this page.")
    return "\n".join(text)


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
        raise RuntimeError("Local OCR failed. Check that Tesseract and its English language data are installed.") from e


# ── Gemini Vision path ────────────────────────────────────────────────────────

def run_ocr_gemini(svg_path: str, api_key: Optional[str] = None) -> str:
    """Send the selected page through Gemini's REST API; no extra SDK required."""
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY not set.\n"
            "Export it with:  export GEMINI_API_KEY=your_key_here"
        )
    import requests
    model = os.environ.get("HUION_GEMINI_MODEL", "gemini-3.8-flash")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
        raise ValueError("HUION_GEMINI_MODEL must be a Gemini model ID.")

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
    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": key},
            json={"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/png", "data": b64}}]}]},
            timeout=(10, 120),
        )
    except requests.RequestException as exc:
        raise RuntimeError("Could not reach Gemini. Check your internet connection and try again.") from exc
    if not response.ok:
        raise RuntimeError(f"Gemini returned HTTP {response.status_code}. Check your API key, model access and quota.")
    data = response.json()
    candidates = data.get("candidates", [])
    parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
    text = "\n".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if not text:
        raise RuntimeError("Gemini did not return a transcript. Try local OCR or another page.")
    return text


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
    """Returns (raw_text, markdown) using local line-segmented TrOCR."""
    raw = run_ocr_local(svg_path)
    return raw, to_markdown(raw, title=title)


def convert_tesseract(svg_path: str, title: str = "Note") -> tuple[str, str]:
    """Legacy explicit Tesseract entry point retained for the CLI."""
    raw = run_ocr_tesseract(svg_path)
    return raw, to_markdown(raw, title=title)


def convert_gemini(svg_path: str, title: str = "Note",
                   api_key: Optional[str] = None) -> tuple[str, str]:
    """Returns (raw_text, markdown) using Gemini Vision AI."""
    raw = run_ocr_gemini(svg_path, api_key=api_key)
    return raw, to_markdown(raw, title=title)
