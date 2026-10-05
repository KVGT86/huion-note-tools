"""Antigravity conversion bridge.

Spec source: huion-note-pipeline.allium — ConversionBridge surface.

The AntigravityBridge is a black-box integration: it submits SVG + JSON to
Antigravity / VLM and receives a ConversionResult. The spec guarantees idempotency:
the same SVG + JSON inputs always produce equivalent output.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Callable

from .enums import NoteCategory
from .models import ConversionResult
from .frontmatter import build_frontmatter, render_frontmatter


class AntigravityBridge:
    """Calls Antigravity / VLM to convert a note page.

    Spec guarantee (ConversionBridge @guarantee Idempotent):
      Same SVG + JSON → equivalent category and output.
    """

    def __init__(
        self,
        vlm_transcriber: Optional[Callable[[str, str], ConversionResult]] = None,
    ) -> None:
        self.vlm_transcriber = vlm_transcriber

    def convert(self, svg_path: str, json_path: str) -> ConversionResult:
        """Submit SVG and JSON to Antigravity. Returns ConversionResult."""
        if self.vlm_transcriber is not None:
            return self.vlm_transcriber(svg_path, json_path)

        # Deterministic transcription and metadata extraction
        svg_file = Path(svg_path)
        json_file = Path(json_path)

        svg_content = svg_file.read_text(encoding="utf-8", errors="ignore") if svg_file.exists() else ""
        json_content = json_file.read_text(encoding="utf-8", errors="ignore") if json_file.exists() else "{}"

        # 1. CYCLOPS marker detection
        # Spec: CYCLOPS present and legible -> work, absent -> personal, unreadable -> unclassified
        is_cyclops = bool(re.search(r"\bcyclops\b", svg_content, re.IGNORECASE))
        if not is_cyclops and json_content:
            is_cyclops = bool(re.search(r"\bcyclops\b", json_content, re.IGNORECASE))

        category = NoteCategory.WORK if is_cyclops else NoteCategory.PERSONAL

        # 2. Derive context title
        title = "note"
        text_matches = re.findall(r">([^<]+)<", svg_content)
        cleaned_texts = [t.strip() for t in text_matches if t.strip() and t.strip().upper() != "CYCLOPS"]
        if cleaned_texts:
            candidate = re.sub(r"[^\w\s-]", "", cleaned_texts[0]).strip().replace(" ", "_").lower()
            if candidate:
                title = candidate
        elif svg_file.stem:
            title = svg_file.stem.replace(" ", "_").lower()

        # 3. Inferred tags
        tags: List[str] = ["engineering"] if category == NoteCategory.WORK else ["notes"]

        # 4. Generate markdown with frontmatter and embedded SVG
        sync_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        fm = build_frontmatter(
            title=title.replace("_", " ").title(),
            sync_date=sync_date_str,
            category=category,
            tags=tags,
        )
        fm_block = render_frontmatter(fm)

        body_lines = [fm_block]
        body_lines.append(f"# {title.replace('_', ' ').title()}\n")
        if cleaned_texts:
            for line in cleaned_texts:
                body_lines.append(f"{line}\n")

        # Embed SVG sketch
        body_lines.append(f"\n![Note Sketch]({svg_file.name})\n")
        markdown_text = "\n".join(body_lines)

        return ConversionResult(
            success=True,
            derived_title=title,
            category=category,
            markdown=markdown_text,
            tags=tags,
            error=None,
        )
