import json
import os
from typing import List
from .models import Stroke, PenPoint, ExportArtifacts

try:
    from PIL import Image, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class MultiFormatRenderer:
    """Implements MultiFormatRenderer contract from huion-note.allium"""

    PAGE_WIDTH = 28200
    PAGE_HEIGHT = 37400

    def render_svg(self, strokes: List[Stroke], target_path: str) -> bool:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        svg_header = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {self.PAGE_WIDTH} {self.PAGE_HEIGHT}" '
            f'width="100%" height="100%" style="background-color: #ffffff;">\n'
        )
        svg_body = []
        for stroke in strokes:
            if not stroke.points:
                continue
            path_d = []
            for i, pt in enumerate(stroke.points):
                cmd = "M" if i == 0 else "L"
                path_d.append(f"{cmd} {pt.x} {pt.y}")
            # Stroke width proportional to average pressure
            avg_pressure = sum(p.pressure for p in stroke.points) / len(stroke.points)
            stroke_width = max(10, int(avg_pressure / 100))
            svg_body.append(
                f'  <path d="{" ".join(path_d)}" fill="none" stroke="#000000" '
                f'stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round" />\n'
            )
        svg_footer = '</svg>\n'
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(svg_header + "".join(svg_body) + svg_footer)
        return True

    def render_json(self, strokes: List[Stroke], target_path: str) -> bool:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        data = {
            "page_width": self.PAGE_WIDTH,
            "page_height": self.PAGE_HEIGHT,
            "max_pressure": 8192,
            "stroke_count": len(strokes),
            "strokes": [
                {
                    "pen_type": s.pen_type.value,
                    "points": [
                        {
                            "x": pt.x,
                            "y": pt.y,
                            "pressure": pt.pressure,
                            "tilt_x": pt.tilt_x,
                            "tilt_y": pt.tilt_y,
                        }
                        for pt in s.points
                    ]
                }
                for s in strokes
            ]
        }
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True

    def render_png(self, strokes: List[Stroke], target_path: str, scale: float = 0.1) -> bool:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        if PIL_AVAILABLE:
            width = max(1, int(self.PAGE_WIDTH * scale))
            height = max(1, int(self.PAGE_HEIGHT * scale))
            img = Image.new("RGB", (width, height), "white")
            draw = ImageDraw.Draw(img)

            for stroke in strokes:
                if not stroke.points or len(stroke.points) < 2:
                    continue
                coords = [(pt.x * scale, pt.y * scale) for pt in stroke.points]
                avg_pressure = sum(p.pressure for p in stroke.points) / len(stroke.points)
                stroke_w = max(1, int(avg_pressure / 8192.0 * 5))
                draw.line(coords, fill=(0, 0, 0), width=stroke_w, joint="curve")

            img.save(target_path, "PNG")
            return True

        # Fallback minimal PNG placeholder if PIL is omitted
        with open(target_path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")
        return True

    def export_all(
        self,
        strokes: List[Stroke],
        folder_path: str,
        base_name: str,
        png_only: bool = False
    ) -> ExportArtifacts:
        png_file = f"{base_name}.png"
        png_path = os.path.join(folder_path, png_file)
        self.render_png(strokes, png_path)

        if png_only:
            return ExportArtifacts(
                folder_path=folder_path,
                svg_filename=None,
                png_filename=png_file,
                json_filename=None,
            )

        svg_file = f"{base_name}.svg"
        json_file = f"{base_name}.json"
        svg_path = os.path.join(folder_path, svg_file)
        json_path = os.path.join(folder_path, json_file)

        self.render_svg(strokes, svg_path)
        self.render_json(strokes, json_path)

        return ExportArtifacts(
            folder_path=folder_path,
            svg_filename=svg_file,
            png_filename=png_file,
            json_filename=json_file
        )
