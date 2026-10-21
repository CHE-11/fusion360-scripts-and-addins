"""List, create, delete, and select sketch geometric constraints."""

import adsk.core
import adsk.fusion

from ...lib import fusionAddInUtils as futil

app = adsk.core.Application.get()
ui = app.userInterface

# Temporary canvas highlight. Fusion cannot select most sketch geometry unless
# that sketch is being edited, and a constraint's entityToken resolves to a
# BaseVector. Hover draws the real curves instead.
_highlight_set = None
_highlight_graphics = None

_TYPE_INFO = {
    'CoincidentConstraint': ('coincident', 'Coincident'),
    'CollinearConstraint': ('collinear', 'Collinear'),
    'ConcentricConstraint': ('concentric', 'Concentric'),
    'EqualConstraint': ('equal', 'Equal'),
    'HorizontalConstraint': ('horizontal', 'Horizontal'),
    'HorizontalPointsConstraint': ('horizontalPoints', 'Horizontal points'),
    'MidPointConstraint': ('midpoint', 'Midpoint'),
    'ParallelConstraint': ('parallel', 'Parallel'),
    'PerpendicularConstraint': ('perpendicular', 'Perpendicular'),
    'SmoothConstraint': ('smooth', 'Smooth'),
    'SymmetryConstraint': ('symmetry', 'Symmetry'),
    'TangentConstraint': ('tangent', 'Tangent'),
    'VerticalConstraint': ('vertical', 'Vertical'),
    'VerticalPointsConstraint': ('verticalPoints', 'Vertical points'),
    'OffsetConstraint': ('offset', 'Offset'),
}

_ENTITY_ROLES = {
    'CoincidentConstraint': ('point', 'entity'),
    'CollinearConstraint': ('lineOne', 'lineTwo'),
    'ConcentricConstraint': ('entityOne', 'entityTwo'),
    'EqualConstraint': ('curveOne', 'curveTwo'),
    'HorizontalConstraint': ('line',),
    'HorizontalPointsConstraint': ('pointOne', 'pointTwo'),
    'MidPointConstraint': ('point', 'midPointCurve'),
    'ParallelConstraint': ('lineOne', 'lineTwo'),
    'PerpendicularConstraint': ('lineOne', 'lineTwo'),
    'SmoothConstraint': ('curveOne', 'curveTwo'),
    'SymmetryConstraint': ('entityOne', 'entityTwo', 'symmetryLine'),
    'TangentConstraint': ('curveOne', 'curveTwo'),
    'VerticalConstraint': ('line',),
    'VerticalPointsConstraint': ('pointOne', 'pointTwo'),
    'OffsetConstraint': ('curve', 'offsetCurve'),
}

_GENERIC_ROLES = (
    'point', 'entity', 'line', 'lineOne', 'lineTwo', 'entityOne', 'entityTwo',
    'curveOne', 'curveTwo', 'pointOne', 'pointTwo', 'midPointCurve', 'symmetryLine',
    'curve', 'offsetCurve',
)


def empty_selection():
    return {
        'sketchName': '',
        'sketchToken': '',
        'entities': [],
        'compatible': [],
        'error': None,
    }


def list_sketches():
    design = _design()
    root_name = ''
    try:
        root_name = design.rootComponent.name
    except Exception:
        root_name = ''

    groups = []
    for comp in _components(design):
        sketches = []
        for index in range(comp.sketches.count):
            sketch = comp.sketches.item(index)
            sketches.append(_serialize_sketch(sketch))
        sketches.sort(key=lambda item: (item['isFullyConstrained'], item['name'].lower()))
        if sketches:
            groups.append({
                'name': _safe_name(comp, 'Component'),
                'token': _token(comp),
                'sketches': sketches,
            })

    groups.sort(key=lambda item: (item['name'] != root_name, item['name'].lower()))
    return {'components': groups}


def delete_constraint(data):
    data = data or {}
    if data.get('sharedPointToken'):
        return _detach_shared_point(data)

    design = _design()
    constraint = _locate_constraint(design, data)
    if not _is_deletable(constraint):
        raise ValueError('This constraint cannot be deleted.')
    label = _type_info(constraint)[1]
    sketch = _parent_sketch(constraint)
    sketch_token = _token(sketch) if sketch else data.get('sketchToken', '')
    try:
        constraint.deleteMe()
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    return {'sketchToken': sketch_token, 'label': label}


def select_item(data):
    if isinstance(data, str):
        data = {'token': data}
    data = data or {}
    design = _design()

    if data.get('sharedPointToken'):
        point, entities = _shared_point_targets(design, data)
        sketch = _parent_sketch(point)
        _reveal_sketch(sketch)
        selected = _try_select(entities, clear=True)
        highlighted = 0
        if selected == 0:
            highlighted = show_highlight(sketch, entities)
            if sketch:
                selected = _try_select([sketch], clear=False)
        else:
            clear_highlight()
        if selected == 0 and highlighted == 0:
            raise ValueError('Fusion could not select that geometry.')
        return {'selected': selected, 'highlighted': highlighted}

    # Geometric-constraint tokens do not round-trip through findEntityByToken.
    if data.get('sketchToken') and data.get('type') and _as_index(data.get('index')) is not None:
        constraint = _locate_constraint(design, data)
        entities = _live_entities(constraint)
        sketch = _parent_sketch(constraint)
        _reveal_sketch(sketch)
        selected = _try_select(entities, clear=True)
        highlighted = 0
        if selected == 0:
            highlighted = show_highlight(sketch, entities)
            if sketch:
                selected = _try_select([sketch], clear=False)
        else:
            clear_highlight()
        if selected == 0 and highlighted == 0:
            raise ValueError('Fusion could not select that geometry.')
        return {'selected': selected, 'highlighted': highlighted}

    return _select_targets([_find(design, data.get('token', ''))])


def highlight_constraint(data):
    data = data or {}
    design = _design()
    if data.get('sharedPointToken'):
        point, entities = _shared_point_targets(design, data)
        sketch = _parent_sketch(point)
    else:
        constraint = _locate_constraint(design, data)
        entities = _live_entities(constraint)
        sketch = _parent_sketch(constraint)
    _reveal_sketch(sketch)
    return {'highlighted': show_highlight(sketch, entities)}


def clear_highlight():
    global _highlight_set, _highlight_graphics
    if _highlight_set is not None:
        try:
            _highlight_set.deleteMe()
        except Exception:
            pass
        _highlight_set = None
    if _highlight_graphics is not None:
        try:
            _highlight_graphics.deleteMe()
        except Exception:
            pass
        _highlight_graphics = None
    return {'cleared': True}


def show_highlight(sketch, entities):
    """Highlight constraint geometry. Returns how many entities were drawn.

    Sketch curves are not selectable outside sketch edit, and HighlightSet uses
    that same rule. The cyan graphics are what actually show up in the canvas.
    """
    clear_highlight()
    if not entities:
        return 0
    highlighted = _highlight_with_set(entities)
    drawn = bool(sketch) and _highlight_with_graphics(sketch, entities)
    if highlighted or drawn:
        return len(entities)
    return 0


def read_selection():
    try:
        _design()
    except RuntimeError as exc:
        result = empty_selection()
        result['error'] = str(exc)
        return result

    entities = []
    try:
        selections = ui.activeSelections
        for index in range(selections.count):
            entity = selections.item(index).entity
            if _kind(entity):
                entities.append(entity)
    except Exception:
        futil.log('Could not read the active selection.')
        return empty_selection()

    if not entities:
        return empty_selection()

    sketch = None
    sketch_tokens = []
    for entity in entities:
        parent = _parent_sketch(entity)
        if parent is None:
            result = empty_selection()
            result['error'] = 'Selected geometry is not on a sketch.'
            return result
        sketch = parent
        sketch_tokens.append(_token(parent))

    if len(set(sketch_tokens)) > 1:
        result = empty_selection()
        result['error'] = 'Selected geometry is on more than one sketch.'
        return result

    result = {
        'sketchName': _safe_name(sketch, 'Sketch'),
        'sketchToken': _token(sketch),
        'entities': [_serialize_entity(entity, '') for entity in entities],
        'compatible': [],
        'error': None,
    }
    if len(entities) > 3:
        result['error'] = 'Select 1, 2, or 3 sketch entities.'
        return result

    result['compatible'] = _compatible(entities)
    if not result['compatible']:
        result['error'] = 'No constraint fits this selection.'
    return result


def add_constraint(data):
    design = _design()
    payload = data or {}
    kind = payload.get('type', '')
    tokens = payload.get('entityTokens') or []
    if not kind or not tokens:
        raise ValueError('Choose a constraint and sketch geometry.')

    entities = [_find(design, token) for token in tokens]
    sketch = _parent_sketch(entities[0])
    if sketch is None:
        raise ValueError('Selected geometry is not on a sketch.')
    sketch_token = _token(sketch)
    for entity in entities[1:]:
        parent = _parent_sketch(entity)
        if parent is None or _token(parent) != sketch_token:
            raise ValueError('Selected geometry is on more than one sketch.')

    created = _apply(sketch.geometricConstraints, kind, entities)
    return {
        'sketchToken': sketch_token,
        'constraint': _serialize_constraint(sketch, _index_of_new(sketch, created), created),
    }


def _apply(geometric_constraints, kind, entities):
    try:
        if kind == 'horizontal':
            return geometric_constraints.addHorizontal(_line(entities[0]))
        if kind == 'vertical':
            return geometric_constraints.addVertical(_line(entities[0]))
        if kind == 'horizontalPoints':
            return geometric_constraints.addHorizontalPoints(_point(entities[0]), _point(entities[1]))
        if kind == 'verticalPoints':
            return geometric_constraints.addVerticalPoints(_point(entities[0]), _point(entities[1]))
        if kind == 'coincident':
            return geometric_constraints.addCoincident(_point(entities[0]), entities[1])
        if kind == 'collinear':
            return geometric_constraints.addCollinear(_line(entities[0]), _line(entities[1]))
        if kind == 'parallel':
            return geometric_constraints.addParallel(_line(entities[0]), _line(entities[1]))
        if kind == 'perpendicular':
            return geometric_constraints.addPerpendicular(_line(entities[0]), _line(entities[1]))
        if kind == 'equal':
            return geometric_constraints.addEqual(_curve(entities[0]), _curve(entities[1]))
        if kind == 'concentric':
            return geometric_constraints.addConcentric(_curve(entities[0]), _curve(entities[1]))
        if kind == 'tangent':
            return geometric_constraints.addTangent(_curve(entities[0]), _curve(entities[1]))
        if kind == 'smooth':
            return geometric_constraints.addSmooth(_curve(entities[0]), _curve(entities[1]))
        if kind == 'midpoint':
            return geometric_constraints.addMidPoint(_point(entities[0]), _curve(entities[1]))
        if kind == 'symmetry':
            return geometric_constraints.addSymmetry(entities[0], entities[1], _line(entities[2]))
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    raise ValueError(f'Unknown constraint type: {kind}')


def _compatible(entities):
    kinds = [_kind(entity) for entity in entities]
    count = len(entities)

    def option(type_id, label, ordered=None):
        chosen = entities if ordered is None else ordered
        return {
            'type': type_id,
            'label': label,
            'entityTokens': [_token(entity) for entity in chosen],
        }

    if count == 1 and kinds[0] == 'line':
        return [option('horizontal', 'Horizontal'), option('vertical', 'Vertical')]

    if count == 2 and kinds == ['line', 'line']:
        return [
            option('collinear', 'Collinear'),
            option('parallel', 'Parallel'),
            option('perpendicular', 'Perpendicular'),
            option('equal', 'Equal'),
        ]

    if count == 2 and kinds == ['point', 'point']:
        return [
            option('coincident', 'Coincident'),
            option('horizontalPoints', 'Horizontal points'),
            option('verticalPoints', 'Vertical points'),
        ]

    if count == 2 and 'point' in kinds and all(kind in ('point', 'line', 'circle', 'curve') for kind in kinds):
        point = entities[0] if kinds[0] == 'point' else entities[1]
        curve = entities[1] if kinds[0] == 'point' else entities[0]
        options = [option('coincident', 'Coincident', [point, curve])]
        if _kind(curve) in ('line', 'circle'):
            options.append(option('midpoint', 'Midpoint', [point, curve]))
        return options

    if count == 2 and kinds == ['circle', 'circle']:
        return [
            option('concentric', 'Concentric'),
            option('equal', 'Equal'),
            option('tangent', 'Tangent'),
        ]

    if count == 2 and all(kind in ('line', 'circle', 'curve') for kind in kinds):
        return [
            option('tangent', 'Tangent'),
            option('equal', 'Equal'),
            option('smooth', 'Smooth'),
        ]

    if count == 3:
        line_indexes = [index for index, kind in enumerate(kinds) if kind == 'line']
        if line_indexes:
            axis_index = line_indexes[-1]
            others = [entities[index] for index in range(3) if index != axis_index]
            return [option('symmetry', 'Symmetry', [others[0], others[1], entities[axis_index]])]

    return []


def _serialize_sketch(sketch):
    constraints = []
    try:
        geometric = sketch.geometricConstraints
        for index in range(geometric.count):
            try:
                constraints.append(_serialize_constraint(sketch, index, geometric.item(index)))
            except Exception:
                futil.log(f'Could not read constraint {index} on {_safe_name(sketch, "Sketch")}.')
    except Exception:
        futil.log(f'Could not read constraints on {_safe_name(sketch, "Sketch")}.')

    # Fusion draws a coincident glyph where curves share a sketch point, but that
    # point is not a CoincidentConstraint and is absent from geometricConstraints.
    constraints.extend(_shared_coincidents(sketch, len(constraints)))

    fully = False
    try:
        fully = bool(sketch.isFullyConstrained)
    except Exception:
        fully = False

    return {
        'name': _safe_name(sketch, 'Sketch'),
        'token': _token(sketch),
        'isFullyConstrained': fully,
        'constraints': constraints,
    }


def _shared_coincidents(sketch, start_index):
    rows = []
    try:
        points = sketch.sketchPoints
        count = points.count
    except Exception:
        return rows

    for index in range(count):
        try:
            point = points.item(index)
        except Exception:
            continue
        connected = _connected_entities(point)
        if len(connected) < 2:
            continue
        point_token = _token(point)
        if not point_token:
            continue
        entities = [_serialize_entity(point, 'point')]
        for entity in connected:
            entities.append(_serialize_entity(entity, 'entity'))
        sketch_token = _token(sketch)
        rows.append({
            'token': f'{sketch_token}::shared::{point_token}',
            'sketchToken': sketch_token,
            'index': start_index + len(rows),
            'type': 'coincident',
            'label': 'Coincident',
            'isDeletable': _detachable_curve(point, connected) is not None,
            'sharedPointToken': point_token,
            'entities': entities,
        })
    return rows


def _detach_shared_point(data):
    design = _design()
    point, connected = _shared_point_and_curves(design, data)
    curve = _detachable_curve(point, connected)
    if curve is None:
        raise ValueError('This constraint cannot be deleted.')
    sketch = _parent_sketch(point)
    sketch_token = _token(sketch) if sketch else data.get('sketchToken', '')
    try:
        detached = point.detach(curve)
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    if detached is False:
        raise ValueError('This constraint cannot be deleted.')
    return {'sketchToken': sketch_token, 'label': 'Coincident'}


def _shared_point_targets(design, data):
    point, connected = _shared_point_and_curves(design, data)
    return point, [point, *connected]


def _shared_point_and_curves(design, data):
    point = adsk.fusion.SketchPoint.cast(_find(design, data.get('sharedPointToken')))
    if not point:
        raise ValueError('That coincident constraint is no longer in the sketch.')
    connected = _connected_entities(point)
    if len(connected) < 2:
        raise ValueError('That coincident constraint is no longer in the sketch.')
    return point, connected


def _connected_entities(point):
    entities = []
    seen = set()
    try:
        connected = point.connectedEntities
        count = connected.count
    except Exception:
        return entities
    for index in range(count):
        try:
            entity = connected.item(index)
        except Exception:
            continue
        if entity is None:
            continue
        key = _token(entity) or id(entity)
        if key in seen:
            continue
        seen.add(key)
        entities.append(entity)
    return entities


def _detachable_curve(point, entities):
    # detach() only splits a curve that uses the point as an endpoint, and only
    # while another curve still shares that endpoint. A shared center cannot.
    curves = [entity for entity in entities if _uses_as_endpoint(entity, point)]
    if len(curves) < 2:
        return None
    return curves[-1]


def _uses_as_endpoint(entity, point):
    curve = adsk.fusion.SketchCurve.cast(entity)
    if not curve:
        return False
    for name in ('startSketchPoint', 'endSketchPoint'):
        other = _read_attr(curve, name)
        if other is not None and _same_entity(other, point):
            return True
    return False


def _same_entity(left, right):
    try:
        if left == right:
            return True
    except Exception:
        pass
    left_token = _token(left)
    right_token = _token(right)
    return bool(left_token) and left_token == right_token


def _serialize_constraint(sketch, index, constraint):
    type_id, label = _type_info(constraint)
    entities = _constraint_entities(constraint)
    sketch_token = _token(sketch)
    return {
        'token': f'{sketch_token}::{index}::{type_id}',
        'sketchToken': sketch_token,
        'index': index,
        'type': type_id,
        'label': label,
        'isDeletable': _is_deletable(constraint),
        'entities': entities,
    }


def _locate_constraint(design, data):
    """Find a geometric constraint without using its entityToken.

    Fusion's findEntityByToken resolves those tokens to a BaseVector, which
    has no deleteMe.
    """
    sketch_token = data.get('sketchToken') or ''
    index = _as_index(data.get('index'))
    type_id = data.get('type') or ''
    entity_tokens = [token for token in (data.get('entityTokens') or []) if token]
    if not sketch_token or index is None or not type_id:
        raise ValueError('Could not identify that constraint. Stop CONstrainer, run it again, and retry.')

    sketches = []
    if sketch_token:
        try:
            sketch = adsk.fusion.Sketch.cast(_find(design, sketch_token))
            if sketch:
                sketches.append(sketch)
        except ValueError:
            pass
    if not sketches:
        for comp in _components(design):
            for sketch_index in range(comp.sketches.count):
                sketches.append(comp.sketches.item(sketch_index))

    def matches(constraint):
        if type_id and _type_info(constraint)[0] != type_id:
            return False
        if not entity_tokens:
            return True
        found = {ref['token'] for ref in _constraint_entities(constraint) if ref['token']}
        return set(entity_tokens) == found or set(entity_tokens).issubset(found)

    if len(sketches) == 1 and index is not None:
        geometric = sketches[0].geometricConstraints
        if 0 <= index < geometric.count and matches(geometric.item(index)):
            return geometric.item(index)

    for sketch in sketches:
        geometric = sketch.geometricConstraints
        for item_index in range(geometric.count):
            candidate = geometric.item(item_index)
            if matches(candidate):
                return candidate
    raise ValueError('That constraint is no longer in the sketch.')


def _index_of_new(sketch, constraint):
    geometric = sketch.geometricConstraints
    target_type = _type_info(constraint)[0]
    target_tokens = {ref['token'] for ref in _constraint_entities(constraint) if ref['token']}
    for index in range(geometric.count - 1, -1, -1):
        item = geometric.item(index)
        if _type_info(item)[0] != target_type:
            continue
        tokens = {ref['token'] for ref in _constraint_entities(item) if ref['token']}
        if tokens == target_tokens:
            return index
    return max(geometric.count - 1, 0)


def _as_index(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _select_targets(targets):
    added = _try_select(targets, clear=True)
    if added == 0:
        raise ValueError('Fusion could not select that geometry.')
    return {'selected': added}


def _try_select(entities, clear):
    if clear:
        try:
            ui.activeSelections.clear()
        except Exception:
            pass
    added = 0
    for entity in entities or []:
        try:
            ui.activeSelections.add(entity)
            added += 1
        except Exception:
            futil.log(f'Could not select {_short_type(entity) or entity}')
    return added


def _live_entities(constraint):
    short = _short_type(constraint)
    roles = _ENTITY_ROLES.get(short, _GENERIC_ROLES)
    entities = []
    seen = set()
    for role in roles:
        entity = _read_attr(constraint, role)
        if entity is None:
            continue
        if adsk.fusion.SketchCurve.cast(entity) is None and adsk.fusion.SketchPoint.cast(entity) is None:
            continue
        key = _token(entity) or id(entity)
        if key in seen:
            continue
        seen.add(key)
        entities.append(entity)
    return entities


def _reveal_sketch(sketch):
    if sketch is None:
        return
    try:
        if not sketch.isLightBulbOn:
            sketch.isLightBulbOn = True
    except Exception:
        pass


def _highlight_with_set(entities):
    global _highlight_set
    try:
        highlight = ui.highlightSets.add()
    except Exception:
        return False
    added = 0
    for entity in entities:
        try:
            result = highlight.add(entity)
            if result is not False:
                added += 1
        except Exception:
            pass
    if added == 0:
        try:
            highlight.deleteMe()
        except Exception:
            pass
        return False
    _highlight_set = highlight
    return True


def _highlight_with_graphics(sketch, entities):
    global _highlight_graphics
    component = None
    try:
        component = sketch.parentComponent
    except Exception:
        component = None
    if component is None:
        return False
    try:
        group = component.customGraphicsGroups.add()
    except Exception:
        return False

    color = adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(20, 184, 199, 255))
    drawn = 0
    for entity in entities:
        try:
            if _draw_highlight(group, sketch, entity, color):
                drawn += 1
        except Exception:
            futil.log(f'Could not draw highlight for {_short_type(entity)}')
    if drawn == 0:
        try:
            group.deleteMe()
        except Exception:
            pass
        return False
    _highlight_graphics = group
    return True


def _draw_highlight(group, sketch, entity, color):
    point = adsk.fusion.SketchPoint.cast(entity)
    if point:
        center = _to_component(sketch, point.geometry)
        return _draw_cross(group, sketch, center, color)
    points = _sample_curve(sketch, entity)
    if len(points) < 2:
        return False
    _draw_strip(group, points, color)
    return True


def _sample_curve(sketch, entity):
    line = adsk.fusion.SketchLine.cast(entity)
    if line:
        return [
            _to_component(sketch, line.startSketchPoint.geometry),
            _to_component(sketch, line.endSketchPoint.geometry),
        ]

    curve = adsk.fusion.SketchCurve.cast(entity)
    if curve is None:
        return []
    try:
        geometry = curve.geometry
        evaluator = geometry.evaluator
    except Exception:
        return _end_points(sketch, curve)

    extents = evaluator.getParameterExtents()
    start_param, end_param = _extents(extents)
    if start_param is None:
        return _end_points(sketch, curve)

    count = 28
    points = []
    for step in range(count + 1):
        param = start_param + (end_param - start_param) * step / count
        point = _point_at(evaluator, param)
        if point is not None:
            points.append(_to_component(sketch, point))
    if adsk.fusion.SketchCircle.cast(entity) and len(points) > 2:
        points.append(points[0])
    return points


def _end_points(sketch, curve):
    points = []
    for name in ('startSketchPoint', 'endSketchPoint'):
        try:
            point = getattr(curve, name).geometry
        except Exception:
            continue
        points.append(_to_component(sketch, point))
    return points


def _extents(extents):
    if isinstance(extents, tuple):
        if len(extents) >= 3 and extents[0]:
            return extents[1], extents[2]
        if len(extents) == 2:
            return extents[0], extents[1]
    return None, None


def _point_at(evaluator, param):
    result = evaluator.getPointAtParameter(param)
    if isinstance(result, tuple):
        if len(result) >= 2 and result[0]:
            return result[1]
        return None
    return result


def _draw_cross(group, sketch, center, color):
    size = _marker_size(sketch)
    x_axis, y_axis = _sketch_axes(sketch, size)
    _draw_strip(group, [_shift(center, x_axis, -1), _shift(center, x_axis, 1)], color)
    _draw_strip(group, [_shift(center, y_axis, -1), _shift(center, y_axis, 1)], color)
    return True


def _draw_strip(group, points, color):
    flat = []
    for point in points:
        flat.extend((point.x, point.y, point.z))
    coordinates = adsk.fusion.CustomGraphicsCoordinates.create(flat)
    try:
        lines = group.addLines(coordinates, [], True)
    except TypeError:
        lines = group.addLines(coordinates, [], True, [])
    lines.color = color
    try:
        lines.weight = 4
    except Exception:
        pass
    try:
        lines.depthPriority = 2
    except Exception:
        pass


def _shift(origin, direction, scale):
    return adsk.core.Point3D.create(
        origin.x + direction.x * scale,
        origin.y + direction.y * scale,
        origin.z + direction.z * scale,
    )


def _sketch_axes(sketch, length):
    origin = adsk.core.Point3D.create(0, 0, 0)
    x_point = adsk.core.Point3D.create(length, 0, 0)
    y_point = adsk.core.Point3D.create(0, length, 0)
    origin.transformBy(sketch.transform)
    x_point.transformBy(sketch.transform)
    y_point.transformBy(sketch.transform)
    x_axis = adsk.core.Vector3D.create(x_point.x - origin.x, x_point.y - origin.y, x_point.z - origin.z)
    y_axis = adsk.core.Vector3D.create(y_point.x - origin.x, y_point.y - origin.y, y_point.z - origin.z)
    return x_axis, y_axis


def _marker_size(sketch):
    try:
        box = sketch.boundingBox
        diagonal = box.minPoint.distanceTo(box.maxPoint)
        if diagonal > 0:
            return max(diagonal * 0.02, 0.05)
    except Exception:
        pass
    return 0.2


def _to_component(sketch, point):
    copied = point.copy()
    copied.transformBy(sketch.transform)
    return copied


def _constraint_entities(constraint):
    short = _short_type(constraint)
    roles = _ENTITY_ROLES.get(short, _GENERIC_ROLES)
    refs = []
    for role in roles:
        entity = _read_attr(constraint, role)
        if entity is None or not _token(entity):
            continue
        refs.append(_serialize_entity(entity, role))
    return refs


def _serialize_entity(entity, role):
    return {
        'role': role,
        'kind': _kind(entity) or 'entity',
        'label': _entity_label(entity),
        'token': _token(entity),
    }


def _entity_label(entity):
    if adsk.fusion.SketchLine.cast(entity):
        return 'Line'
    if adsk.fusion.SketchPoint.cast(entity):
        return 'Point'
    if adsk.fusion.SketchArc.cast(entity):
        return 'Arc'
    if adsk.fusion.SketchCircle.cast(entity):
        return 'Circle'
    if _cast(entity, 'SketchEllipse') or _cast(entity, 'SketchEllipticalArc'):
        return 'Ellipse'
    if _cast(entity, 'SketchFittedSpline') or _cast(entity, 'SketchFixedSpline'):
        return 'Spline'
    if _cast(entity, 'SketchConicCurve'):
        return 'Conic'
    if adsk.fusion.SketchCurve.cast(entity):
        return 'Curve'
    return _short_type(entity) or 'Entity'


def _kind(entity):
    if entity is None:
        return None
    if adsk.fusion.SketchLine.cast(entity):
        return 'line'
    if adsk.fusion.SketchPoint.cast(entity):
        return 'point'
    if adsk.fusion.SketchArc.cast(entity) or adsk.fusion.SketchCircle.cast(entity):
        return 'circle'
    if adsk.fusion.SketchCurve.cast(entity):
        return 'curve'
    return None


def _type_info(constraint):
    short = _short_type(constraint)
    if short in _TYPE_INFO:
        return _TYPE_INFO[short]
    label = short.replace('Constraint', '') or 'Constraint'
    return (label[:1].lower() + label[1:] if label else 'constraint', label)


def _is_constraint(entity):
    return 'Constraint' in _short_type(entity)


def _is_deletable(constraint):
    try:
        return bool(constraint.isDeletable)
    except Exception:
        return True


def _parent_sketch(entity):
    try:
        return entity.parentSketch
    except Exception:
        return None


def _line(entity):
    line = adsk.fusion.SketchLine.cast(entity)
    if not line:
        raise ValueError('Expected a sketch line.')
    return line


def _point(entity):
    point = adsk.fusion.SketchPoint.cast(entity)
    if not point:
        raise ValueError('Expected a sketch point.')
    return point


def _curve(entity):
    curve = adsk.fusion.SketchCurve.cast(entity)
    if not curve:
        raise ValueError('Expected a sketch curve.')
    return curve


def _components(design):
    components = design.allComponents
    for index in range(components.count):
        yield components.item(index)


def _design():
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise RuntimeError('No active design.')
    return design


def _find(design, token):
    if not token:
        raise ValueError('Missing item id.')
    try:
        found = design.findEntityByToken(token)
    except Exception as exc:
        raise ValueError('That item is no longer in the design.') from exc
    found = _unwrap(found)
    if found is None:
        raise ValueError('That item is no longer in the design.')
    return found


def _unwrap(found):
    """findEntityByToken returns a SWIG vector in Python, not an adsk object."""
    if found is None:
        return None
    try:
        if found.objectType == 'adsk::core::ObjectCollection':
            return found.item(0) if found.count > 0 else None
        return found
    except Exception:
        pass
    try:
        items = [item for item in list(found) if item is not None]
    except Exception:
        return None
    return items[0] if items else None


def _token(entity):
    if entity is None:
        return ''
    try:
        return entity.entityToken or ''
    except Exception:
        return ''


def _safe_name(entity, fallback):
    try:
        name = entity.name
    except Exception:
        return fallback
    return name or fallback


def _short_type(entity):
    try:
        return entity.objectType.split('::')[-1]
    except Exception:
        return ''


def _read_attr(obj, name):
    try:
        value = getattr(obj, name)
    except Exception:
        return None
    if value is None or callable(value):
        return None
    return value


def _cast(entity, class_name):
    cls = getattr(adsk.fusion, class_name, None)
    if cls is None:
        return None
    try:
        return cls.cast(entity)
    except Exception:
        return None
