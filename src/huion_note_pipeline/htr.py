"""Handwriting transcription through the Gemini REST API."""
from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Optional

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
        raise RuntimeError("Gemini did not return a transcript. Try another page.")
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

def convert_gemini(svg_path: str, title: str = "Note",
                   api_key: Optional[str] = None) -> tuple[str, str]:
    """Returns (raw_text, markdown) using Gemini Vision AI."""
    raw = run_ocr_gemini(svg_path, api_key=api_key)
    return raw, to_markdown(raw, title=title)
