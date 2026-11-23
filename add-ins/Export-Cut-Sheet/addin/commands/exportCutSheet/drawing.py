"""Dimensioned part drawings laid out on PDF pages.

Model values are in centimeters, in each body's own frame, with axes lined
up with Fusion's Front view: x runs right, y runs away from the viewer, and z
runs up. The origin is the frame's minimum corner. Paper values are PDF points.
Each part page is a third-angle drawing (top, front, right) plus a shaded home view.
"""
import math
from dataclasses import dataclass, field

from . import shading
from .pdf_writer import PdfDocument, text_width

PT_PER_INCH = 72.0
PT_PER_CM = PT_PER_INCH / 2.54

# Landscape (width, height) in points.
PAGE_SIZES = {
    'Letter': (11.0 * 72, 8.5 * 72),
    'Tabloid': (17.0 * 72, 11.0 * 72),
    'A4': (841.89, 595.28),
    'A3': (1190.55, 841.89),
}

# View name -> (paper u axis, paper v axis, view direction axis) as frame indices.
VIEW_AXES = {
    'top': (0, 1, 2),
    'front': (0, 2, 1),
    'right': (1, 2, 0),
}

# Fusion's internal length unit is the centimeter.
UNIT_FACTORS = {
    'mm': 10.0,
    'cm': 1.0,
    'm': 0.01,
    'in': 1.0 / 2.54,
    'ft': 1.0 / 30.48,
}
IMPERIAL_UNITS = ('in', 'ft')
FRACTION_DENOMINATORS = (2, 4, 8, 16, 32, 64)

REDUCTION_SCALES = (
    1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 12, 15, 16, 20, 24, 25, 30, 40, 48, 50,
    60, 75, 96, 100, 125, 150, 200, 250, 300, 400, 500, 750, 1000,
)
ENLARGEMENT_SCALES = (1, 1.5, 2, 2.5, 3, 4, 5, 10, 20, 50)

BORDER_MARGIN = 0.4 * PT_PER_INCH
TITLE_HEIGHT = 46.0
AREA_PADDING = 14.0
DIM_OFFSET = 20.0
DIM_ROW = 16.0
# Feature (chain) dimensions sit on the left and top; overall dimensions sit one row further out.
LEFT_MARGIN = DIM_OFFSET + DIM_ROW + 18.0
TOP_MARGIN = DIM_OFFSET + DIM_ROW + 18.0
RIGHT_MARGIN = DIM_OFFSET + 18.0
BOTTOM_MARGIN = DIM_OFFSET + 18.0
VIEW_GAP = 44.0
EXTENSION_GAP = 2.0
EXTENSION_OVERSHOOT = 3.0
ARROW_LENGTH = 6.0
ARROW_HALF_WIDTH = 1.8
DIM_TEXT_SIZE = 8.0
OUTLINE_WIDTH = 0.7
THIN_WIDTH = 0.3
CENTER_DASH = (6.0, 2.0, 1.5, 2.0)
LEADER_LENGTH = 18.0
LEADER_SHOULDER = 6.0

LABEL_GAP = 4.0

# Cut sheet table appended after the drawings. Weights match the CSV columns.
TABLE_ROW_HEIGHT = 15.0
TABLE_TEXT_SIZE = 8.0
TABLE_CAPTION_HEIGHT = 28.0
TABLE_BOTTOM_PAD = 10.0
TABLE_CELL_PAD = 4.0
TABLE_HEADER_FILL = 0.82
TABLE_STRIPE_FILL = 0.93
TABLE_WEIGHTS = (2.6, 1.1, 1.1, 1.2, 0.7, 2.8)
TABLE_ALIGNS = ('left', 'right', 'right', 'right', 'center', 'left')
MIN_STATION_GAP_PT = 10.0
MAX_STATIONS = 14
MIN_ANGLE_DEG = 0.5
MIN_ANGLE_LINE_PT = 8.0
MAX_ANGLES_PER_VIEW = 8
FULL_CIRCLE_DEG = 359.0

# Overview sheet: top and home above front and right.
OVERVIEW_VIEWS = ('home', 'top', 'front', 'right')
OVERVIEW_LABELS = {'home': 'HOME', 'top': 'TOP', 'front': 'FRONT', 'right': 'RIGHT'}
OVERVIEW_LINE_WIDTH = 0.45


@dataclass
class ViewData:
    polylines: list = field(default_factory=list)
    # (u, v, radius) for full circular edges seen face-on.
    circles: list = field(default_factory=list)
    # (center u, center v, depth, radius, sweep degrees, mid u, mid v) for arcs seen face-on.
    arcs: list = field(default_factory=list)
    # ((u1, v1), (u2, v2)) for straight edges.
    lines: list = field(default_factory=list)


@dataclass
class PartSheet:
    views: dict
    body_name: str
    component_name: str
    document_name: str
    # Length >= width >= thickness, for the title block.
    size: tuple
    quantity: int = 1
    # Extents along the view frame's x, y, z. Defaults to `size`.
    view_size: tuple = None
    # Shaded home view (shading.SceneView) in this part's drawing frame, or None.
    home: object = None


@dataclass
class OverviewSheet:
    # View name -> shading.SceneView in model centimeters.
    views: dict
    document_name: str
    body_count: int


@dataclass
class ViewBox:
    name: str
    x: float
    y: float
    width: float
    height: float


@dataclass
class Layout:
    scale: float
    scale_label: str
    boxes: dict


@dataclass(frozen=True)
class LengthFormat:
    """Formats centimeter values as decimals, or as fractions for inches and feet."""
    unit: str
    decimals: int = 3
    denominator: int = 0

    @property
    def uses_fractions(self):
        return self.denominator > 0 and self.unit in IMPERIAL_UNITS

    def format(self, value_cm):
        if not self.uses_fractions:
            return format_number(value_cm * UNIT_FACTORS[self.unit], self.decimals)
        inches = value_cm / 2.54
        if self.unit == 'in':
            return format_fraction(inches, self.denominator)
        return format_feet_inches(inches, self.denominator)


def empty_views():
    return {name: ViewData() for name in VIEW_AXES}


def project(point, view):
    u_axis, v_axis, _normal = VIEW_AXES[view]
    return (point[u_axis], point[v_axis])


def view_extent(size, view):
    u_axis, v_axis, _normal = VIEW_AXES[view]
    return size[u_axis], size[v_axis]


def view_basis(direction, up):
    """Paper (right, up) unit vectors for an orthographic camera looking along `direction`."""
    d = _normalize(direction)
    along = _dot(up, d)
    paper_up = _normalize(tuple(up[i] - along * d[i] for i in range(3)))
    return _cross(d, paper_up), paper_up


def home_frame_in_view(front_right, front_up, home_right, home_up):
    """Home camera axes in the front view's drawing frame.

    All four vectors are paper axes in the same model space. Returns paper
    (right, up) for the home view once a part has been squared up to Front,
    so a custom Home stays the same angle relative to Front as on the cover.
    """
    front_depth = _cross(front_up, front_right)

    def into(vector):
        return (
            _dot(vector, front_right),
            _dot(vector, front_depth),
            _dot(vector, front_up),
        )

    return _normalize(into(home_right)), _normalize(into(home_up))


def project_onto(point, basis):
    right, up = basis
    return (_dot(point, right), _dot(point, up))


def default_view_directions(z_up=True):
    """Fusion's standard (view direction, up vector) for each overview view."""
    if z_up:
        return {
            'home': ((-1.0, 1.0, -1.0), (0.0, 0.0, 1.0)),
            'top': ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
            'front': ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            'right': ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        }
    return {
        'home': ((-1.0, -1.0, -1.0), (0.0, 1.0, 0.0)),
        'top': ((0.0, -1.0, 0.0), (0.0, 0.0, -1.0)),
        'front': ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
        'right': ((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    }


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _normalize(vector):
    length = math.sqrt(_dot(vector, vector))
    if length < 1e-12:
        raise ValueError('zero-length vector')
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def format_number(value, decimals):
    text = f'{value:.{decimals}f}'
    if float(text) == 0:
        text = f'{0:.{decimals}f}'
    return text


def format_fraction(value, denominator):
    """`12.4` at 1/16 -> `12 3/8`. Rounds to the nearest 1/denominator."""
    sign = '-' if value < 0 else ''
    steps = int(round(abs(value) * denominator))
    whole, remainder = divmod(steps, denominator)
    if remainder == 0:
        return f'{sign}{whole}'
    divisor = math.gcd(remainder, denominator)
    fraction = f'{remainder // divisor}/{denominator // divisor}'
    return f'{sign}{whole} {fraction}' if whole else f'{sign}{fraction}'


def format_feet_inches(inches, denominator):
    """`40.5` inches at 1/16 -> `3' 4 1/2"`."""
    steps = int(round(abs(inches) * denominator))
    feet, rest = divmod(steps, 12 * denominator)
    inch_text = format_fraction(rest / denominator, denominator)
    sign = '-' if inches < 0 and steps else ''
    if feet == 0:
        return f'{sign}{inch_text}"'
    return f'{sign}{feet}\' {inch_text}"'


def format_angle(degrees):
    text = f'{degrees:.1f}'
    if text.endswith('.0'):
        text = text[:-2]
    return f'{text}\u00b0'


def standard_scale(raw_points_per_cm):
    """Snap a fitted scale down to a standard drawing ratio.

    Returns (points per cm, label). A ratio of 1:N means 1 unit on paper is
    N units on the part.
    """
    if raw_points_per_cm <= 0:
        raise ValueError('scale must be positive')
    reduction = PT_PER_CM / raw_points_per_cm
    if reduction >= 1.0:
        for ratio in REDUCTION_SCALES:
            if ratio >= reduction - 1e-9:
                return PT_PER_CM / ratio, f'1:{_ratio_text(ratio)}'
        ratio = math.ceil(reduction)
        return PT_PER_CM / ratio, f'1:{ratio}'
    enlargement = 1.0 / reduction
    best = 1
    for ratio in ENLARGEMENT_SCALES:
        if ratio <= enlargement + 1e-9:
            best = ratio
    return PT_PER_CM * best, f'{_ratio_text(best)}:1'


def layout_views(size, area, home_extent=None):
    """Fit the third-angle layout (top above front, right beside front) into `area`.

    `area` is (x, y, width, height) in points. `size` is (x, y, z) in centimeters.
    `home_extent` is the home view's (width, height) in centimeters. When it is
    given, Home sits in the top-right cell and the sheet scales to fit it.
    The top view stays level with the top of that cell, so its dimensions sit
    above the home view. Returns a Layout with one box per view.
    """
    length, depth, height = (max(value, 0.0) for value in size)
    home_w = home_h = 0.0
    if home_extent:
        home_w, home_h = (max(value, 0.0) for value in home_extent)
    has_home = home_w > 0.0 and home_h > 0.0
    col_right = max(depth, home_w)
    row_top = max(depth, home_h)
    area_x, area_y, area_w, area_h = area
    fixed_w = LEFT_MARGIN + VIEW_GAP + RIGHT_MARGIN
    fixed_h = BOTTOM_MARGIN + VIEW_GAP + TOP_MARGIN

    model_w = length + col_right
    model_h = height + row_top
    if model_w <= 0 or model_h <= 0:
        raise ValueError('part has no measurable size')

    raw = min((area_w - fixed_w) / model_w, (area_h - fixed_h) / model_h)
    if raw <= 0:
        raise ValueError('page is too small for this drawing')
    scale, label = standard_scale(raw)

    total_w = scale * model_w + fixed_w
    total_h = scale * model_h + fixed_h
    left = area_x + (area_w - total_w) / 2.0
    bottom = area_y + (area_h - total_h) / 2.0

    front = ViewBox('front', left + LEFT_MARGIN, bottom + BOTTOM_MARGIN, scale * length, scale * height)
    top_row_bottom = front.y + front.height + VIEW_GAP
    top = ViewBox(
        'top', front.x, top_row_bottom + scale * (row_top - depth), scale * length, scale * depth
    )
    right = ViewBox('right', front.x + front.width + VIEW_GAP, front.y, scale * depth, scale * height)
    boxes = {'front': front, 'top': top, 'right': right}
    if has_home:
        cell_w, cell_h = scale * col_right, scale * row_top
        box_w, box_h = scale * home_w, scale * home_h
        boxes['home'] = ViewBox(
            'home',
            right.x + (cell_w - box_w) / 2.0,
            top_row_bottom + (cell_h - box_h) / 2.0,
            box_w,
            box_h,
        )
    return Layout(scale, label, boxes)


def layout_overview(extents, area):
    """Fit a 2 x 2 grid: top and home above front and right, all at one scale.

    `extents` maps view name to (width, height) in centimeters. Views in a
    column or row are centered in their cell, so aligned projections line up.
    """
    widths = {name: max(extents.get(name, (0.0, 0.0))[0], 0.0) for name in OVERVIEW_VIEWS}
    heights = {name: max(extents.get(name, (0.0, 0.0))[1], 0.0) for name in OVERVIEW_VIEWS}
    left_col = max(widths['top'], widths['front'])
    right_col = max(widths['home'], widths['right'])
    bottom_row = max(heights['front'], heights['right'])
    top_row = max(heights['top'], heights['home'])
    model_w = left_col + right_col
    model_h = bottom_row + top_row
    if model_w <= 0 or model_h <= 0:
        raise ValueError('model has no measurable size')

    area_x, area_y, area_w, area_h = area
    fixed_w = LEFT_MARGIN + VIEW_GAP + RIGHT_MARGIN
    fixed_h = BOTTOM_MARGIN + VIEW_GAP + TOP_MARGIN
    raw = min((area_w - fixed_w) / model_w, (area_h - fixed_h) / model_h)
    if raw <= 0:
        raise ValueError('page is too small for the overview')
    scale, label = standard_scale(raw)

    total_w = scale * model_w + fixed_w
    total_h = scale * model_h + fixed_h
    x0 = area_x + (area_w - total_w) / 2.0 + LEFT_MARGIN
    y0 = area_y + (area_h - total_h) / 2.0 + BOTTOM_MARGIN
    x1 = x0 + scale * left_col + VIEW_GAP
    y1 = y0 + scale * bottom_row + VIEW_GAP

    def box(name, cell_x, cell_y, cell_w, cell_h):
        width, height = scale * widths[name], scale * heights[name]
        return ViewBox(name, cell_x + (cell_w - width) / 2.0, cell_y + (cell_h - height) / 2.0, width, height)

    boxes = {
        'front': box('front', x0, y0, scale * left_col, scale * bottom_row),
        'right': box('right', x1, y0, scale * right_col, scale * bottom_row),
        'top': box('top', x0, y1, scale * left_col, scale * top_row),
        'home': box('home', x1, y1, scale * right_col, scale * top_row),
    }
    return Layout(scale, label, boxes)


def resolve_arcs(view):
    """Split face-on arcs into full circles and true arcs.

    Fusion often stores a hole as two half arcs. Arcs that share a center,
    radius, and depth and add up to a full turn become a circle. Returns
    (circles, arcs) with arcs as (center u, center v, radius, mid u, mid v),
    one per position across all depths.
    """
    sweeps = {}
    for cu, cv, depth, radius, sweep, _mu, _mv in view.arcs:
        key = (round(cu, 4), round(cv, 4), round(radius, 4), round(depth, 4))
        sweeps[key] = sweeps.get(key, 0.0) + abs(sweep)

    full = {key[:3] for key, total in sweeps.items() if total >= FULL_CIRCLE_DEG}
    circles = list(view.circles)
    added = set()
    for cu, cv, _depth, radius, _sweep, _mu, _mv in view.arcs:
        key = (round(cu, 4), round(cv, 4), round(radius, 4))
        if key in full and key not in added:
            added.add(key)
            circles.append((cu, cv, radius))

    arcs = []
    seen = set()
    for cu, cv, _depth, radius, _sweep, mu, mv in view.arcs:
        key = (round(cu, 4), round(cv, 4), round(radius, 4))
        if key in full:
            continue
        position = key + (round(mu, 4), round(mv, 4))
        if position in seen:
            continue
        seen.add(position)
        arcs.append((cu, cv, radius, mu, mv))
    return circles, arcs


def group_circles(circles, fmt):
    """Merge duplicate circles and group the rest by displayed diameter.

    Returns a list of (diameter text, [(u, v, r), ...]) sorted largest first.
    """
    unique = {}
    for u, v, radius in circles:
        key = (round(u, 4), round(v, 4), round(radius, 4))
        unique.setdefault(key, (u, v, radius))

    groups = {}
    for u, v, radius in unique.values():
        groups.setdefault(fmt.format(radius * 2.0), []).append((u, v, radius))
    return sorted(groups.items(), key=lambda item: -item[1][0][2])


def group_arcs(arcs, fmt):
    """Group arcs by displayed radius. Returns [(radius text, [arc, ...]), ...] largest first."""
    groups = {}
    for arc in arcs:
        groups.setdefault(fmt.format(arc[2]), []).append(arc)
    return sorted(groups.items(), key=lambda item: -item[1][0][2])


def diameter_label(diameter_text, count):
    prefix = f'{count}X ' if count > 1 else ''
    return f'{prefix}\u00d8 {diameter_text}'


def radius_label(radius_text, count):
    prefix = f'{count}X ' if count > 1 else ''
    return f'{prefix}R {radius_text}'


def feature_stations(values, extent, min_gap):
    """Positions along one axis where features start or end, including both ends.

    Values closer than `min_gap` merge into one station so the chain stays readable.
    Returns [] when there is nothing between the two ends.
    """
    tolerance = max(extent * 1e-6, 1e-7)
    inside = sorted(v for v in values if tolerance < v < extent - tolerance)
    stations = [0.0]
    for value in inside:
        if value - stations[-1] >= min_gap:
            stations.append(value)
    if extent - stations[-1] < min_gap and len(stations) > 1:
        stations[-1] = extent
    else:
        stations.append(extent)
    if len(stations) <= 2 or len(stations) > MAX_STATIONS:
        return []
    return stations


def angled_lines(lines, min_length):
    """Straight edges that are neither horizontal nor vertical in the view.

    Returns [(start, end, degrees from the nearest reference, reference)] where
    reference is 'h' or 'v'. Coincident duplicates are removed.
    """
    found = []
    seen = set()
    for start, end in lines:
        du, dv = end[0] - start[0], end[1] - start[1]
        length = math.hypot(du, dv)
        if length < min_length:
            continue
        from_horizontal = math.degrees(math.atan2(abs(dv), abs(du)))
        if from_horizontal < MIN_ANGLE_DEG or from_horizontal > 90.0 - MIN_ANGLE_DEG:
            continue
        a, b = sorted((start, end))
        key = (round(a[0], 4), round(a[1], 4), round(b[0], 4), round(b[1], 4))
        if key in seen:
            continue
        seen.add(key)
        if from_horizontal <= 45.0:
            found.append((a, b, from_horizontal, 'h'))
        else:
            found.append((a, b, 90.0 - from_horizontal, 'v'))
    return found[:MAX_ANGLES_PER_VIEW]


def build_document(parts, fmt, page_name, date_text, overview=None, table=None):
    """One page per part, the model overview first, and the cut sheet table last.

    `table` is `(header, rows)` with the same columns and values as the CSV.
    """
    page_w, page_h = PAGE_SIZES[page_name]
    header, table_rows = _table_contents(table)
    if overview is not None:
        title = overview.document_name
    else:
        title = parts[0].document_name if parts else 'Drawings'
    document = PdfDocument(f'{title} drawings')
    table_pages = _table_page_count(page_h, len(table_rows))
    sheet_count = len(parts) + (1 if overview is not None else 0) + table_pages
    sheet = 1
    if overview is not None:
        draw_overview(document.add_page(page_w, page_h), overview, fmt, date_text, sheet, sheet_count)
        sheet += 1
    for part in parts:
        draw_part(document.add_page(page_w, page_h), part, fmt, date_text, sheet, sheet_count)
        sheet += 1
    if table_pages:
        _draw_table_pages(
            document, header, table_rows, page_w, page_h, title, date_text, sheet, sheet_count
        )
    return document


def _table_contents(table):
    if not table:
        return (), ()
    header, rows = table
    rows = [tuple(row) for row in rows]
    if not rows:
        return (), ()
    return tuple(str(cell) for cell in header), rows


def _table_body_rows(page_h):
    """How many data rows fit under the repeated header on one landscape page."""
    span = page_h - 2 * BORDER_MARGIN - TABLE_CAPTION_HEIGHT - TABLE_BOTTOM_PAD
    slots = int(span // TABLE_ROW_HEIGHT)
    return max(slots - 1, 1)


def _table_page_count(page_h, row_count):
    if row_count <= 0:
        return 0
    return math.ceil(row_count / _table_body_rows(page_h))


def _draw_table_pages(document, header, rows, page_w, page_h, document_name, date_text, sheet, sheet_count):
    body_rows = _table_body_rows(page_h)
    start = 0
    while start < len(rows):
        chunk = rows[start:start + body_rows]
        page = document.add_page(page_w, page_h)
        _draw_table_page(page, header, chunk, start, document_name, date_text, sheet, sheet_count)
        start += body_rows
        sheet += 1


def _draw_table_page(page, header, rows, start, document_name, date_text, sheet, sheet_count):
    x, y, width, height = _content_border(page)
    _draw_table_caption(page, x, y + height, width, document_name, date_text, sheet, sheet_count)

    table_left = x + 8.0
    table_width = width - 16.0
    table_top = y + height - TABLE_CAPTION_HEIGHT
    columns = _table_columns(header, table_width)
    grid_height = (1 + len(rows)) * TABLE_ROW_HEIGHT
    grid_bottom = table_top - grid_height

    page.fill_rect(table_left, table_top - TABLE_ROW_HEIGHT, table_width, TABLE_ROW_HEIGHT, TABLE_HEADER_FILL)
    for local in range(len(rows)):
        if (start + local) % 2 == 1:
            row_bottom = table_top - (local + 2) * TABLE_ROW_HEIGHT
            page.fill_rect(table_left, row_bottom, table_width, TABLE_ROW_HEIGHT, TABLE_STRIPE_FILL)

    _draw_table_row(page, table_left, table_top - TABLE_ROW_HEIGHT, columns, header, bold=True)
    for local, row in enumerate(rows):
        row_bottom = table_top - (local + 2) * TABLE_ROW_HEIGHT
        _draw_table_row(page, table_left, row_bottom, columns, row, bold=False)
    _draw_table_grid(page, table_left, grid_bottom, table_width, grid_height, columns, len(rows))


def _content_border(page):
    x = BORDER_MARGIN
    y = BORDER_MARGIN
    width = page.width - 2 * BORDER_MARGIN
    height = page.height - 2 * BORDER_MARGIN
    page.rect(x, y, width, height, 1.0)
    return x, y, width, height


def _draw_table_caption(page, x, top, width, document_name, date_text, sheet, sheet_count):
    baseline = top - 18.0
    page.text(x + 8.0, baseline, 'CUT SHEET', 11, bold=True)
    sheet_text = f'{sheet} / {sheet_count}'
    page.text(x + width - 8.0, baseline, sheet_text, 9, align='right')
    date_right = x + width - 8.0 - text_width(sheet_text, 9) - 14.0
    page.text(date_right, baseline, date_text, 9, align='right')
    name_left = x + 8.0 + text_width('CUT SHEET', 11, bold=True) + 14.0
    name_width = date_right - text_width(date_text, 9) - 12.0 - name_left
    if name_width > 20.0:
        size, fitted = fit_text(document_name, name_width, 9.0, 7.0)
        page.text(name_left, baseline, fitted, size)


def _table_columns(header, width):
    count = len(header)
    if count == len(TABLE_WEIGHTS):
        weights, aligns = TABLE_WEIGHTS, TABLE_ALIGNS
    else:
        weights, aligns = (1.0,) * count, ('left',) * count
    total = sum(weights) or 1.0
    return [
        (label, width * weight / total, align)
        for label, weight, align in zip(header, weights, aligns)
    ]


def _draw_table_row(page, x, row_bottom, columns, values, bold):
    baseline = row_bottom + (TABLE_ROW_HEIGHT - TABLE_TEXT_SIZE * 0.72) / 2.0
    cursor = x
    for (_label, col_w, align), value in zip(columns, values):
        _cell_text(page, cursor, baseline, col_w, '' if value is None else str(value), bold, align)
        cursor += col_w


def _cell_text(page, x, baseline, width, text, bold, align):
    available = width - 2 * TABLE_CELL_PAD
    if available <= 0:
        return
    size, fitted = fit_text(text, available, TABLE_TEXT_SIZE, TABLE_TEXT_SIZE, bold=bold)
    if align == 'right':
        page.text(x + width - TABLE_CELL_PAD, baseline, fitted, size, bold=bold, align='right')
    elif align == 'center':
        page.text(x + width / 2.0, baseline, fitted, size, bold=bold, align='center')
    else:
        page.text(x + TABLE_CELL_PAD, baseline, fitted, size, bold=bold)


def _draw_table_grid(page, x, y, width, height, columns, data_rows):
    page.rect(x, y, width, height, 0.7)
    cursor = x
    for _label, col_w, _align in columns[:-1]:
        cursor += col_w
        page.line(cursor, y, cursor, y + height, 0.3)
    for index in range(1, data_rows):
        line_y = y + index * TABLE_ROW_HEIGHT
        page.line(x, line_y, x + width, line_y, 0.3)
    header_y = y + data_rows * TABLE_ROW_HEIGHT
    page.line(x, header_y, x + width, header_y, 0.8)


def _page_frame(page):
    """Draw the border. Returns (drawing area, title block rect)."""
    border_x = BORDER_MARGIN
    border_y = BORDER_MARGIN
    border_w = page.width - 2 * BORDER_MARGIN
    border_h = page.height - 2 * BORDER_MARGIN
    page.rect(border_x, border_y, border_w, border_h, 1.0)

    area = (
        border_x + AREA_PADDING,
        border_y + TITLE_HEIGHT + AREA_PADDING,
        border_w - 2 * AREA_PADDING,
        border_h - TITLE_HEIGHT - 2 * AREA_PADDING,
    )
    return area, (border_x, border_y, border_w, TITLE_HEIGHT)


def draw_overview(page, overview, fmt, date_text, sheet, sheet_count):
    """Shaded home, top, front, and right views of the whole model with its overall size."""
    area, title_rect = _page_frame(page)
    bounds = {name: shading.scene_bounds(overview.views.get(name)) for name in OVERVIEW_VIEWS}
    extents = {
        name: (b[2] - b[0], b[3] - b[1]) if b else (0.0, 0.0)
        for name, b in bounds.items()
    }
    layout = layout_overview(extents, area)

    for name in OVERVIEW_VIEWS:
        box = layout.boxes[name]
        if bounds[name]:
            _draw_shaded_view(page, box, overview.views[name], bounds[name], layout.scale)
        page.text(box.x + box.width / 2.0, box.y + box.height + 8.0, OVERVIEW_LABELS[name], 7, bold=True, align='center')

    width, height = extents['front']
    depth = extents['right'][0]
    front, right = layout.boxes['front'], layout.boxes['right']
    if width > 0:
        _linear_dim(page, front.x, front.x + front.width, front.y, front.y - DIM_OFFSET, fmt.format(width), True)
    if height > 0:
        _linear_dim(page, front.y, front.y + front.height, front.x, front.x - DIM_OFFSET, fmt.format(height), False)
    if depth > 0:
        _linear_dim(page, right.x, right.x + right.width, right.y, right.y - DIM_OFFSET, fmt.format(depth), True)

    size_text = ' x '.join(fmt.format(value) for value in (width, depth, height))
    _draw_cells(page, title_rect, (
        ('DRAWING', 'MODEL OVERVIEW', 2.6),
        ('DOCUMENT', overview.document_name, 3.0),
        ('OVERALL (W x D x H)', size_text, 2.8),
        ('BODIES', str(overview.body_count), 0.8),
        ('UNITS', _unit_text(fmt), 0.9),
        ('SCALE', layout.scale_label, 0.9),
        ('DATE', date_text, 1.2),
        ('SHEET', f'{sheet} / {sheet_count}', 0.9),
    ))


def draw_part(page, part, fmt, date_text, sheet, sheet_count):
    area, title_rect = _page_frame(page)
    view_size = part.view_size or part.size
    home_bounds = shading.scene_bounds(part.home)
    home_extent = None
    if home_bounds:
        home_extent = (home_bounds[2] - home_bounds[0], home_bounds[3] - home_bounds[1])
    layout = layout_views(view_size, area, home_extent)
    views = {name: part.views.get(name) or ViewData() for name in VIEW_AXES}

    for name, box in layout.boxes.items():
        if name == 'home':
            continue
        _draw_view(page, box, views[name], layout.scale, fmt)
    if home_bounds and 'home' in layout.boxes:
        _draw_shaded_view(page, layout.boxes['home'], part.home, home_bounds, layout.scale)

    _draw_dimensions(page, layout, views, view_size, fmt)
    _draw_view_labels(page, layout.boxes)
    _draw_title_block(
        page,
        title_rect,
        part,
        fmt,
        layout.scale_label,
        date_text,
        sheet,
        sheet_count,
    )


def _draw_shaded_view(page, box, view, bounds, scale):
    """Shaded faces with visible edges over them, matching the cover page."""
    raster, edges = shading.render(view, bounds, scale)
    page.image(
        box.x, box.y + box.height - raster.height_pt, raster.width_pt, raster.height_pt,
        raster.width, raster.height, raster.pixels, shading.PALETTE,
    )
    for run in edges:
        page.polyline([(box.x + x, box.y + y) for x, y in run], OVERVIEW_LINE_WIDTH)


def _draw_view(page, box, view, scale, fmt):
    def to_paper(u, v):
        return (box.x + u * scale, box.y + v * scale)

    for polyline in view.polylines:
        page.polyline([to_paper(u, v) for u, v in polyline], OUTLINE_WIDTH)

    circles, arcs = resolve_arcs(view)
    circle_groups = group_circles(circles, fmt)
    for _label, members in circle_groups:
        for u, v, radius in members:
            _center_mark(page, to_paper(u, v), radius * scale)

    angles = (45.0, 135.0, 315.0, 225.0)
    for index, (label, members) in enumerate(circle_groups):
        u, v, radius = max(members, key=lambda circle: circle[0] + circle[1])
        angle = angles[index % len(angles)]
        _leader(page, to_paper(u, v), radius * scale, angle, diameter_label(label, len(members)))

    for label, members in group_arcs(arcs, fmt):
        cu, cv, radius, mu, mv = max(members, key=lambda arc: arc[3] + arc[4])
        angle = math.degrees(math.atan2(mv - cv, mu - cu))
        _leader(page, to_paper(cu, cv), radius * scale, angle, radius_label(label, len(members)))

    paper_lines = [(to_paper(*start), to_paper(*end)) for start, end in view.lines]
    for start, end, degrees, reference in angled_lines(paper_lines, MIN_ANGLE_LINE_PT):
        _angle_dimension(page, start, end, degrees, reference)


def _center_mark(page, center, radius):
    if radius < 1.5:
        return
    reach = radius + 4.0
    cx, cy = center
    page.line(cx - reach, cy, cx + reach, cy, THIN_WIDTH, CENTER_DASH)
    page.line(cx, cy - reach, cx, cy + reach, THIN_WIDTH, CENTER_DASH)


def _leader(page, center, radius, angle, label):
    cx, cy = center
    radians = math.radians(angle)
    dx, dy = math.cos(radians), math.sin(radians)
    tip = (cx + dx * radius, cy + dy * radius)
    elbow = (cx + dx * (radius + LEADER_LENGTH), cy + dy * (radius + LEADER_LENGTH))
    direction = 1.0 if dx >= 0 else -1.0
    shoulder = (elbow[0] + direction * LEADER_SHOULDER, elbow[1])

    page.polyline([shoulder, elbow, tip], THIN_WIDTH)
    _arrowhead(page, tip, (tip[0] - elbow[0], tip[1] - elbow[1]))
    align = 'left' if direction > 0 else 'right'
    page.text(shoulder[0] + direction * 2.0, shoulder[1] - DIM_TEXT_SIZE * 0.3, label, DIM_TEXT_SIZE, align=align)


def _angle_dimension(page, start, end, degrees, reference):
    """Arc between the edge and a horizontal or vertical reference at the edge's start."""
    du, dv = end[0] - start[0], end[1] - start[1]
    length = math.hypot(du, dv)
    radius = min(max(length * 0.45, 14.0), 36.0)

    edge_angle = math.atan2(dv, du)
    if reference == 'h':
        ref_angle = 0.0 if du >= 0 else math.pi
    else:
        ref_angle = math.pi / 2.0 if dv >= 0 else -math.pi / 2.0
    sweep = math.atan2(math.sin(edge_angle - ref_angle), math.cos(edge_angle - ref_angle))

    reach = radius + 4.0
    page.line(
        start[0], start[1],
        start[0] + math.cos(ref_angle) * reach, start[1] + math.sin(ref_angle) * reach,
        THIN_WIDTH,
    )

    steps = max(6, int(abs(math.degrees(sweep)) / 3))
    arc = [
        (
            start[0] + math.cos(ref_angle + sweep * i / steps) * radius,
            start[1] + math.sin(ref_angle + sweep * i / steps) * radius,
        )
        for i in range(steps + 1)
    ]
    page.polyline(arc, THIN_WIDTH)

    turn = 1.0 if sweep >= 0 else -1.0
    for angle, sense in ((ref_angle, -turn), (ref_angle + sweep, turn)):
        tip = (start[0] + math.cos(angle) * radius, start[1] + math.sin(angle) * radius)
        tangent = (-math.sin(angle) * sense, math.cos(angle) * sense)
        _arrowhead(page, tip, tangent, length=4.5, half_width=1.4)

    middle = ref_angle + sweep / 2.0
    label_radius = radius + 4.0
    label_x = start[0] + math.cos(middle) * label_radius
    label_y = start[1] + math.sin(middle) * label_radius - DIM_TEXT_SIZE * 0.35
    align = 'left' if math.cos(middle) >= -0.2 else 'right'
    page.text(label_x, label_y, format_angle(degrees), DIM_TEXT_SIZE, align=align)


def _draw_dimensions(page, layout, views, size, fmt):
    boxes = layout.boxes
    scale = layout.scale
    top, front, right = boxes['top'], boxes['front'], boxes['right']
    length_text, width_text, thickness_text = (fmt.format(value) for value in size)
    min_gap = MIN_STATION_GAP_PT / scale

    length_stations = feature_stations(
        _axis_values(views['top'], 0) + _axis_values(views['front'], 0), size[0], min_gap
    )
    width_stations = feature_stations(
        _axis_values(views['top'], 1) + _axis_values(views['right'], 0), size[1], min_gap
    )
    thickness_stations = feature_stations(
        _axis_values(views['front'], 1) + _axis_values(views['right'], 1), size[2], min_gap
    )

    top_edge = top.y + top.height
    _chain(page, length_stations, top.x, scale, fmt, horizontal=True, ref=top_edge, at=top_edge + DIM_OFFSET)
    length_row = DIM_OFFSET + (DIM_ROW if length_stations else 0.0)
    _linear_dim(page, top.x, top.x + top.width, top_edge, top_edge + length_row, length_text, True)

    _chain(page, width_stations, top.y, scale, fmt, horizontal=False, ref=top.x, at=top.x - DIM_OFFSET)
    width_row = DIM_OFFSET + (DIM_ROW if width_stations else 0.0)
    _linear_dim(page, top.y, top.y + top.height, top.x, top.x - width_row, width_text, False)

    _linear_dim(page, front.x, front.x + front.width, front.y, front.y - DIM_OFFSET, length_text, True)
    _chain(page, thickness_stations, front.y, scale, fmt, horizontal=False, ref=front.x, at=front.x - DIM_OFFSET)
    thickness_row = DIM_OFFSET + (DIM_ROW if thickness_stations else 0.0)
    _linear_dim(page, front.y, front.y + front.height, front.x, front.x - thickness_row, thickness_text, False)

    _linear_dim(page, right.x, right.x + right.width, right.y, right.y - DIM_OFFSET, width_text, True)
    right_edge = right.x + right.width
    _linear_dim(page, right.y, right.y + right.height, right_edge, right_edge + DIM_OFFSET, thickness_text, False)


def _axis_values(view, index):
    values = []
    for start, end in view.lines:
        values.append(start[index])
        values.append(end[index])
    circles, _arcs = resolve_arcs(view)
    for circle in circles:
        values.append(circle[index])
    return values


def _chain(page, stations, base, scale, fmt, horizontal, ref, at):
    """Chain of feature dimensions with labels spread so they never overlap."""
    rows = {'outward': [], 'inward': []}
    narrow_count = 0
    for index in range(len(stations) - 1):
        a = base + stations[index] * scale
        b = base + stations[index + 1] * scale
        text = fmt.format(stations[index + 1] - stations[index])
        _linear_dim(page, a, b, ref, at, text, horizontal, draw_text=False)
        width = text_width(text, DIM_TEXT_SIZE)
        fits = (b - a) >= width + 2 * ARROW_LENGTH + 4.0
        row = 'outward'
        if not fits:
            row = 'inward' if narrow_count % 2 else 'outward'
            narrow_count += 1
        rows[row].append(((a + b) / 2.0, width, text))

    sign = 1.0 if at >= ref else -1.0
    for row, labels in rows.items():
        side = sign if row == 'outward' else -sign
        for center, text in spread_labels(labels, LABEL_GAP):
            _dim_text(page, center, at, side, text, horizontal)


def spread_labels(labels, gap):
    """Shift (center, width, text) labels along one axis so neighbours keep `gap` apart.

    Labels keep their order. Returns [(center, text)].
    """
    placed = []
    previous_right = -math.inf
    for center, width, text in sorted(labels, key=lambda label: label[0]):
        left = max(center - width / 2.0, previous_right + gap)
        placed.append((left + width / 2.0, text))
        previous_right = left + width
    return placed


def _dim_text(page, along, at, side, text, horizontal):
    """Text centered at `along`, on `side` (+1 or -1) of a dimension line at `at`."""
    cap = DIM_TEXT_SIZE * 0.72
    if horizontal:
        y = at + 2.0 if side > 0 else at - 2.0 - cap
        page.text(along, y, text, DIM_TEXT_SIZE, align='center')
    else:
        # Rotated text reads bottom to top; its glyphs sit on the -x side of the baseline.
        x = at - 2.0 if side < 0 else at + 2.0 + cap
        page.text(x, along, text, DIM_TEXT_SIZE, align='center', angle=90.0)


def _linear_dim(page, a1, a2, ref, at, text, horizontal, draw_text=True):
    """Dimension from a1 to a2 along one paper axis, drawn at offset `at`.

    `ref` is the geometry edge the extension lines start from. Horizontal
    dimensions run along x; vertical ones run along y with rotated text.
    """
    def point(along, across):
        return (along, across) if horizontal else (across, along)

    sign = 1.0 if at >= ref else -1.0
    for along in (a1, a2):
        x1, y1 = point(along, ref + sign * EXTENSION_GAP)
        x2, y2 = point(along, at + sign * EXTENSION_OVERSHOOT)
        page.line(x1, y1, x2, y2, THIN_WIDTH)

    span = a2 - a1
    start, end = point(a1, at), point(a2, at)
    page.line(start[0], start[1], end[0], end[1], THIN_WIDTH)
    forward = (1.0, 0.0) if horizontal else (0.0, 1.0)
    backward = (-forward[0], -forward[1])
    if span >= 2.5 * ARROW_LENGTH:
        _arrowhead(page, start, backward)
        _arrowhead(page, end, forward)
    else:
        outer_start = point(a1 - 2 * ARROW_LENGTH, at)
        outer_end = point(a2 + 2 * ARROW_LENGTH, at)
        page.line(outer_start[0], outer_start[1], start[0], start[1], THIN_WIDTH)
        page.line(end[0], end[1], outer_end[0], outer_end[1], THIN_WIDTH)
        _arrowhead(page, start, forward)
        _arrowhead(page, end, backward)

    if not draw_text:
        return

    width = text_width(text, DIM_TEXT_SIZE)
    if span >= width + 2 * ARROW_LENGTH + 4.0:
        _dim_text(page, (a1 + a2) / 2.0, at, sign, text, horizontal)
    elif horizontal:
        page.text(a2 + 2 * ARROW_LENGTH + 3.0, at - DIM_TEXT_SIZE * 0.35, text, DIM_TEXT_SIZE, align='left')
    else:
        # Too short for rotated text: write it level, beside the dimension line.
        x = at - 3.0 if sign < 0 else at + 3.0
        align = 'right' if sign < 0 else 'left'
        page.text(x, (a1 + a2) / 2.0 - DIM_TEXT_SIZE * 0.35, text, DIM_TEXT_SIZE, align=align)


def _arrowhead(page, tip, direction, length=ARROW_LENGTH, half_width=ARROW_HALF_WIDTH):
    dx, dy = direction
    norm = math.hypot(dx, dy)
    if norm == 0:
        return
    dx, dy = dx / norm, dy / norm
    base_x = tip[0] - dx * length
    base_y = tip[1] - dy * length
    px, py = -dy * half_width, dx * half_width
    page.polygon([tip, (base_x + px, base_y + py), (base_x - px, base_y - py)])


def _draw_view_labels(page, boxes):
    front, top, right = boxes['front'], boxes['top'], boxes['right']
    page.text(front.x + front.width, front.y + front.height + 6.0, 'FRONT', 7, bold=True, align='right')
    page.text(right.x, right.y + right.height + 6.0, 'RIGHT', 7, bold=True)
    page.text(top.x + top.width, top.y - 12.0, 'TOP', 7, bold=True, align='right')
    home = boxes.get('home')
    if home is not None:
        page.text(home.x + home.width / 2.0, home.y + home.height + 8.0, 'HOME', 7, bold=True, align='center')


def _draw_title_block(page, rect, part, fmt, scale_label, date_text, sheet, sheet_count):
    size_text = ' x '.join(fmt.format(value) for value in part.size)
    _draw_cells(page, rect, (
        ('PART', part.body_name, 3.0),
        ('COMPONENT', part.component_name, 2.2),
        ('DOCUMENT', part.document_name, 2.4),
        ('SIZE (L x W x T)', size_text, 2.8),
        ('QTY', str(part.quantity), 0.6),
        ('UNITS', _unit_text(fmt), 0.9),
        ('SCALE', scale_label, 0.9),
        ('DATE', date_text, 1.2),
        ('SHEET', f'{sheet} / {sheet_count}', 0.9),
    ))


def _unit_text(fmt):
    return f'{fmt.unit} (1/{fmt.denominator})' if fmt.uses_fractions else fmt.unit


def _draw_cells(page, rect, cells):
    """Title block row of (label, value, relative width) cells."""
    x, y, width, height = rect
    page.line(x, y + height, x + width, y + height, 1.0)
    total = sum(weight for _label, _value, weight in cells)
    cursor = x
    for index, (label, value, weight) in enumerate(cells):
        cell_w = width * weight / total
        if index > 0:
            page.line(cursor, y, cursor, y + height, 0.5)
        page.text(cursor + 4.0, y + height - 10.0, label, 6)
        size, fitted = fit_text(value, cell_w - 8.0, 11.0, 6.0, bold=True)
        page.text(cursor + 4.0, y + 10.0, fitted, size, bold=True)
        cursor += cell_w


def fit_text(text, max_width, max_size, min_size, bold=False):
    """Shrink text to fit, then truncate with '...' at the minimum size."""
    text = text or ''
    size = max_size
    while size > min_size and text_width(text, size, bold) > max_width:
        size -= 0.5
    if text_width(text, size, bold) <= max_width:
        return size, text
    trimmed = text
    while trimmed and text_width(trimmed + '...', size, bold) > max_width:
        trimmed = trimmed[:-1]
    return size, (trimmed + '...') if trimmed else ''


def _ratio_text(ratio):
    return str(int(ratio)) if float(ratio).is_integer() else f'{ratio:g}'
