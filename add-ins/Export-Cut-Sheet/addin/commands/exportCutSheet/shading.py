"""Shaded, hidden-line-removed rendering for the overview and part home views.

Faces are filled into a depth-buffered raster with flat lighting. Edges are
checked against that depth buffer and only their visible stretches are kept,
so they can be drawn as crisp vector lines over the image.

View coordinates are (u, v, depth) in centimeters: u runs right, v runs up,
and depth grows away from the viewer.
"""
import math
from dataclasses import dataclass, field

DPI = 200.0
MAX_PIXELS = 1_500_000
BACKGROUND = 255
AMBIENT = 0.4
EDGE_SAMPLE_PX = 1.0
# Hidden edges leave stubs about this long where they meet a silhouette.
MIN_RUN_PX = 3.0
SIMPLIFY_PX = 0.05
# Palette ramp for indices 1..254, dark to light. Index 255 is the white background.
SHADE_DARK = (72, 80, 92)
SHADE_LIGHT = (228, 233, 240)


@dataclass
class SceneView:
    # ((u, v, depth), (u, v, depth), (u, v, depth)) per mesh triangle.
    triangles: list = field(default_factory=list)
    # Polylines of (u, v, depth) along each model edge.
    edges: list = field(default_factory=list)

    def is_empty(self):
        return not self.triangles and not self.edges


@dataclass
class Raster:
    width: int
    height: int
    # One palette index per pixel, rows top to bottom.
    pixels: bytearray
    width_pt: float
    height_pt: float


def _build_palette():
    entries = [SHADE_DARK]
    for index in range(1, 255):
        t = (index - 1) / 253.0
        entries.append(tuple(round(d + (l - d) * t) for d, l in zip(SHADE_DARK, SHADE_LIGHT)))
    entries.append((255, 255, 255))
    return bytes(channel for entry in entries for channel in entry)


PALETTE = _build_palette()


def view_frame(right, up):
    """(right, up, depth) unit axes; depth points away from the viewer."""
    depth = (
        up[1] * right[2] - up[2] * right[1],
        up[2] * right[0] - up[0] * right[2],
        up[0] * right[1] - up[1] * right[0],
    )
    return right, up, depth


def project(point, frame):
    right, up, depth = frame
    return (_dot(point, right), _dot(point, up), _dot(point, depth))


def scene_bounds(view):
    """(min u, min v, max u, max v) over triangles and edges, or None when empty."""
    if view is None or view.is_empty():
        return None
    points = [p for triangle in view.triangles for p in triangle]
    points.extend(p for polyline in view.edges for p in polyline)
    us = [p[0] for p in points]
    vs = [p[1] for p in points]
    return min(us), min(vs), max(us), max(vs)


def render(view, bounds, scale, dpi=DPI, max_pixels=MAX_PIXELS):
    """Shade `view` over `bounds` at `scale` points per centimeter.

    Returns (Raster, visible edge runs). Runs are polylines of (x, y) points
    measured from the bottom-left corner of `bounds` on paper; the raster's
    top edge lines up with the top of `bounds`.
    """
    umin, vmin, umax, vmax = bounds
    width_pt = max((umax - umin) * scale, 0.0)
    height_pt = max((vmax - vmin) * scale, 0.0)
    px_per_pt = dpi / 72.0
    area = width_pt * height_pt
    if area > 0 and area * px_per_pt * px_per_pt > max_pixels:
        px_per_pt = math.sqrt(max_pixels / area)
    width = max(1, int(math.ceil(width_pt * px_per_pt)))
    height = max(1, int(math.ceil(height_pt * px_per_pt)))
    px_per_cm = scale * px_per_pt

    def to_pixels(point):
        return ((point[0] - umin) * px_per_cm, (vmax - point[1]) * px_per_cm, point[2])

    zbuf = [math.inf] * (width * height)
    pixels = bytearray([BACKGROUND]) * (width * height)
    for triangle in view.triangles:
        shade = _shade(triangle)
        if shade is not None:
            _fill(tuple(to_pixels(p) for p in triangle), shade, zbuf, pixels, width, height)

    diagonal = math.hypot(umax - umin, vmax - vmin)
    bias = diagonal * 0.003 + 2.5 / px_per_cm
    runs = []
    for polyline in view.edges:
        for run in _visible_runs([to_pixels(p) for p in polyline], zbuf, width, height, bias):
            runs.append([(x / px_per_pt, height_pt - y / px_per_pt) for x, y in run])

    raster = Raster(width, height, pixels, width / px_per_pt, height / px_per_pt)
    return raster, runs


def _shade(triangle):
    """Palette index from flat two-sided lighting, or None for a degenerate triangle."""
    p0, p1, p2 = triangle
    a = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    b = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
    normal = (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )
    length = math.sqrt(_dot(normal, normal))
    if length < 1e-12:
        return None
    facing = abs(_dot(normal, _LIGHT)) / length
    intensity = AMBIENT + (1.0 - AMBIENT) * facing
    return 1 + int(round(min(intensity, 1.0) * 253))


def _fill(triangle, shade, zbuf, pixels, width, height):
    (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = triangle
    area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
    if abs(area) < 1e-9:
        return
    # Depth plane z = a * x + b * y + c across the triangle.
    a = ((z1 - z0) * (y2 - y0) - (z2 - z0) * (y1 - y0)) / area
    b = ((x1 - x0) * (z2 - z0) - (x2 - x0) * (z1 - z0)) / area
    c = z0 - a * x0 - b * y0

    sides = ((x0, y0, x1, y1), (x1, y1, x2, y2), (x2, y2, x0, y0))
    row_start = max(0, int(math.ceil(min(y0, y1, y2) - 0.5)))
    row_end = min(height - 1, int(math.floor(max(y0, y1, y2) - 0.5)))
    for row in range(row_start, row_end + 1):
        yc = row + 0.5
        crossings = [
            xa + (yc - ya) * (xb - xa) / (yb - ya)
            for xa, ya, xb, yb in sides
            if (ya <= yc < yb) or (yb <= yc < ya)
        ]
        if len(crossings) < 2:
            continue
        col_start = max(0, int(math.ceil(min(crossings) - 0.5)))
        col_end = min(width - 1, int(math.floor(max(crossings) - 0.5)))
        if col_end < col_start:
            continue
        z = a * (col_start + 0.5) + b * yc + c
        index = row * width + col_start
        for _col in range(col_start, col_end + 1):
            if z < zbuf[index]:
                zbuf[index] = z
                pixels[index] = shade
            z += a
            index += 1


def _visible_runs(points, zbuf, width, height, bias):
    """Split a pixel-space polyline into the stretches no face covers."""
    samples = []
    for (x0, y0, z0), (x1, y1, z1) in zip(points, points[1:]):
        steps = max(1, int(math.ceil(math.hypot(x1 - x0, y1 - y0) / EDGE_SAMPLE_PX)))
        start = 1 if samples else 0
        for step in range(start, steps + 1):
            t = step / steps
            samples.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, z0 + (z1 - z0) * t))

    runs = []
    current = []
    for sample in samples + [None]:
        if sample is not None and _visible(*sample, zbuf, width, height, bias):
            current.append(sample[:2])
            continue
        if len(current) >= 2 and _length(current) >= MIN_RUN_PX:
            runs.append(_simplify(current))
        current = []
    return runs


def _length(points):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))


def _visible(x, y, z, zbuf, width, height, bias):
    col = min(max(int(x), 0), width - 1)
    row = min(max(int(y), 0), height - 1)
    nearest_face = zbuf[row * width + col]
    for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        c, r = col + dc, row + dr
        if 0 <= c < width and 0 <= r < height:
            nearest_face = max(nearest_face, zbuf[r * width + c])
    return z <= nearest_face + bias


def _simplify(points):
    """Drop points that sit on the straight line between their neighbours."""
    kept = [points[0]]
    for index in range(1, len(points) - 1):
        ax, ay = kept[-1]
        bx, by = points[index]
        cx, cy = points[index + 1]
        span = math.hypot(cx - ax, cy - ay)
        if span == 0 or abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / span > SIMPLIFY_PX:
            kept.append(points[index])
    kept.append(points[-1])
    return kept


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _unit(vector):
    length = math.sqrt(_dot(vector, vector))
    return (vector[0] / length, vector[1] / length, vector[2] / length)


# Light from the viewer's upper left.
_LIGHT = _unit((-0.35, 0.55, -1.0))
