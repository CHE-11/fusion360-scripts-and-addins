"""List and edit assembly constraints made with Assemble > Constrain Components.

Fusion exposes these through a preview API (AssemblyConstraint, July 2025), so every
call is guarded and the tab reports when the running Fusion does not support it.
"""

import re
from contextlib import contextmanager

import adsk.core
import adsk.fusion

from ...lib import fusionAddInUtils as futil
from . import design_utils as du

app = adsk.core.Application.get()
ui = app.userInterface

_ASSEMBLY_CONSTRAINT = getattr(adsk.fusion, 'AssemblyConstraint', None)
_highlight_token = None
_pinned_entities = []
_saved_selection = None
_pinned = False
_suspend_depth = 0
_geometry_key = None
_geometry_by_constraint = {}


def is_supported():
    return _ASSEMBLY_CONSTRAINT is not None


def empty_selection():
    return {'focus': None, 'direct': [], 'component': []}


def list_constraints():
    design = du.design()
    intent = du.intent_name(design)
    if intent not in ('assembly', 'hybrid'):
        return {'constraints': [], 'supported': is_supported(), 'allowed': False}
    if not is_supported():
        return {'constraints': [], 'supported': False, 'allowed': True}
    root_token = du.token(design.rootComponent)
    entries = list(_all_constraints(design))
    _geometry(design, [entry[0] for entry in entries])
    constraints = [_serialize(*entry) for entry in entries]
    constraints.sort(key=lambda item: (
        0 if item['componentToken'] == root_token else 1,
        item['component'].lower(),
        _natural_key(item['name']),
    ))
    return {'constraints': constraints, 'supported': True, 'allowed': True}


def _natural_key(name):
    """Sort Constraint 2 before Constraint 10, and Constraint 1 (1) between 1 and 2."""
    return [(0, int(part), '') if part.isdigit() else (1, 0, part) for part in re.findall(r'\d+|[^\W\d_]+', name.lower())]


def read_selection():
    try:
        design = du.require_assembly()
    except (RuntimeError, ValueError):
        return empty_selection()
    if not is_supported():
        return empty_selection()
    try:
        if ui.activeSelections.count == 0:
            return empty_selection()
    except Exception:
        return empty_selection()
    _geometry(design, [entry[0] for entry in _all_constraints(design)])
    try:
        selections = ui.activeSelections
        count = selections.count
    except Exception:
        return empty_selection()

    for index in range(count):
        try:
            entity = selections.item(index).entity
        except Exception:
            continue
        if not du.focus_kind(entity):
            continue
        occurrence = du.occurrence_of(entity)
        direct, component = _related(design, entity, occurrence)
        return {'focus': du.describe_focus(entity, occurrence), 'direct': direct, 'component': component}
    return empty_selection()


def rename(data):
    design = du.require_assembly()
    payload = data or {}
    constraint = _find_constraint(design, payload.get('token', ''))
    name = str(payload.get('name', '') or '').strip()
    if not name:
        raise ValueError('Name is required.')
    old_key = _constraint_key(constraint)
    _apply(lambda: setattr(constraint, 'name', name))
    geometry = _geometry_by_constraint.pop(old_key, None)
    if geometry is not None:
        _geometry_by_constraint[_constraint_key(constraint)] = geometry
    return _serialize_found(constraint)


def set_suppressed(data):
    design = du.require_assembly()
    payload = data or {}
    constraint = _find_constraint(design, payload.get('token', ''))
    _apply(lambda: setattr(constraint, 'isSuppressed', bool(payload.get('suppressed'))))
    return _serialize_found(constraint)


def set_visible(data):
    design = du.require_assembly()
    payload = data or {}
    constraint = _find_constraint(design, payload.get('token', ''))
    _apply(lambda: setattr(constraint, 'isLightBulbOn', bool(payload.get('visible'))))
    return _serialize_found(constraint)


def delete(data):
    design = du.require_assembly()
    constraint = _find_constraint(design, (data or {}).get('token', ''))
    name = du.safe_name(constraint, 'Constraint')
    _apply(constraint.deleteMe)
    return {'name': name}


def selection_suspended():
    """True while the palette owns the selection, so it does not refocus on its own highlight."""
    if _suspend_depth > 0:
        return True
    if _highlight_token is None:
        return False
    if not _pinned:
        return True
    return _selection_is(_pinned_entities)


def highlight(data):
    """Select the constraint's geometry briefly so Fusion highlights it in the canvas.

    Fusion rejects AssemblyConstraint and its TimelineObject in activeSelections, so the
    faces and edges it relates stand in. clear_highlight restores the previous selection.
    """
    global _highlight_token, _pinned
    design = du.require_assembly()
    token = str((data or {}).get('token', '') or '')
    constraint = _find_constraint(design, token)
    with _selection_suspended():
        if _saved_selection is None:
            _remember_selection()
        _pinned = False
        _highlight_token = token
        geometry = _select_geometry(design, constraint)
        if geometry == 0:
            _restore_selection()
            _highlight_token = None
            return {'highlighted': 0, 'selected': False, 'geometry': 0}
    return {'highlighted': 1, 'selected': True, 'geometry': geometry}


def clear_highlight(data=None):
    """Drop a hover highlight and restore the selection from before it.

    Calling this with no argument, as document changes and add-in shutdown do, forgets the
    saved selection instead of writing it into a different document. A pinned highlight from
    the locate button stays until another constraint is highlighted or this is forced.
    """
    global _highlight_token, _pinned, _saved_selection, _pinned_entities
    force = data is None or bool((data or {}).get('force'))
    token = str((data or {}).get('token', '') or '') if data is not None else ''
    if not force and _pinned:
        return {'cleared': False}
    if not force and token and _highlight_token and token != _highlight_token:
        return {'cleared': False}
    with _selection_suspended():
        if force:
            _saved_selection = None
        else:
            _restore_selection()
        _highlight_token = None
        _pinned = False
        _pinned_entities = []
    return {'cleared': True}


def select(data):
    """Leave the constraint's geometry selected so it stays highlighted in the canvas."""
    global _highlight_token, _pinned, _saved_selection, _pinned_entities
    design = du.require_assembly()
    token = str((data or {}).get('token', '') or '')
    constraint = _find_constraint(design, token)
    _saved_selection = None
    _pinned = True
    _highlight_token = token
    with _selection_suspended():
        geometry = _select_geometry(design, constraint)
    if geometry == 0:
        _pinned = False
        _highlight_token = None
        _pinned_entities = []
        raise ValueError('Fusion could not select the geometry for that constraint.')
    _pinned_entities = _current_selection()
    return {'selected': 1, 'geometry': geometry}


def _all_constraints(design):
    for comp in du.components(design):
        collection = du.read_attr(comp, 'assemblyConstraints')
        if collection is None:
            continue
        component_name = du.safe_name(comp, 'Component')
        component_token = du.token(comp)
        try:
            count = collection.count
        except Exception:
            continue
        for index in range(count):
            try:
                constraint = collection.item(index)
            except Exception:
                continue
            if constraint is not None:
                yield constraint, component_name, component_token


def _serialize_found(constraint):
    component = du.read_attr(constraint, 'parentComponent')
    component_name = du.safe_name(component, 'Component') if component else 'Component'
    component_token = du.token(component) if component else ''
    return _serialize(constraint, component_name, component_token)


def _serialize(constraint, component_name, component_token):
    geometry = _geometry_by_constraint.get(_constraint_key(constraint)) or []
    relationships = [
        _serialize_relationship(rel, index, geometry[index] if index < len(geometry) else [None, None])
        for index, rel in enumerate(du.relationships(constraint))
    ]
    side_one, side_two = _sides(geometry)
    return {
        'token': du.token(constraint),
        'name': du.safe_name(constraint, 'Constraint'),
        'typeLabel': _type_label(relationships),
        'sideOne': side_one,
        'sideTwo': side_two,
        'isSuppressed': du.is_suppressed(constraint),
        'isLightBulbOn': du.is_light_bulb_on(constraint),
        'isVisible': du.is_visible(constraint),
        'health': _health(constraint),
        'message': du.read_attr(constraint, 'errorOrWarningMessage') or '',
        'relationships': relationships,
        'component': component_name,
        'componentToken': component_token,
    }


def _serialize_relationship(relationship, index, entities):
    parameter = du.read_attr(relationship, 'offsetOrAngle')
    is_mate = du.read_attr(relationship, 'isMate')
    one, two = entities
    return {
        'index': index,
        'name': du.read_attr(relationship, 'name') or f'Relationship {index + 1}',
        'type': 'angle' if is_mate is False else 'mate',
        'isFlipped': bool(du.read_attr(relationship, 'isFlipped')),
        'isSuppressed': bool(du.read_attr(relationship, 'isSuppressed')),
        'expression': du.expression(parameter),
        'parameterName': du.safe_name(parameter, '') if parameter else '',
        'entityOne': one['label'] if one else 'Geometry',
        'entityTwo': two['label'] if two else 'Geometry',
        'entityOneGeometry': one['geometry'] if one else 'Geometry',
        'entityTwoGeometry': two['geometry'] if two else 'Geometry',
        'entityOneComponent': one['side'] if one else '',
        'entityTwoComponent': two['side'] if two else '',
    }


def _type_label(relationships):
    kinds = {item['type'] for item in relationships}
    if kinds == {'angle'}:
        return 'Angle'
    if 'angle' in kinds:
        return 'Mate + angle'
    return 'Mate'


def _entity_label(entity):
    if entity is None:
        return 'Geometry'
    label = du.geometry_label(entity)
    occurrence = du.occurrence_of(entity)
    return f'{label} · {du.safe_name(occurrence, "Component")}' if occurrence else label


def _sides(geometry):
    sides = []
    for pair in geometry:
        for info in pair:
            if info is None:
                continue
            label = info['side']
            if label not in sides:
                sides.append(label)
    while len(sides) < 2:
        sides.append('Root')
    return sides[0], sides[1]


def _health(constraint):
    state = du.read_attr(constraint, 'healthState')
    states = adsk.fusion.FeatureHealthStates
    if state == states.ErrorFeatureHealthState:
        return 'error'
    if state == states.WarningFeatureHealthState:
        return 'warning'
    return 'ok'


def _entity_infos(constraint):
    geometry = _geometry_by_constraint.get(_constraint_key(constraint)) or []
    return [info for pair in geometry for info in pair if info is not None]


def _related(design, entity, occurrence):
    body = adsk.fusion.BRepBody.cast(entity)
    is_component = adsk.fusion.Occurrence.cast(entity) is not None
    target = du.occurrence_path(occurrence)
    entries = list(_all_constraints(design))
    _geometry(design, [entry[0] for entry in entries])
    direct = []
    component = []
    cache = {}
    for constraint, component_name, component_token in entries:
        infos = _entity_infos(constraint)
        owner = du.read_attr(constraint, 'parentComponent')
        uses = False
        touches = False
        for context in du.owner_occurrences(design, owner, cache):
            prefix = du.occurrence_path(context)
            touches = touches or any(du.path_within(du.join_path(info['path'], prefix), target) for info in infos)
            if is_component:
                uses = touches
            else:
                uses = any(_info_matches(info, prefix, entity, body) for info in infos)
            if uses:
                break
        if uses:
            direct.append(_serialize(constraint, component_name, component_token))
        elif touches:
            component.append(_serialize(constraint, component_name, component_token))
    direct.sort(key=lambda item: _natural_key(item['name']))
    component.sort(key=lambda item: _natural_key(item['name']))
    return direct, component


def _info_matches(info, prefix, entity, body):
    """Match captured geometry against the selection, by native object and occurrence path."""
    candidate = info['entity']
    target = entity
    if body is not None:
        candidate = du.read_attr(candidate, 'body')
        target = body
    if candidate is None or target is None:
        return False
    if du.same(candidate, target):
        return True
    native_candidate = du.read_attr(candidate, 'nativeObject') or candidate
    native_target = du.read_attr(target, 'nativeObject') or target
    try:
        if not native_candidate == native_target:
            return False
    except Exception:
        return False
    return du.join_path(info['path'], prefix) == du.occurrence_path(du.occurrence_of(target))


def _constraint_key(constraint):
    owner = du.read_attr(constraint, 'parentComponent')
    return (du.safe_name(owner, ''), du.safe_name(constraint, ''))


def _geometry(design, constraints):
    """Relationship geometry for each constraint, read once per timeline state.

    Fusion raises on GeometricRelationship.entityOne and entityTwo unless the timeline
    marker sits just before the constraint, so those are read with the timeline rolled back.
    Entity tokens are not stable, so the cache is keyed on names and the timeline length.
    """
    global _geometry_key, _geometry_by_constraint
    timeline = du.read_attr(design, 'timeline')
    state = (
        du.safe_name(du.read_attr(design, 'parentDocument'), ''),
        du.read_attr(timeline, 'count') if timeline is not None else None,
    )
    key = (state, tuple(_constraint_key(constraint) for constraint in constraints))
    if key == _geometry_key:
        return _geometry_by_constraint
    previous = _geometry_by_constraint if _geometry_key and _geometry_key[0] == state else {}
    captured = {}
    pending = []
    for constraint in constraints:
        reused = previous.get(_constraint_key(constraint))
        if reused is not None:
            captured[_constraint_key(constraint)] = reused
            continue
        geometry = _capture(constraint)
        if geometry is None:
            pending.append(constraint)
        else:
            captured[_constraint_key(constraint)] = geometry
    if pending:
        _capture_rolled_back(design, timeline, pending, captured)
    _geometry_key = key
    _geometry_by_constraint = captured
    return captured


def _capture(constraint):
    try:
        collection = constraint.geometricRelationships
        relationships = [collection.item(index) for index in range(collection.count)]
        return [[_entity_info(rel.entityOne), _entity_info(rel.entityTwo)] for rel in relationships]
    except Exception:
        return None


def _entity_info(entity):
    if entity is None:
        return None
    occurrence = du.occurrence_of(entity)
    return {
        'entity': entity,
        'token': du.token(entity),
        'label': _entity_label(entity),
        'geometry': du.geometry_label(entity),
        'side': du.side_label(occurrence),
        'path': du.occurrence_path(occurrence),
    }


def _capture_rolled_back(design, timeline, pending, captured):
    if timeline is None:
        return
    try:
        marker = timeline.markerPosition
        at_end = marker >= timeline.count
    except Exception:
        return
    ordered = sorted(pending, key=lambda item: du.read_attr(du.read_attr(item, 'timelineObject'), 'index') or 0)
    selected = _current_selection()
    rolled = []
    with _selection_suspended():
        try:
            for constraint in ordered:
                timeline_object = du.read_attr(constraint, 'timelineObject')
                if timeline_object is None:
                    continue
                try:
                    timeline_object.rollTo(True)
                except Exception:
                    futil.log(f"Could not roll the timeline to {du.safe_name(constraint, 'a constraint')}.")
                    continue
                geometry = _capture(constraint)
                if geometry is not None:
                    key = _constraint_key(constraint)
                    captured[key] = geometry
                    rolled.append(key)
        finally:
            try:
                if at_end:
                    timeline.moveToEnd()
                else:
                    timeline.markerPosition = marker
            except Exception:
                futil.log('Could not restore the timeline marker after reading assembly constraints.')
            _select_entities(selected)
    for key in rolled:
        for pair in captured[key]:
            for info in pair:
                if info is not None:
                    _revive(design, info)


def _revive(design, info):
    """Swap geometry read while rolled back for the live entity at the current marker."""
    matches = du.find_all(design, info['token'])
    for candidate in matches:
        if du.occurrence_path(du.occurrence_of(candidate)) == info['path']:
            info['entity'] = candidate
            return
    if matches:
        info['entity'] = matches[0]


def _find_constraint(design, token):
    if not is_supported():
        raise ValueError('This version of Fusion does not expose assembly constraints to add-ins.')
    if not token:
        raise ValueError('Missing item id.')
    for found in du.find_all(design, token):
        constraint = _ASSEMBLY_CONSTRAINT.cast(found)
        if constraint:
            return constraint
    for constraint, _name, _component_token in _all_constraints(design):
        if du.token(constraint) == token:
            return constraint
    raise ValueError('That assembly constraint is no longer in the design.')


@contextmanager
def _selection_suspended():
    global _suspend_depth
    _suspend_depth += 1
    try:
        yield
    finally:
        _suspend_depth -= 1


def _remember_selection():
    global _saved_selection
    _saved_selection = _current_selection()


def _restore_selection():
    global _saved_selection
    saved = _saved_selection
    _saved_selection = None
    if saved is None:
        return
    _select_entities(saved)


def _current_selection():
    captured = []
    try:
        selections = ui.activeSelections
        for index in range(selections.count):
            try:
                captured.append(selections.item(index).entity)
            except Exception:
                continue
    except Exception:
        return []
    return captured


def _select_entities(entities):
    try:
        ui.activeSelections.clear()
    except Exception:
        return
    for entity in entities:
        if entity is None:
            continue
        try:
            ui.activeSelections.add(entity)
        except Exception:
            pass


def _select_geometry(design, constraint):
    """Replace the selection with the constraint's geometry. Returns how many Fusion accepted."""
    try:
        selections = ui.activeSelections
        selections.clear()
    except Exception:
        return 0
    added = 0
    for entity in _placed_entities(design, constraint):
        try:
            if selections.add(entity) is not False:
                added += 1
        except Exception:
            pass
    return added


def _placed_entities(design, constraint):
    """Constraint geometry as root-level proxies, which is what activeSelections accepts."""
    infos = [info for info in _entity_infos(constraint) if info['entity'] is not None]
    owner = du.read_attr(constraint, 'parentComponent')
    placed = []
    by_path = None
    for context in du.owner_occurrences(design, owner, {}):
        prefix = du.occurrence_path(context)
        for info in infos:
            if not prefix:
                placed.append(info['entity'])
                continue
            if by_path is None:
                by_path = _occurrences_by_path(design)
            occurrence = by_path.get(du.join_path(info['path'], prefix))
            if occurrence is None:
                continue
            native = du.read_attr(info['entity'], 'nativeObject') or info['entity']
            placed.append(du.proxy(native, occurrence))
    return placed


def _occurrences_by_path(design):
    found = {}
    try:
        occurrences = design.rootComponent.allOccurrences
        for index in range(occurrences.count):
            occurrence = occurrences.item(index)
            found[du.occurrence_path(occurrence)] = occurrence
    except Exception:
        pass
    return found


def _selection_is(entities):
    current = _current_selection()
    if not entities or len(current) != len(entities):
        return False
    return all(any(du.same(item, entity) for entity in entities) for item in current)


def _apply(action):
    try:
        action()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(str(exc)) from exc
