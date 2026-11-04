"""Build thread sweeps and heat-set pockets in the active design.

Fusion's Python API on current installs can read a coil feature but cannot
create one, and the coil primitive only offers a circle, square, or triangle.
Printable trapezoids and truncated ISO/UNC profiles are swept along a helix
that lies on the selected cylinder, with that face as the guide so the tooth
does not roll. Fit numbers live in user parameters. Changing them rebuilds
this sweep, which is what the palette nudge does after a test print.
"""

from __future__ import annotations

import math

import adsk.core
import adsk.fusion

from . import profile as thread_profile

ATTR_GROUP = 'CHE_Threader'
NAME_ROOT = 'Threader'

_app = adsk.core.Application.get()
_ui = _app.userInterface

# Clicking the palette clears Fusion's active selection. Keep the last
# cylinder and insert targets so Create still has what the palette is showing.
_held_cylinder = None
_held_insert_targets = []


class GeometryError(ValueError):
    """A modeling step failed in a way the palette can show."""


def _design():
    design = adsk.fusion.Design.cast(_app.activeProduct)
    if not design:
        raise GeometryError('Open a Fusion design first.')
    return design


def _native(entity):
    native = getattr(entity, 'nativeObject', None)
    return native if native else entity


def _mm_to_cm(value_mm):
    return float(value_mm) / 10.0


def _vec(x, y, z):
    return adsk.core.Vector3D.create(x, y, z)


def _point(x, y, z):
    return adsk.core.Point3D.create(x, y, z)


def _sub(a, b):
    return _vec(a.x - b.x, a.y - b.y, a.z - b.z)


def _add_point(origin, *parts):
    x, y, z = origin.x, origin.y, origin.z
    for vector, scale in parts:
        x += vector.x * scale
        y += vector.y * scale
        z += vector.z * scale
    return _point(x, y, z)


def _dot(vector, other):
    return vector.dotProduct(other)


def _normalized(vector):
    copy = vector.copy()
    if copy.length < 1e-8:
        raise GeometryError('The cylinder axis is degenerate.')
    copy.normalize()
    return copy


def _perpendicular(axis):
    best = min(
        (_vec(1, 0, 0), _vec(0, 1, 0), _vec(0, 0, 1)),
        key=lambda candidate: abs(_dot(axis, candidate)),
    )
    radial = axis.crossProduct(best)
    return _normalized(radial)


def _world_vector(vector, occurrence):
    if not occurrence:
        return _normalized(vector)
    start = _point(0, 0, 0)
    end = _point(vector.x, vector.y, vector.z)
    start.transformBy(occurrence.transform)
    end.transformBy(occurrence.transform)
    return _normalized(_sub(end, start))


def _axial_values(face, origin, axis):
    values = []
    for edge in face.edges:
        for vertex in (edge.startVertex, edge.endVertex):
            if vertex and vertex.geometry:
                values.append(_dot(_sub(vertex.geometry, origin), axis))
        curve = edge.geometry
        center = getattr(curve, 'center', None)
        if center:
            values.append(_dot(_sub(center, origin), axis))
    if not values:
        box = face.boundingBox
        for x in (box.minPoint.x, box.maxPoint.x):
            for y in (box.minPoint.y, box.maxPoint.y):
                for z in (box.minPoint.z, box.maxPoint.z):
                    values.append(_dot(_sub(_point(x, y, z), origin), axis))
    return min(values), max(values)


def _is_external(face, origin, axis):
    evaluator = face.evaluator
    bounds = evaluator.parametricRange()
    u = (bounds.minPoint.x + bounds.maxPoint.x) / 2
    v = (bounds.minPoint.y + bounds.maxPoint.y) / 2
    parameter = adsk.core.Point2D.create(u, v)
    ok, point = evaluator.getPointAtParameter(parameter)
    ok_normal, normal = evaluator.getNormalAtParameter(parameter)
    if not ok or not ok_normal:
        raise GeometryError('Could not read the cylindrical face.')
    along = _dot(_sub(point, origin), axis)
    radial = _sub(point, _add_point(origin, (axis, along)))
    outward = normal
    body = face.body
    if body:
        probe = _add_point(point, (normal, 0.05))
        try:
            inside = body.pointContainment(probe) == adsk.fusion.PointContainment.PointInsidePointContainment
        except Exception:
            inside = False
        if inside:
            outward = _vec(-normal.x, -normal.y, -normal.z)
    return _dot(outward, radial) > 0


def inspect_cylinder(face):
    """Measure a cylindrical face in its owning component."""
    if not face:
        raise GeometryError('Select a cylindrical face.')
    native = _native(face)
    cylinder = adsk.core.Cylinder.cast(native.geometry)
    if not cylinder:
        raise GeometryError('Select a cylindrical face. Cones and flat faces are not threaded.')
    axis = _normalized(cylinder.axis)
    origin = cylinder.origin
    z_min, z_max = _axial_values(native, origin, axis)
    length_cm = z_max - z_min
    if length_cm <= 1e-4:
        raise GeometryError('The selected face is too short to thread.')
    external = _is_external(native, origin, axis)
    world_axis = _world_vector(axis, getattr(face, 'assemblyContext', None))
    vertical = abs(_dot(world_axis, _vec(0, 0, 1))) >= math.cos(math.radians(20))
    body = native.body
    return {
        'face': native,
        'proxy': face,
        'body': body,
        'component': body.parentComponent,
        'origin': origin,
        'axis': axis,
        'z_min_cm': z_min,
        'radius_mm': cylinder.radius * 10.0,
        'length_mm': length_cm * 10.0,
        'gender': 'male' if external else 'female',
        'axis_vertical': vertical,
        'token': face.entityToken,
        'body_token': body.entityToken,
    }


def empty_selection():
    return {
        'cylinder': None,
        'planar': None,
        'center': None,
        'inserts': {'faceCount': 0, 'pointCount': 0},
    }


def clear_held_selection():
    global _held_cylinder, _held_insert_targets
    _held_cylinder = None
    _held_insert_targets = []


def _face_usable(face):
    try:
        return bool(face and face.isValid and adsk.core.Cylinder.cast(_native(face).geometry))
    except Exception:
        return False


def _cylinder_summary(face):
    frame = inspect_cylinder(face)
    return {
        'token': frame['token'],
        'bodyToken': frame['body_token'],
        'radiusMm': round(frame['radius_mm'], 4),
        'diameterMm': round(frame['radius_mm'] * 2, 4),
        'lengthMm': round(frame['length_mm'], 4),
        'gender': frame['gender'],
        'axisVertical': frame['axis_vertical'],
    }


def _largest_cylinder_face(body):
    best = None
    best_area = -1.0
    for face in body.faces:
        if not adsk.core.Cylinder.cast(face.geometry):
            continue
        area = 0.0
        try:
            area = face.area
        except Exception:
            area = 0.0
        if area > best_area:
            best = face
            best_area = area
    return best


def resolve_cylinder_face(token=None):
    """Return the cylinder the palette is showing, even if the canvas selection was cleared."""
    global _held_cylinder
    if token:
        entity = None
        try:
            design = adsk.fusion.Design.cast(_app.activeProduct)
            entity = design.findEntityByToken(token) if design and token else None
        except Exception:
            entity = None
        face = adsk.fusion.BRepFace.cast(entity)
        if _face_usable(face):
            _held_cylinder = face
            return face
    if _face_usable(_held_cylinder):
        return _held_cylinder
    current = read_selection().get('cylinder')
    if current and _face_usable(_held_cylinder):
        return _held_cylinder
    raise GeometryError('Select a cylindrical face.')


def _entity_valid(entity):
    try:
        return bool(entity and entity.isValid)
    except Exception:
        return False


def _safe_token(entity):
    """Read an entity token. A face can go invalid once a cut consumes it."""
    try:
        token = entity.entityToken if entity else ''
    except Exception:
        return ''
    return token or ''


def _is_insert_point(entity):
    return bool(
        adsk.fusion.SketchPoint.cast(entity)
        or adsk.fusion.BRepVertex.cast(entity)
        or adsk.fusion.ConstructionPoint.cast(entity)
    )


def _capture_insert_targets(selection):
    targets = []
    seen = set()
    for index in range(selection.count):
        entity = selection.item(index).entity
        face = adsk.fusion.BRepFace.cast(entity)
        if face and adsk.core.Plane.cast(_native(face).geometry):
            key = ('face', face.entityToken)
            if key not in seen:
                seen.add(key)
                targets.append(('face', face))
            continue
        if _is_insert_point(entity):
            key = ('point', entity.entityToken)
            if key not in seen:
                seen.add(key)
                targets.append(('point', entity))
    return targets


def _insert_summary():
    faces = 0
    points = 0
    for kind, entity in _held_insert_targets:
        if not _entity_valid(entity):
            continue
        if kind == 'face':
            faces += 1
        elif kind == 'point':
            points += 1
    return {'faceCount': faces, 'pointCount': points}


def held_insert_targets():
    """Flat faces and points kept after the palette click clears the selection."""
    global _held_insert_targets
    valid = [(kind, entity) for kind, entity in _held_insert_targets if _entity_valid(entity)]
    _held_insert_targets = valid
    return list(valid)


def read_selection():
    """Summarize the active canvas selection for the palette."""
    global _held_cylinder, _held_insert_targets
    summary = empty_selection()
    try:
        selection = _ui.activeSelections
    except Exception:
        selection = None
    if selection and selection.count:
        captured = _capture_insert_targets(selection)
        if captured:
            _held_insert_targets = captured
        for index in range(selection.count):
            entity = selection.item(index).entity
            face = adsk.fusion.BRepFace.cast(entity)
            if not face:
                body = adsk.fusion.BRepBody.cast(entity)
                if body:
                    face = _largest_cylinder_face(body)
            if face and adsk.core.Cylinder.cast(_native(face).geometry):
                try:
                    summary['cylinder'] = _cylinder_summary(face)
                except GeometryError:
                    continue
                _held_cylinder = face
                continue
            if face and adsk.core.Plane.cast(_native(face).geometry) and summary['planar'] is None:
                summary['planar'] = {'token': face.entityToken}
                continue
            edge = adsk.fusion.BRepEdge.cast(entity)
            if edge and _circular_curve(edge.geometry) and summary['center'] is None:
                summary['center'] = {'token': edge.entityToken, 'kind': 'edge'}
                continue
            point = adsk.fusion.SketchPoint.cast(entity)
            if point and summary['center'] is None:
                summary['center'] = {'token': point.entityToken, 'kind': 'point'}
    if summary['cylinder'] is None and _face_usable(_held_cylinder):
        try:
            summary['cylinder'] = _cylinder_summary(_held_cylinder)
        except GeometryError:
            _held_cylinder = None
    summary['inserts'] = _insert_summary()
    return summary


def _circular_curve(geometry):
    return adsk.core.Circle3D.cast(geometry) or adsk.core.Arc3D.cast(geometry)


def _feature_name(prefix, suffix):
    return f'{NAME_ROOT}_{prefix}_{suffix}'


def _set_name(entity, name):
    try:
        entity.name = name
    except Exception:
        pass


def _timeline_index(entity):
    timeline_object = getattr(entity, 'timelineObject', None)
    if not timeline_object:
        return None
    try:
        return timeline_object.index
    except Exception:
        return None


def _allow_3d_sketch():
    preferences = getattr(_app, 'preferences', None)
    if not preferences:
        return None, None
    product_preferences = getattr(preferences, 'productPreferences', None)
    if not product_preferences:
        return None, None
    for item in product_preferences:
        fusion_preferences = adsk.fusion.FusionProductPreferences.cast(item)
        if not fusion_preferences:
            continue
        previous = fusion_preferences.is3DSketchingAllowed
        fusion_preferences.is3DSketchingAllowed = True
        return fusion_preferences, previous
    return None, None


def _restore_3d_sketch(fusion_preferences, previous):
    if fusion_preferences is not None and previous is not None:
        try:
            fusion_preferences.is3DSketchingAllowed = previous
        except Exception:
            pass


def _helix_points(frame, radius_cm, z0_cm, pitch_cm, turn0, turn1, samples, right_hand):
    axis = frame['axis']
    origin = frame['origin']
    radial = _perpendicular(axis)
    binormal = _normalized(axis.crossProduct(radial))
    direction = -1.0 if right_hand else 1.0
    span = max(turn1 - turn0, 1e-6)
    count = max(int(math.ceil(span * samples)), 8)
    points = []
    for index in range(count + 1):
        turn = turn0 + span * (index / count)
        theta = direction * turn * 2.0 * math.pi
        z = z0_cm + turn * pitch_cm
        cosine = math.cos(theta)
        sine = math.sin(theta)
        points.append(_add_point(
            origin,
            (axis, z),
            (radial, radius_cm * cosine),
            (binormal, radius_cm * sine),
        ))
    return points


def _hide(entity):
    """Keep helper sketches and planes out of the model. They read as loose coils."""
    for name in ('isLightBulbOn', 'isVisible'):
        if not hasattr(entity, name):
            continue
        try:
            setattr(entity, name, False)
            return
        except Exception:
            pass


def _add_spline(component, points, name):
    sketch = component.sketches.add(component.xYConstructionPlane)
    _set_name(sketch, name)
    try:
        sketch.isComputeDeferred = True
    except Exception:
        pass
    collection = adsk.core.ObjectCollection.create()
    for point in points:
        collection.add(point)
    spline = sketch.sketchCurves.sketchFittedSplines.add(collection)
    try:
        sketch.isComputeDeferred = False
    except Exception:
        pass
    _hide(sketch)
    if not spline:
        raise GeometryError('Could not build the helix.')
    end = spline.endSketchPoint.worldGeometry
    expected = points[-1]
    if end.distanceTo(expected) > 0.1:
        raise GeometryError(
            'The helix collapsed onto the sketch plane. Turn on 3D sketching in Fusion preferences and try again.'
        )
    return sketch, spline


def _path_from_curve(curve):
    path = adsk.fusion.Path.create(curve, adsk.fusion.ChainedCurveOptions.noChainedCurves)
    if not path:
        raise GeometryError('Could not use the helix as a sweep path.')
    return path


def _plane_on_curve(component, curve, name):
    """Plane perpendicular to the helix at its start. The tooth is drawn in this plane."""
    plane_input = component.constructionPlanes.createInput()
    origin = adsk.core.ValueInput.createByReal(0.0)
    placed = False
    try:
        placed = bool(plane_input.setByDistanceOnPath(curve, origin))
    except Exception:
        placed = False
    if not placed:
        plane_input = component.constructionPlanes.createInput()
        path = _path_from_curve(curve)
        placed = bool(plane_input.setByPath(
            path,
            adsk.fusion.PathDistanceTypes.ProportionalPathDistanceType,
            adsk.core.ValueInput.createByReal(0.0),
        ))
    if not placed:
        raise GeometryError('Could not place the thread profile on the helix.')
    plane = component.constructionPlanes.add(plane_input)
    _set_name(plane, name)
    _hide(plane)
    return plane


def _radial_from_point(frame, point):
    axis = frame['axis']
    along = _dot(_sub(point, frame['origin']), axis)
    radial = _sub(point, _add_point(frame['origin'], (axis, along)))
    return _normalized(radial)


def _profile_points(frame, path_point, corners):
    radial = _radial_from_point(frame, path_point)
    axis = frame['axis']
    points = []
    for axial_mm, radial_mm in corners:
        points.append(_add_point(
            path_point,
            (axis, _mm_to_cm(axial_mm)),
            (radial, _mm_to_cm(radial_mm)),
        ))
    return points


def _sketch_points(sketch, model_points):
    local = []
    for point in model_points:
        mapped = sketch.modelToSketchSpace(point)
        local.append(_point(mapped.x, mapped.y, 0))
    return local


def _draw_quad(component, plane, model_points, name):
    sketch = component.sketches.add(plane)
    _set_name(sketch, name)
    _hide(sketch)
    local = _sketch_points(sketch, model_points)
    lines = sketch.sketchCurves.sketchLines
    for index in range(len(local)):
        lines.addByTwoPoints(local[index], local[(index + 1) % len(local)])
    if sketch.profiles.count < 1:
        raise GeometryError('The thread profile did not close. Try a coarser pitch or a larger face.')
    profile_shape = sketch.profiles.item(0)
    try:
        area_cm2 = profile_shape.areaProperties().area
    except Exception:
        area_cm2 = 1.0
    if area_cm2 < 1e-5:
        raise GeometryError('The thread profile collapsed flat, so the sweep would be a wire.')
    return sketch, profile_shape


def _operation(name):
    if name == 'join':
        return adsk.fusion.FeatureOperations.JoinFeatureOperation
    return adsk.fusion.FeatureOperations.CutFeatureOperation


def _sweep_solid(component, profile_shape, path, guide_face, name):
    """Sweep a new solid along the helix, guided by the cylinder.

    The result stays a separate body. Joining each section onto the part as it
    is built splits the guide face, and the next section comes out as a ribbon.
    A sweep with no guide does the same. There is no unguided fallback.
    """
    sweep_input = component.features.sweepFeatures.createInput(
        profile_shape,
        path,
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    )
    try:
        sweep_input.isSolid = True
    except Exception:
        pass
    guides = adsk.fusion.BRepFaceVector()
    guides.append(guide_face)
    sweep_input.guideSurfaces = guides
    try:
        sweep_input.isChainSelection = False
    except Exception:
        pass
    try:
        sweep = component.features.sweepFeatures.add(sweep_input)
    except Exception as exc:
        raise GeometryError(f'Fusion could not sweep this thread section. {exc}') from exc
    if not sweep or sweep.bodies.count < 1:
        raise GeometryError(
            'Fusion could not sweep this thread section. The profile missed the cylinder, or the pitch is too fine for this diameter.'
        )
    _set_name(sweep, name)
    return sweep, sweep.bodies.item(sweep.bodies.count - 1)


def _combine(component, target, tools, operation, name):
    collection = adsk.core.ObjectCollection.create()
    for tool in tools:
        collection.add(tool)
    combine_input = component.features.combineFeatures.createInput(target, collection)
    combine_input.operation = operation
    combine_input.isKeepToolBodies = False
    try:
        feature = component.features.combineFeatures.add(combine_input)
    except Exception as exc:
        raise GeometryError(f'Could not join the thread into one solid. {exc}') from exc
    if not feature:
        raise GeometryError('Could not join the thread into one solid.')
    _set_name(feature, name)
    return feature


def _delete_item(item):
    try:
        return bool(item.deleteMe())
    except Exception:
        return False


def _delete_group(design, prefix):
    groups = design.timeline.timelineGroups.itemByName(f'{NAME_ROOT} {prefix}')
    if not groups:
        return
    if not isinstance(groups, list):
        groups = [groups]
    for group in groups:
        _delete_item(group)


def delete_everywhere(prefix):
    """Remove a thread or insert from every component. Parameters stay."""
    design = _design()
    components = []
    try:
        components.extend(list(design.allComponents))
    except Exception:
        components.append(design.rootComponent)
    seen = set()
    for component in components:
        marker = id(component)
        if marker in seen:
            continue
        seen.add(marker)
        delete_named(component, prefix)


def delete_named(component, prefix):
    """Remove geometry created for one thread or insert. Parameters stay."""
    stem = f'{NAME_ROOT}_{prefix}'
    design = _design()
    _delete_group(design, prefix)
    collections = (
        component.features.chamferFeatures,
        component.features.revolveFeatures,
        component.features.sweepFeatures,
        component.features.extrudeFeatures,
        component.features.combineFeatures,
    )
    for _pass in range(3):
        pending = []
        for collection in collections:
            for index in range(collection.count):
                item = collection.item(index)
                if item.name and item.name.startswith(stem):
                    pending.append(item)
        if not pending:
            break
        for item in reversed(pending):
            _delete_item(item)

    for collection in (component.sketches, component.constructionPlanes, component.constructionAxes):
        for index in range(collection.count - 1, -1, -1):
            item = collection.item(index)
            if item.name and item.name.startswith(stem):
                _delete_item(item)

    _delete_group(design, prefix)


def _tag(entity, fields):
    attributes = entity.attributes
    for key, value in fields.items():
        text = '' if value is None else str(value)
        existing = attributes.itemByName(ATTR_GROUP, key)
        if existing:
            existing.value = text
        else:
            attributes.add(ATTR_GROUP, key, text)


def _group_timeline(design, indexes, name):
    indexes = [index for index in indexes if index is not None]
    if len(indexes) < 2:
        return
    try:
        group = design.timeline.timelineGroups.add(min(indexes), max(indexes))
        if group:
            group.name = name
    except Exception:
        pass


def _axis_from_face(component, face, name):
    axis_input = component.constructionAxes.createInput()
    if not axis_input.setByCircularFace(face):
        raise GeometryError('Could not build an axis through the selected face.')
    axis = component.constructionAxes.add(axis_input)
    _set_name(axis, name)
    _hide(axis)
    return axis


def _axial_plane(component, construction_axis, name):
    plane_input = component.constructionPlanes.createInput()
    for angle in ('0 deg', '90 deg'):
        if plane_input.setByAngle(
            construction_axis,
            adsk.core.ValueInput.createByString(angle),
            component.xYConstructionPlane,
        ):
            plane = component.constructionPlanes.add(plane_input)
            _set_name(plane, name)
            _hide(plane)
            return plane
        plane_input = component.constructionPlanes.createInput()
    raise GeometryError('Could not place a plane through the thread axis.')


def _radial_in_plane(sketch, axis):
    for direction in (sketch.xDirection, sketch.yDirection):
        copy = direction.copy()
        along = _dot(copy, axis)
        copy.x -= axis.x * along
        copy.y -= axis.y * along
        copy.z -= axis.z * along
        if copy.length > 0.2:
            return _normalized(copy)
    raise GeometryError('Could not find the radial direction for the lead-in.')


def _lead_in(component, frame, construction_axis, spec, body, created):
    if spec['lead_mm'] <= 0.05:
        return
    plane = _axial_plane(component, construction_axis, _feature_name(spec['prefix'], 'LeadPlane'))
    created.append(plane)
    sketch = component.sketches.add(plane)
    _set_name(sketch, _feature_name(spec['prefix'], 'Lead'))
    _hide(sketch)
    created.append(sketch)
    radial = _radial_in_plane(sketch, frame['axis'])
    inner_mm = max(0.2, min(spec['root_radius_mm'], spec['crest_radius_mm']) - 0.05)
    outer_mm = max(spec['root_radius_mm'], spec['crest_radius_mm']) + 0.05
    z0 = frame['z_min_cm'] + _mm_to_cm(spec['offset_mm'])
    length_cm = _mm_to_cm(spec['length_mm'])
    lead_cm = _mm_to_cm(spec['lead_mm'])
    ends = (
        (z0, z0 + lead_cm, 'Start'),
        (z0 + length_cm, z0 + length_cm - lead_cm, 'End'),
    )
    for end_z, inner_z, suffix in ends:
        model_points = (
            _add_point(frame['origin'], (frame['axis'], end_z), (radial, _mm_to_cm(inner_mm))),
            _add_point(frame['origin'], (frame['axis'], end_z), (radial, _mm_to_cm(outer_mm))),
            _add_point(frame['origin'], (frame['axis'], inner_z), (radial, _mm_to_cm(outer_mm))),
        )
        local = _sketch_points(sketch, model_points)
        lines = sketch.sketchCurves.sketchLines
        for index in range(3):
            lines.addByTwoPoints(local[index], local[(index + 1) % 3])
    if sketch.profiles.count < 1:
        raise GeometryError('Lead-in profile did not close.')
    for index in range(sketch.profiles.count):
        revolve_input = component.features.revolveFeatures.createInput(
            sketch.profiles.item(index),
            construction_axis,
            adsk.fusion.FeatureOperations.CutFeatureOperation,
        )
        revolve_input.setAngleExtent(False, adsk.core.ValueInput.createByString('360 deg'))
        try:
            revolve_input.participantBodies = [body]
        except Exception:
            pass
        revolve = component.features.revolveFeatures.add(revolve_input)
        if not revolve:
            raise GeometryError('Lead-in revolve failed.')
        _set_name(revolve, _feature_name(spec['prefix'], f'Lead{suffix if sketch.profiles.count > 1 else index}'))
        created.append(revolve)


def build_thread(frame, spec, prefix):
    """Sweep the resolved profile. Returns the primary feature and any warnings."""
    spec = dict(spec)
    spec['prefix'] = prefix
    component = frame['component']
    created = []
    warnings = []
    fusion_preferences, previous_3d = _allow_3d_sketch()
    try:
        pitch_cm = _mm_to_cm(spec['pitch_mm'])
        radius_cm = _mm_to_cm(frame['radius_mm'])
        z0 = frame['z_min_cm'] + _mm_to_cm(spec['offset_mm'])
        samples = spec['samples_per_turn']
        turns = spec['turns']
        if spec.get('chamfer_mm', 0) > 0.05:
            try:
                _chamfer_rims(component, frame, prefix, created)
                _refresh_guide_face(frame)
            except Exception as exc:
                warnings.append(f'Edge chamfer was skipped. {exc}')
        # One sweep when the helix is short. Longer helices are cut into 4-turn
        # pieces first: asking Fusion to sweep the whole thing can crash the session,
        # and Python never gets a chance to recover.
        max_turns = 4.0
        overlap = 0.05
        if turns <= max_turns:
            segments = [(0.0, turns)]
        else:
            warnings.append(
                'This thread is long, so it was built as several sweeps and joined into one tooth.'
            )
            segments = []
            start = 0.0
            while start < turns - 1e-6:
                stop = min(turns, start + max_turns)
                seg_start = max(0.0, start - (overlap if start > 0 else 0.0))
                seg_stop = min(turns, stop + (overlap if stop < turns - 1e-6 else 0.0))
                segments.append((seg_start, seg_stop))
                start = stop

        several = len(segments) > 1
        solids = []
        primary = None
        for index, (turn0, turn1) in enumerate(segments):
            suffix = str(index + 1) if several else ''
            points = _helix_points(
                frame, radius_cm, z0, pitch_cm, turn0, turn1, samples, spec['right_hand']
            )
            helix_sketch, spline = _add_spline(
                component, points, _feature_name(prefix, f'Helix{suffix}')
            )
            created.append(helix_sketch)
            path = _path_from_curve(spline)
            plane = _plane_on_curve(component, spline, _feature_name(prefix, f'Plane{suffix}'))
            created.append(plane)
            section = _profile_points(frame, points[0], spec['corners'])
            profile_sketch, profile_shape = _draw_quad(
                component, plane, section, _feature_name(prefix, f'Profile{suffix}')
            )
            created.append(profile_sketch)
            sweep, solid = _sweep_solid(
                component,
                profile_shape,
                path,
                frame['face'],
                _feature_name(prefix, f'Sweep{suffix}'),
            )
            created.append(sweep)
            solids.append(solid)
            primary = sweep

        thread_body = solids[0]
        if len(solids) > 1:
            merged = _combine(
                component,
                solids[0],
                solids[1:],
                adsk.fusion.FeatureOperations.JoinFeatureOperation,
                _feature_name(prefix, 'Join'),
            )
            created.append(merged)
            thread_body = solids[0]
        fused = _combine(
            component,
            frame['body'],
            [thread_body],
            _operation(spec['operation']),
            _feature_name(prefix, 'Fuse'),
        )
        created.append(fused)
        primary = fused

        try:
            construction_axis = _axis_from_face(
                component, frame['face'], _feature_name(prefix, 'Axis')
            )
            created.append(construction_axis)
            _lead_in(component, frame, construction_axis, spec, frame['body'], created)
        except Exception as exc:
            warnings.append(f'Lead-in was skipped. {exc}')

        _tag(primary, _thread_fields(frame, spec, prefix))
        _group_timeline(
            _design(),
            [_timeline_index(item) for item in created],
            f'{NAME_ROOT} {prefix}',
        )
        return primary, warnings
    except Exception:
        for item in reversed(created):
            _delete_item(item)
        raise
    finally:
        _restore_3d_sketch(fusion_preferences, previous_3d)


def _thread_fields(frame, spec, prefix):
    return {
        'primary': '1',
        'kind': 'thread',
        'id': prefix,
        'prefix': prefix,
        'gender': spec['gender'],
        'build': spec['build'],
        'family': spec['family'],
        'size': spec['size'],
        'mating': spec['mating'],
        'label': spec['label'],
        'face': frame['token'],
        'body': frame['body_token'],
        'radius': f'{frame["radius_mm"]:.6f}',
        'right': '1' if spec['right_hand'] else '0',
        'lead': '1' if spec['lead'] else '0',
        'chamfer': '1' if spec.get('chamfer') else '0',
        'flip': '1' if spec.get('flip') else '0',
    }


def _point_containment_sign(face, body):
    """Negative when the face normal points out of the material."""
    native = _native(face)
    evaluator = native.evaluator
    bounds = evaluator.parametricRange()
    parameter = adsk.core.Point2D.create(
        (bounds.minPoint.x + bounds.maxPoint.x) / 2,
        (bounds.minPoint.y + bounds.maxPoint.y) / 2,
    )
    ok, point = evaluator.getPointAtParameter(parameter)
    ok_normal, normal = evaluator.getNormalAtParameter(parameter)
    if not ok or not ok_normal:
        return -1.0
    normal.normalize()
    probe = _add_point(point, (normal, 0.02))
    containment = body.pointContainment(probe)
    if containment == adsk.fusion.PointContainment.PointInsidePointContainment:
        return 1.0
    return -1.0


def _end_planar_face(cylinder_face):
    found = []
    seen = set()
    for edge in cylinder_face.edges:
        for face in edge.faces:
            token = face.entityToken
            if token in seen:
                continue
            if adsk.core.Plane.cast(face.geometry):
                seen.add(token)
                found.append(face)
    if not found:
        return None
    def height(face):
        box = face.boundingBox
        return (box.minPoint.z + box.maxPoint.z) / 2
    return max(found, key=height)


def _face_extent_center(face):
    """Center of a flat face along its two in-plane axes."""
    native = _native(face)
    plane = adsk.core.Plane.cast(native.geometry)
    if not plane:
        raise GeometryError('Select a flat face.')
    circles = []
    for edge in native.edges:
        curve = _circular_curve(edge.geometry)
        if curve:
            circles.append(curve.center)
    if len(circles) == 1:
        return circles[0]
    normal = _normalized(plane.normal)
    x_dir = _perpendicular(normal)
    y_dir = _normalized(normal.crossProduct(x_dir))
    origin = plane.origin
    xs = []
    ys = []
    for edge in native.edges:
        for vertex in (edge.startVertex, edge.endVertex):
            if not vertex:
                continue
            relative = _sub(vertex.geometry, origin)
            xs.append(_dot(relative, x_dir))
            ys.append(_dot(relative, y_dir))
    if not xs:
        centroid = getattr(native, 'centroid', None)
        if centroid:
            return centroid
        raise GeometryError('Could not find the center of a selected face.')
    return _add_point(origin, (x_dir, (min(xs) + max(xs)) / 2.0), (y_dir, (min(ys) + max(ys)) / 2.0))


def _best_planar_face(faces):
    best = None
    best_area = -1.0
    for face in faces:
        if not adsk.core.Plane.cast(face.geometry):
            continue
        try:
            area = face.area
        except Exception:
            area = 0.0
        if area > best_area:
            best = face
            best_area = area
    return _native(best) if best else None


def _point_in_face_bounds(face, point, plane):
    normal = _normalized(plane.normal)
    x_dir = _perpendicular(normal)
    y_dir = _normalized(normal.crossProduct(x_dir))
    origin = plane.origin
    xs = []
    ys = []
    for edge in face.edges:
        for vertex in (edge.startVertex, edge.endVertex):
            if not vertex:
                continue
            relative = _sub(vertex.geometry, origin)
            xs.append(_dot(relative, x_dir))
            ys.append(_dot(relative, y_dir))
    if not xs:
        return False
    relative = _sub(point, origin)
    x = _dot(relative, x_dir)
    y = _dot(relative, y_dir)
    margin = 0.05
    return min(xs) - margin <= x <= max(xs) + margin and min(ys) - margin <= y <= max(ys) + margin


def _face_contains_point(face, point):
    plane = adsk.core.Plane.cast(face.geometry)
    if not plane:
        return False
    if abs(_dot(_sub(point, plane.origin), _normalized(plane.normal))) > 0.05:
        return False
    try:
        result = face.evaluator.getParameterAtPoint(point)
        parameter = result[1] if isinstance(result, tuple) and len(result) > 1 and result[0] else None
        if parameter is not None:
            on_face = face.evaluator.isParameterOnFace(parameter)
            if isinstance(on_face, tuple):
                return bool(on_face[-1])
            return bool(on_face)
    except Exception:
        pass
    return _point_in_face_bounds(face, point, plane)


def _find_planar_face_at_point(component, point):
    bodies = []
    try:
        bodies.extend(list(component.bRepBodies))
    except Exception:
        pass
    for body in bodies:
        for face in body.faces:
            if _face_contains_point(face, point):
                return _native(face)
    return None


def _components(design):
    try:
        return list(design.allComponents)
    except Exception:
        return [design.rootComponent]


def _to_component_space(point, component, design):
    if component == design.rootComponent:
        return point
    try:
        occurrences = design.rootComponent.allOccurrences
    except Exception:
        return point
    for occurrence in occurrences:
        if occurrence.component != component:
            continue
        inverse = occurrence.transform.copy()
        inverse.invert()
        local = point.copy()
        local.transformBy(inverse)
        return local
    return point


def _find_face_for_model_point(point):
    """Return a flat face under a world-space point, and the point in that face's component."""
    design = _design()
    for component in _components(design):
        local = _to_component_space(point, component, design)
        for candidate in (local, point):
            found = _find_planar_face_at_point(component, candidate)
            if found:
                return found, candidate
    return None, point


def _sketch_reference_face(sketch):
    """Read a sketch's face after rolling to the sketch. Fusion refuses this at the timeline end."""
    design = _design()
    timeline = getattr(design, 'timeline', None)
    marker = timeline.markerPosition if timeline else None
    reference = None
    try:
        timeline_object = getattr(sketch, 'timelineObject', None)
        if timeline_object:
            timeline_object.rollTo(True)
        reference = sketch.referencePlane
    except Exception:
        reference = None
    finally:
        if timeline is not None and marker is not None:
            try:
                timeline.markerPosition = marker
            except Exception:
                pass
    face = adsk.fusion.BRepFace.cast(reference) if reference else None
    if face and adsk.core.Plane.cast(_native(face).geometry):
        return _native(face)
    return None


def _target_from_point(entity):
    vertex = adsk.fusion.BRepVertex.cast(entity)
    if vertex:
        native = _native(vertex)
        point = native.geometry
        face = None
        try:
            face = _best_planar_face(native.faces)
        except Exception:
            face = None
        if face:
            return face, point
        found, local = _find_face_for_model_point(point)
        if not found:
            raise GeometryError('A selected point is not on a flat face.')
        return found, local
    sketch_point = adsk.fusion.SketchPoint.cast(entity)
    if sketch_point:
        native = _native(sketch_point) or sketch_point
        point = native.worldGeometry
        found, local = _find_face_for_model_point(point)
        if found:
            return found, local
        face = _sketch_reference_face(native.parentSketch)
        if not face:
            raise GeometryError('A selected point is not on a flat face.')
        return face, local
    construction = adsk.fusion.ConstructionPoint.cast(entity)
    if construction:
        point = construction.geometry
        found, local = _find_face_for_model_point(point)
        if not found:
            raise GeometryError('A selected point is not on a flat face.')
        return found, local
    raise GeometryError('A selected point cannot start a pocket.')


def _insert_placements(targets):
    placements = []
    for kind, entity in targets:
        if kind == 'face':
            face = _native(entity)
            placements.append((face, _face_extent_center(face)))
            continue
        placements.append(_target_from_point(entity))
    return placements


def _link_diameter(sketch, circle, prefix):
    bounds = circle.boundingBox
    text = _point(bounds.maxPoint.x, bounds.maxPoint.y, 0)
    dimension = sketch.sketchDimensions.addDiameterDimension(circle, text, True)
    if dimension and dimension.parameter:
        dimension.parameter.expression = f'{prefix}_dia'


def _profile_matching_circle(sketch, radius_cm):
    """Use the circle, not a face outline Fusion projected into the sketch."""
    if sketch.profiles.count < 1:
        raise GeometryError('Could not close an insert pocket profile.')
    target = math.pi * radius_cm * radius_cm
    best = sketch.profiles.item(0)
    best_delta = None
    for index in range(sketch.profiles.count):
        profile = sketch.profiles.item(index)
        try:
            area = profile.areaProperties().area
        except Exception:
            continue
        delta = abs(area - target)
        if best_delta is None or delta < best_delta:
            best = profile
            best_delta = delta
    return best


def _cut_pocket(face, center, prefix, index, hole_mm, created, warnings):
    body = face.body
    component = body.parentComponent
    sketch = component.sketches.add(face)
    _set_name(sketch, _feature_name(prefix, f'Pocket{index + 1}'))
    created.append(sketch)
    local = sketch.modelToSketchSpace(center)
    radius_cm = _mm_to_cm(float(hole_mm) / 2.0)
    circle = sketch.sketchCurves.sketchCircles.addByCenterRadius(
        _point(local.x, local.y, 0),
        radius_cm,
    )
    try:
        _link_diameter(sketch, circle, prefix)
    except Exception:
        if index == 0:
            warnings.append('Hole diameter is stored as a parameter, but the sketch dimension could not be linked.')
    profile = _profile_matching_circle(sketch, radius_cm)
    sign = _point_containment_sign(face, body)
    distance = f'{prefix}_depth' if sign > 0 else f'-{prefix}_depth'
    extrude_input = component.features.extrudeFeatures.createInput(
        profile,
        adsk.fusion.FeatureOperations.CutFeatureOperation,
    )
    extrude_input.setDistanceExtent(False, adsk.core.ValueInput.createByString(distance))
    try:
        extrude_input.participantBodies = [body]
    except Exception:
        pass
    extrude = component.features.extrudeFeatures.add(extrude_input)
    if not extrude:
        raise GeometryError('Could not cut an insert pocket.')
    _set_name(extrude, _feature_name(prefix, f'Cut{index + 1}'))
    created.append(extrude)
    try:
        _chamfer_opening(component, extrude, prefix, created, center, index)
    except Exception:
        if not any(warning.startswith('Entrance chamfer') for warning in warnings):
            warnings.append('Entrance chamfer was skipped on at least one pocket.')
    return extrude, body


def build_insert(data, prefix):
    """Cut one heat-set pocket for every held flat face or point."""
    design = _design()
    created = []
    warnings = []
    try:
        targets = held_insert_targets()
        if not targets:
            raise GeometryError('Select one or more flat faces or points.')
        placements = _insert_placements(targets)
        primary = None
        body_token = ''
        face_token = ''
        for index, (face, center) in enumerate(placements):
            if primary is None:
                face_token = _safe_token(face)
                body_token = _safe_token(getattr(face, 'body', None))
            extrude, _body = _cut_pocket(face, center, prefix, index, data['hole_mm'], created, warnings)
            if primary is None:
                primary = extrude
        size = data.get('size') or 'Custom'
        count = len(placements)
        label = f'{size} heat-set' if count == 1 else f'{size} heat-set × {count}'
        _tag(primary, {
            'primary': '1',
            'kind': 'insert',
            'id': prefix,
            'prefix': prefix,
            'size': size,
            'label': label,
            'face': face_token,
            'body': body_token,
            'count': str(count),
        })
        _group_timeline(
            design,
            [_timeline_index(item) for item in created],
            f'{NAME_ROOT} {prefix}',
        )
        return primary, warnings
    except Exception:
        for item in reversed(created):
            _delete_item(item)
        try:
            delete_everywhere(prefix)
        except Exception:
            pass
        raise


def _rim_edges(face, origin, axis):
    """Circular edges at the two ends of the cylindrical face."""
    z_min, z_max = _axial_values(face, origin, axis)
    chosen = []
    for edge in face.edges:
        curve = _circular_curve(edge.geometry)
        if not curve:
            continue
        center = getattr(curve, 'center', None)
        if not center:
            continue
        along = _dot(_sub(center, origin), axis)
        if min(abs(along - z_min), abs(along - z_max)) <= 0.02:
            chosen.append(edge)
    return chosen


def _chamfer_rims(component, frame, prefix, created):
    """Chamfer the cylinder rims before the thread is swept."""
    edges = adsk.core.ObjectCollection.create()
    for edge in _rim_edges(frame['face'], frame['origin'], frame['axis']):
        edges.add(edge)
    if edges.count < 1:
        raise GeometryError('The face has no circular end to chamfer.')
    chamfer_input = component.features.chamferFeatures.createInput(edges, True)
    chamfer_input.setToEqualDistance(adsk.core.ValueInput.createByString(f'{prefix}_chamfer'))
    try:
        chamfer = component.features.chamferFeatures.add(chamfer_input)
    except Exception as exc:
        raise GeometryError(f'Fusion could not chamfer the end. {exc}') from exc
    if not chamfer:
        raise GeometryError('Fusion could not chamfer the end.')
    _set_name(chamfer, _feature_name(prefix, 'Edge'))
    created.append(chamfer)


def _refresh_guide_face(frame):
    """The chamfer shortens the cylinder. Sweep the thread on the face that remains."""
    best = None
    best_area = -1.0
    try:
        faces = frame['body'].faces
    except Exception:
        return
    for index in range(faces.count):
        face = faces.item(index)
        try:
            cylinder = adsk.core.Cylinder.cast(face.geometry)
        except Exception:
            continue
        if not cylinder:
            continue
        if abs(cylinder.radius * 10.0 - frame['radius_mm']) > 0.4:
            continue
        area = 0.0
        try:
            area = face.area
        except Exception:
            area = 0.0
        if area > best_area:
            best = face
            best_area = area
    if best:
        frame['face'] = _native(best)


def _chamfer_opening(component, extrude, prefix, created, near_point, index=0):
    edges = adsk.core.ObjectCollection.create()
    candidates = []
    for face in extrude.faces:
        for edge in face.edges:
            if _circular_curve(edge.geometry):
                candidates.append((edge.geometry.center.distanceTo(near_point), edge))
    if not candidates:
        raise GeometryError('No circular edge to chamfer.')
    opening = min(candidates, key=lambda item: item[0])[1]
    edges.add(opening)
    chamfer_input = component.features.chamferFeatures.createInput(edges, True)
    chamfer_input.setToEqualDistance(adsk.core.ValueInput.createByString(f'{prefix}_chamfer'))
    chamfer = component.features.chamferFeatures.add(chamfer_input)
    if not chamfer:
        raise GeometryError('Chamfer failed.')
    _set_name(chamfer, _feature_name(prefix, f'Chamfer{index + 1}'))
    created.append(chamfer)


def find_cylinder(design, token, body_token, radius_mm):
    """Find the face again after the previous thread has been deleted."""
    if token:
        face = adsk.fusion.BRepFace.cast(design.findEntityByToken(token))
        if face and adsk.core.Cylinder.cast(_native(face).geometry):
            return face
    if not body_token:
        return None
    body = adsk.fusion.BRepBody.cast(design.findEntityByToken(body_token))
    if not body:
        return None
    best = None
    best_delta = 1e9
    for face in body.faces:
        cylinder = adsk.core.Cylinder.cast(face.geometry)
        if not cylinder:
            continue
        delta = abs(cylinder.radius * 10.0 - float(radius_mm))
        if delta < best_delta:
            best = face
            best_delta = delta
    if best is not None and best_delta < 0.75:
        return best
    return None
