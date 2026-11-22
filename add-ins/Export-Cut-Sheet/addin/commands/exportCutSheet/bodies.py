import math
from dataclasses import dataclass, field

import adsk.core
import adsk.fusion

from . import drawing

UNIT_FACTORS = drawing.UNIT_FACTORS
UNIT_CHOICES = tuple(UNIT_FACTORS)

PARALLEL_TOLERANCE = 1e-4
VOLUME_TOLERANCE = 1e-4


@dataclass
class Candidate:
    name: str
    component_name: str
    body: object


@dataclass
class BodyInfo:
    name: str
    component_name: str
    body: object
    origin: tuple
    axes: tuple
    size: tuple
    is_rectangle: bool
    token: str = field(default='')


def collect(design, selected=None):
    """Return the solid bodies to export.

    With `selected`, only those bodies are used. Otherwise every visible solid
    body in the root component and in every occurrence is returned, once per
    occurrence, so repeated components appear as many times as they are placed.
    """
    root = design.rootComponent
    found = []

    if selected is not None:
        seen = set()
        for entity in selected:
            body = adsk.fusion.BRepBody.cast(entity)
            if not body or not body.isSolid:
                continue
            key = _token(body) or id(body)
            if key in seen:
                continue
            seen.add(key)
            native = body.nativeObject or body
            found.append(Candidate(body.name, _component_name(native, root), native))
        return found

    for body in root.bRepBodies:
        if body.isSolid and body.isVisible:
            found.append(Candidate(body.name, root.name, body))

    for occurrence in root.allOccurrences:
        if not _occurrence_visible(occurrence):
            continue
        component = occurrence.component
        for body in component.bRepBodies:
            if not body.isSolid:
                continue
            proxy = body.createForAssemblyContext(occurrence)
            if proxy and proxy.isVisible:
                found.append(Candidate(body.name, component.name, body))
    return found


def measure(candidate):
    body = candidate.body
    center, axes, extents = _bounding_frame(body)
    center, axes, extents = sort_frame(center, axes, extents)
    origin = tuple(
        center[i] - sum(axes[k][i] * extents[k] / 2.0 for k in range(3)) for i in range(3)
    )
    return BodyInfo(
        name=candidate.name,
        component_name=candidate.component_name,
        body=body,
        origin=origin,
        axes=axes,
        size=extents,
        is_rectangle=_is_rectangular_body(body, extents),
        token=_token(body),
    )


def group_identical(infos):
    """Merge repeated instances of the same body so the PDF draws each part once."""
    groups = {}
    order = []
    for info in infos:
        key = identity_key(info)
        if key not in groups:
            groups[key] = [info, 0]
            order.append(key)
        groups[key][1] += 1
    return [(groups[key][0], groups[key][1]) for key in order]


def identity_key(info):
    """Same key for every placed instance of one body."""
    return (
        info.token or f'{info.component_name}/{info.name}',
        info.name,
        tuple(round(value, 4) for value in info.size),
    )


def extract_views(info):
    """Project every edge of the body into the top, front, and right views."""
    views = drawing.empty_views()
    tolerance = max(max(info.size) * 0.001, 0.0005)

    for edge in info.body.edges:
        points = [to_local(point, info.origin, info.axes) for point in _edge_points(edge, tolerance)]
        if len(points) >= 2:
            for name, view in views.items():
                projected = [drawing.project(point, name) for point in points]
                if _span(projected) > 1e-6:
                    view.polylines.append(projected)

        geometry = edge.geometry
        line = adsk.core.Line3D.cast(geometry)
        if line:
            start = to_local(_xyz(line.startPoint), info.origin, info.axes)
            end = to_local(_xyz(line.endPoint), info.origin, info.axes)
            for name, view in views.items():
                segment = (drawing.project(start, name), drawing.project(end, name))
                if _span(segment) > 1e-6:
                    view.lines.append(segment)
            continue

        circle = adsk.core.Circle3D.cast(geometry)
        if circle:
            center = to_local(_xyz(circle.center), info.origin, info.axes)
            normal = local_direction(_xyz(circle.normal), info.axes)
            for name, view in _face_on_views(views, normal):
                u, v = drawing.project(center, name)
                view.circles.append((u, v, circle.radius))
            continue

        arc = adsk.core.Arc3D.cast(geometry)
        if arc and len(points) >= 2:
            center = to_local(_xyz(arc.center), info.origin, info.axes)
            normal = local_direction(_xyz(arc.normal), info.axes)
            sweep = abs(math.degrees(arc.endAngle - arc.startAngle))
            middle = points[len(points) // 2]
            for name, view in _face_on_views(views, normal):
                u, v = drawing.project(center, name)
                mu, mv = drawing.project(middle, name)
                depth = center[drawing.VIEW_AXES[name][2]]
                view.arcs.append((u, v, depth, arc.radius, sweep, mu, mv))
    return views


def _face_on_views(views, normal):
    for name, view in views.items():
        axis = drawing.VIEW_AXES[name][2]
        if abs(normal[axis]) >= 1.0 - PARALLEL_TOLERANCE:
            yield name, view


def sort_frame(center, axes, extents):
    """Order axes so extents run length >= width >= thickness, right-handed."""
    pairs = sorted(zip(extents, axes), key=lambda pair: -pair[0])
    x_axis = normalize(pairs[0][1])
    y_axis = normalize(pairs[1][1])
    z_axis = normalize(cross(x_axis, y_axis))
    return tuple(center), (x_axis, y_axis, z_axis), tuple(pair[0] for pair in pairs)


def normals_form_box(normals, tolerance=PARALLEL_TOLERANCE):
    """True when six face normals pair up into three mutually perpendicular directions."""
    if len(normals) != 6:
        return False
    unit = [normalize(n) for n in normals]
    groups = []
    for normal in unit:
        for group in groups:
            if abs(abs(dot(group[0], normal)) - 1.0) <= tolerance:
                group.append(normal)
                break
        else:
            groups.append([normal])
    if len(groups) != 3 or any(len(group) != 2 for group in groups):
        return False
    for i in range(3):
        for j in range(i + 1, 3):
            if abs(dot(groups[i][0], groups[j][0])) > tolerance:
                return False
    return True


def volume_matches_box(volume, extents, tolerance=VOLUME_TOLERANCE):
    box_volume = extents[0] * extents[1] * extents[2]
    if box_volume <= 0:
        return False
    return abs(volume - box_volume) / box_volume < tolerance


def to_local(point, origin, axes):
    delta = (point[0] - origin[0], point[1] - origin[1], point[2] - origin[2])
    return (dot(delta, axes[0]), dot(delta, axes[1]), dot(delta, axes[2]))


def local_direction(vector, axes):
    return (dot(vector, axes[0]), dot(vector, axes[1]), dot(vector, axes[2]))


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def normalize(vector):
    length = math.sqrt(dot(vector, vector))
    if length == 0:
        raise ValueError('zero-length vector')
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def _bounding_frame(body):
    try:
        box = body.orientedMinimumBoundingBox
    except Exception:
        box = None
    if box is not None:
        return _from_oriented_box(box)

    length_dir, width_dir = _planar_frame(body)
    try:
        box = adsk.core.Application.get().measureManager.getOrientedBoundingBox(
            body, _vector(length_dir), _vector(width_dir)
        )
        if box:
            return _from_oriented_box(box)
    except Exception:
        pass
    return _stroke_frame(body, length_dir, width_dir)


def _from_oriented_box(box):
    axes = (_xyz(box.lengthDirection), _xyz(box.widthDirection), _xyz(box.heightDirection))
    axes = tuple(normalize(axis) for axis in axes)
    return _xyz(box.centerPoint), axes, (box.length, box.width, box.height)


def _planar_frame(body):
    """Frame from the largest planar face's normal and that face's longest straight edge."""
    largest = None
    for face in body.faces:
        plane = adsk.core.Plane.cast(face.geometry)
        if plane and (largest is None or face.area > largest[0].area):
            largest = (face, plane)
    if largest is None:
        return (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)

    face, plane = largest
    normal = normalize(_xyz(plane.normal))
    longest = None
    for edge in face.edges:
        line = adsk.core.Line3D.cast(edge.geometry)
        if not line:
            continue
        start, end = _xyz(line.startPoint), _xyz(line.endPoint)
        direction = (end[0] - start[0], end[1] - start[1], end[2] - start[2])
        span = math.sqrt(dot(direction, direction))
        if span > 0 and (longest is None or span > longest[0]):
            longest = (span, direction)

    if longest is None:
        seed = (1.0, 0.0, 0.0) if abs(normal[0]) < 0.9 else (0.0, 1.0, 0.0)
        length_dir = normalize(cross(cross(normal, seed), normal))
    else:
        direction = longest[1]
        along = dot(direction, normal)
        length_dir = normalize(tuple(direction[i] - along * normal[i] for i in range(3)))
    width_dir = normalize(cross(normal, length_dir))
    return length_dir, width_dir


def _stroke_frame(body, length_dir, width_dir):
    axes = (length_dir, width_dir, normalize(cross(length_dir, width_dir)))
    tolerance = 0.001
    lows = [math.inf] * 3
    highs = [-math.inf] * 3
    for edge in body.edges:
        for point in _edge_points(edge, tolerance):
            for k in range(3):
                value = dot(point, axes[k])
                lows[k] = min(lows[k], value)
                highs[k] = max(highs[k], value)
    if lows[0] == math.inf:
        raise ValueError('body has no edges to measure')
    extents = tuple(highs[k] - lows[k] for k in range(3))
    mids = [(highs[k] + lows[k]) / 2.0 for k in range(3)]
    center = tuple(sum(axes[k][i] * mids[k] for k in range(3)) for i in range(3))
    return center, axes, extents


def _is_rectangular_body(body, extents):
    faces = body.faces
    if faces.count != 6:
        return False
    normals = []
    for face in faces:
        plane = adsk.core.Plane.cast(face.geometry)
        if not plane:
            return False
        normals.append(_xyz(plane.normal))
    if not normals_form_box(normals):
        return False
    return volume_matches_box(body.volume, extents)


def _edge_points(edge, tolerance):
    evaluator = edge.evaluator
    ok, start, end = evaluator.getParameterExtents()
    if not ok:
        return []
    ok, points = evaluator.getStrokes(start, end, tolerance)
    if not ok:
        return []
    return [_xyz(point) for point in points]


def _span(points):
    us = [p[0] for p in points]
    vs = [p[1] for p in points]
    return max(max(us) - min(us), max(vs) - min(vs))


def _occurrence_visible(occurrence):
    try:
        return occurrence.isVisible
    except Exception:
        return True


def _component_name(body, root):
    try:
        return body.parentComponent.name
    except Exception:
        return root.name


def _token(body):
    try:
        return body.entityToken
    except Exception:
        return ''


def _xyz(value):
    return (value.x, value.y, value.z)


def _vector(direction):
    return adsk.core.Vector3D.create(direction[0], direction[1], direction[2])
