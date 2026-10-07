"""Device-space ink geometry shared by drawing and exports; no UI dependencies."""
from __future__ import annotations
import base64
import math
import re
from typing import Iterable

PAGE_WIDTH, PAGE_HEIGHT = 28200, 37400
INK = "#25231F"
Sample = tuple[float, float, float]
Background = tuple[str, bytes, int, int]


def validate_color(color: str) -> str:
    """Only opaque hex colours can enter SVG or saved ink metadata."""
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError("Ink colour must be an opaque six-digit hex colour.")
    return color.upper()


def stroke_colors(count: int, colors: Iterable[str] | None = None) -> list[str]:
    try:
        result = [INK] * count if colors is None else [validate_color(c) for c in colors]
    except TypeError as exc:
        raise ValueError("Ink colours must be a list of opaque hex colours.") from exc
    if len(result) != count:
        raise ValueError("Each stroke must have one ink colour.")
    return result


def radius(pressure: float) -> float:
    return 12 + 32 * (min(8192, max(0, pressure)) / 8192) ** 0.65


def fit_image_rect(width: int, height: int) -> tuple[float, float, float, float]:
    """Contain an image on the notebook page without changing its aspect ratio."""
    if width <= 0 or height <= 0:
        raise ValueError("Image dimensions must be positive.")
    scale = min(PAGE_WIDTH / width, PAGE_HEIGHT / height)
    fitted_width, fitted_height = width * scale, height * scale
    return ((PAGE_WIDTH - fitted_width) / 2, (PAGE_HEIGHT - fitted_height) / 2,
            fitted_width, fitted_height)


def outline(samples: Iterable[Sample]) -> list[tuple[float, float]]:
    """Midpoint quadratic curves, local pressure, round caps; preserves raw input."""
    raw = []
    for sample in samples:
        if not all(math.isfinite(v) for v in sample):
            continue
        if raw and sample[:2] == raw[-1][:2]:
            raw[-1] = sample
        else:
            raw.append(sample)
    if not raw:
        return []
    if len(raw) == 1:
        x, y, pressure = raw[0]
        r = radius(pressure)
        return [(x + r * math.cos(i * math.tau / 16), y + r * math.sin(i * math.tau / 16)) for i in range(16)]
    points = [raw[0]]
    start = raw[0]
    for i, control in enumerate(raw):
        end = tuple((a + b) / 2 for a, b in zip(control, raw[i + 1])) if i + 1 < len(raw) else control
        for j in range(1, 5):
            t = j / 4
            pt = tuple((1 - t) ** 2 * a + 2 * (1 - t) * t * b + t * t * c for a, b, c in zip(start, control, end))
            if math.hypot(pt[0] - points[-1][0], pt[1] - points[-1][1]) > 0.001:
                points.append(pt)
        start = end
    left, right, angles = [], [], []
    for i, (x, y, pressure) in enumerate(points):
        prev, nxt = points[max(0, i - 1)], points[min(len(points) - 1, i + 1)]
        angle = math.atan2(nxt[1] - prev[1], nxt[0] - prev[0])
        angles.append(angle)
        r = radius(pressure)
        nx, ny = -math.sin(angle) * r, math.cos(angle) * r
        left.append((x + nx, y + ny))
        right.append((x - nx, y - ny))
    x, y, pressure = points[-1]
    end_cap = [(x + radius(pressure) * math.cos(angles[-1] + math.pi / 2 - j * math.pi / 8),
                y + radius(pressure) * math.sin(angles[-1] + math.pi / 2 - j * math.pi / 8)) for j in range(1, 8)]
    x, y, pressure = points[0]
    start_cap = [(x + radius(pressure) * math.cos(angles[0] - math.pi / 2 - j * math.pi / 8),
                  y + radius(pressure) * math.sin(angles[0] - math.pi / 2 - j * math.pi / 8)) for j in range(1, 8)]
    return left + end_cap + list(reversed(right)) + start_cap


def svg_document(strokes: Iterable[Iterable[Sample]], colors: Iterable[str] | None = None,
                 background: Background | None = None) -> str:
    strokes = list(strokes)
    colors = stroke_colors(len(strokes), colors)
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{PAGE_WIDTH}" height="{PAGE_HEIGHT}" viewBox="0 0 {PAGE_WIDTH} {PAGE_HEIGHT}">',
             f'<rect width="{PAGE_WIDTH}" height="{PAGE_HEIGHT}" fill="white"/>']
    if background:
        mime_type, content, width, height = background
        if mime_type not in {"image/jpeg", "image/png"}:
            raise ValueError("Background must be a JPEG or PNG image.")
        x, y, fitted_width, fitted_height = fit_image_rect(width, height)
        encoded = base64.b64encode(content).decode("ascii")
        lines.append(
            f'<image x="{x:.3f}" y="{y:.3f}" width="{fitted_width:.3f}" height="{fitted_height:.3f}" '
            f'href="data:{mime_type};base64,{encoded}" preserveAspectRatio="none"/>'
        )
    for stroke, color in zip(strokes, colors):
        polygon = outline(stroke)
        if polygon:
            coords = " L ".join(f"{x:.3f},{y:.3f}" for x, y in polygon)
            lines.append(f'<path d="M {coords} Z" fill="{color}" fill-rule="nonzero"/>')
    lines.append("</svg>")
    return "\n".join(lines)
