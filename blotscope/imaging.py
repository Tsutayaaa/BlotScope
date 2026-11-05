"""Image sampling independent of the graphical interface."""
from __future__ import annotations
import math
import statistics
from PIL import Image

def sample_line_intensity(
    image: Image.Image,
    start: tuple[float, float],
    end: tuple[float, float],
    half_width: int = 2,
) -> tuple[list[float], list[tuple[float, float]]]:
    """Sample inverted grayscale intensity along a line, averaging its width."""
    gray = image.convert("L")
    x0, y0 = start
    x1, y1 = end
    length = max(2, int(round(math.hypot(x1 - x0, y1 - y0))) + 1)
    dx = (x1 - x0) / (length - 1)
    dy = (y1 - y0) / (length - 1)
    norm = math.hypot(dx, dy) or 1.0
    px, py = -dy / norm, dx / norm
    values: list[float] = []
    points: list[tuple[float, float]] = []
    width = max(0, int(half_width))
    for i in range(length):
        cx, cy = x0 + i * dx, y0 + i * dy
        samples = []
        for offset in range(-width, width + 1):
            x = min(gray.width - 1, max(0, int(round(cx + offset * px))))
            y = min(gray.height - 1, max(0, int(round(cy + offset * py))))
            samples.append(gray.getpixel((x, y)))
        values.append(255.0 - statistics.fmean(samples))
        points.append((cx, cy))
    return values, points


