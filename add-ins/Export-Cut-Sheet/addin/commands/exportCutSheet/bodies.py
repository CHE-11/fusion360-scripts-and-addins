import itertools
import math
from dataclasses import dataclass, field

import adsk.core
import adsk.fusion

from . import drawing
from . import shading

UNIT_FACTORS = drawing.UNIT_FACTORS
UNIT_CHOICES = tuple(UNIT_FACTORS)

PARALLEL_TOLERANCE = 1e-4
VOLUME_TOLERANCE = 1e-4


@dataclass
class Candidate:
    name: str
    component_name: str
    body: object
    # Matrix3D placing the native body in the root, or None when it already is.
    transform: object = None


@dataclass
class BodyInfo:
    name: str
    component_name: str
    body: object
    # Drawing frame: minimum corner and (right, depth, up) axes as Fusion's Front view shows them.
    origin: tuple
    axes: tuple
    # Length >= width >= thickness.
    size: tuple
    is_rectangle: bool
    token: str = field(default='')
    # Extents along the drawing frame axes.
    view_size: tuple = None


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
            found.append(Candidate(body.name, _component_name(native, root), native, _context_transform(body)))
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
                found.append(Candidate(body.name, component.name, body, occurrence.transform2))
    return found


def extract_overview(design, candidates):
    """Project every candidate's mesh and edges, in root space, into the home, top, front, and right views.

    Returns {view name: shading.SceneView}, oriented like Fusion's ViewCube.
    """
    frames = {name: shading.view_frame(*basis) for name, basis in _overview_bases(design).items()}
    views = {name: shading.SceneView() for name in frames}
    for candidate in candidates:
        matrix = _matrix_values(candidate.transform)

        def place(points):
            return [transform_point(matrix, point) for point in points] if matrix else points

        tolerance = _stroke_tolerance(candidate.body)
        for edge in candidate.body.edges:
            points = _edge_points(edge, tolerance)
            if len(points) < 2:
                continue
            points = place(points)
            for name, frame in frames.items():
                projected = [shading.project(point, frame) for point in points]
                if _span(projected) > 1e-6:
                    views[name].edges.append(projected)

        for triangle in _body_triangles(candidate.body):
            triangle = place(triangle)
            for name, frame in frames.items():
                views[name].triangles.append(tuple(shading.project(point, frame) for point in triangle))
    return views


def _body_triangles(body):
    try:
        calculator = body.meshManager.createMeshCalculator()
        calculator.setQuality(adsk.fusion.TriangleMeshQualityOptions.NormalQualityTriangleMesh)
        mesh = calculator.calculate()
        coords = mesh.nodeCoordinatesAsDouble
        indices = mesh.nodeIndices
    except Exception:
        return []
    nodes = [(coords[i], coords[i + 1], coords[i + 2]) for i in range(0, len(coords) - 2, 3)]
    return [
        (nodes[indices[i]], nodes[indices[i + 1]], nodes[indices[i + 2]])
        for i in range(0, len(indices) - 2, 3)
    ]


def transform_point(matrix, point):
    """Apply a row-major 4 x 4 matrix (Fusion's Matrix3D.asArray order) to a point."""
    x, y, z = point
    m = matrix
    return (
        m[0] * x + m[1] * y + m[2] * z + m[3],
        m[4] * x + m[5] * y + m[6] * z + m[7],
        m[8] * x + m[9] * y + m[10] * z + m[11],
    )


_NAMED_VIEWS = {
    'home': 'homeNamedView',
    'top': 'topNamedView',
    'front': 'frontNamedView',
    'right': 'rightNamedView',
}


def _overview_bases(design):
    """Use the design's named view cameras, so custom Front or Home views are respected."""
    defaults = drawing.default_view_directions(_is_z_up())
    cameras = _named_view_cameras(design)
    bases = {}
    for name in drawing.OVERVIEW_VIEWS:
        if name in cameras:
            try:
                bases[name] = drawing.view_basis(*cameras[name])
                continue
            except ValueError:
                pass
        bases[name] = drawing.view_basis(*defaults[name])
    return bases


def _named_view_cameras(design):
    found = {}
    try:
        named_views = design.namedViews
    except Exception:
        return found
    for name, attribute in _NAMED_VIEWS.items():
        try:
            camera = getattr(named_views, attribute).camera
            eye, target = _xyz(camera.eye), _xyz(camera.target)
            direction = (target[0] - eye[0], target[1] - eye[1], target[2] - eye[2])
            found[name] = (direction, _xyz(camera.upVector))
        except Exception:
            continue
    return found


def _is_z_up():
    try:
        preferences = adsk.core.Application.get().preferences.generalPreferences
        return preferences.defaultModelingOrientation != adsk.core.DefaultModelingOrientations.YUpModelingOrientation
    except Exception:
        return True


def _context_transform(body):
    try:
        context = body.assemblyContext
    except Exception:
        return None
    return context.transform2 if context else None


def _matrix_values(transform):
    if transform is None:
        return None
    try:
        return tuple(transform.asArray())
    except Exception:
        return None


def _stroke_tolerance(body):
    try:
        box = body.boundingBox
        low, high = _xyz(box.minPoint), _xyz(box.maxPoint)
        diagonal = math.sqrt(sum((high[i] - low[i]) ** 2 for i in range(3)))
        return max(diagonal * 0.002, 0.001)
    except Exception:
        return 0.01


def measure(candidate, view_frame=None):
    """Measure a body. `view_frame` is the root-space (right, depth, up) of Fusion's Front view."""
    body = candidate.body
    center, box_axes, box_extents = _bounding_frame(body)
    _center, sorted_axes, sorted_extents = sort_frame(center, box_axes, box_extents)
    if view_frame is None:
        axes, extents = sorted_axes, sorted_extents
    else:
        target = _to_body_space(view_frame, _matrix_values(candidate.transform))
        axes, extents = align_frame(box_axes, box_extents, target)
    origin = tuple(
        center[i] - sum(axes[k][i] * extents[k] / 2.0 for k in range(3)) for i in range(3)
    )
    return BodyInfo(
        name=candidate.name,
        component_name=candidate.component_name,
        body=body,
        origin=origin,
        axes=axes,
        size=sorted_extents,
        is_rectangle=_is_rectangular_body(body, sorted_extents),
        token=_token(body),
        view_size=extents,
    )


def view_frame(design):
    """Root-space (right, depth, up) unit axes of the design's Front view."""
    right, up = _overview_bases(design)['front']
    return right, cross(up, right), up


def align_frame(axes, extents, target):
    """Reorder and flip box axes to follow `target` (right, depth, up) as closely as possible.

    Returns right-handed (axes, extents) so a part is drawn the way Fusion shows
    it, squared up to the nearest view when it sits at an angle.
    """
    axes = [normalize(axis) for axis in axes]
    best_score, best = -1.0, (0, 1, 2)
    for order in itertools.permutations(range(3)):
        score = sum(abs(dot(axes[order[k]], target[k])) for k in range(3))
        if score > best_score + 1e-9:
            best_score, best = score, order
    right = axes[best[0]]
    if dot(right, target[0]) < 0:
        right = _negate(right)
    up = axes[best[2]]
    if dot(up, target[2]) < 0:
        up = _negate(up)
    depth = cross(up, right)
    return (right, depth, up), (extents[best[0]], extents[best[1]], extents[best[2]])


def _to_body_space(frame, matrix):
    """Rotate root-space directions into the native body's component space."""
    if not matrix:
        return frame
    m = matrix
    return tuple(
        normalize((
            m[0] * v[0] + m[4] * v[1] + m[8] * v[2],
            m[1] * v[0] + m[5] * v[1] + m[9] * v[2],
            m[2] * v[0] + m[6] * v[1] + m[10] * v[2],
        ))
        for v in frame
    )


def _negate(vector):
    return (-vector[0], -vector[1], -vector[2])


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


def part_home_frame(design):
    """Home-view (right, up, depth) axes in a part's front-aligned drawing frame.

    Uses the design's ViewCube, including a custom Home or Front view.
    """
    bases = _overview_bases(design)
    front_right, front_up = bases['front']
    home_right, home_up = bases['home']
    right, up = drawing.home_frame_in_view(front_right, front_up, home_right, home_up)
    return shading.view_frame(right, up)


def extract_home_view(info, frame=None):
    """Project one body's mesh and edges into the shaded home view.

    Points are in the part's drawing frame, the same frame as `extract_views`.
    `frame` is a shading view frame; the standard Home view is used when it is omitted.
    """
    if frame is None:
        right, up = drawing.view_basis(*drawing.default_view_directions(True)['home'])
        frame = shading.view_frame(right, up)
    scene = shading.SceneView()
    extents = info.view_size or info.size
    tolerance = max(max(extents) * 0.001, 0.0005) if extents else 0.0005

    for edge in info.body.edges:
        points = [to_local(point, info.origin, info.axes) for point in _edge_points(edge, tolerance)]
        if len(points) < 2:
            continue
        projected = [shading.project(point, frame) for point in points]
        if _span(projected) > 1e-6:
            scene.edges.append(projected)

    for triangle in _body_triangles(info.body):
        local = tuple(to_local(point, info.origin, info.axes) for point in triangle)
        scene.triangles.append(tuple(shading.project(point, frame) for point in local))
    return scene


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
