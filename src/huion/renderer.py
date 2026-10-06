import json
from pathlib import Path
from typing import List

from .ink import PAGE_WIDTH, PAGE_HEIGHT, svg_document
from .models import Stroke, ExportArtifacts


class MultiFormatRenderer:
    """Exports the same pressure-sensitive geometry displayed by the desktop."""
    PAGE_WIDTH = PAGE_WIDTH
    PAGE_HEIGHT = PAGE_HEIGHT

    @staticmethod
    def svg(strokes: List[Stroke]) -> str:
        return svg_document([[(p.x, p.y, p.pressure) for p in s.points] for s in strokes])

    def render_svg(self, strokes: List[Stroke], target_path: str) -> bool:
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        Path(target_path).write_text(self.svg(strokes), encoding="utf-8")
        return True

    def render_json(self, strokes: List[Stroke], target_path: str) -> bool:
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        data = {
            "page_width": self.PAGE_WIDTH, "page_height": self.PAGE_HEIGHT,
            "max_pressure": 8192, "stroke_count": len(strokes),
            "strokes": [{"pen_type": s.pen_type.value, "points": [
                {"x": p.x, "y": p.y, "pressure": p.pressure, "tilt_x": p.tilt_x, "tilt_y": p.tilt_y}
                for p in s.points]} for s in strokes],
        }
        Path(target_path).write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True

    def render_png(self, strokes: List[Stroke], target_path: str, scale: float = 0.1) -> bool:
        import cairosvg
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        cairosvg.svg2png(bytestring=self.svg(strokes).encode(), write_to=target_path,
                       output_width=max(1, int(self.PAGE_WIDTH * scale)),
                       output_height=max(1, int(self.PAGE_HEIGHT * scale)))
        return True

    def export_all(self, strokes: List[Stroke], folder_path: str, base_name: str, png_only: bool = False) -> ExportArtifacts:
        folder = Path(folder_path)
        png_file = f"{base_name}.png"
        self.render_png(strokes, str(folder / png_file))
        if png_only:
            return ExportArtifacts(folder_path=folder_path, png_filename=png_file)
        svg_file, json_file = f"{base_name}.svg", f"{base_name}.json"
        self.render_svg(strokes, str(folder / svg_file))
        self.render_json(strokes, str(folder / json_file))
        return ExportArtifacts(folder_path=folder_path, svg_filename=svg_file,
                               png_filename=png_file, json_filename=json_file)
