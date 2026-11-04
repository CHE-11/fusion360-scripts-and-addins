"""User parameters, attributes, and rebuilds for threads and inserts.

Clearance and hole diameter are Fusion user parameters. A nudge edits the
parameter and, for a thread, rebuilds the sweep so the model matches.
Insert pockets are dimensioned to their parameters, so a nudge recomputes
in place.
"""

from __future__ import annotations

import math
import re

import adsk.core
import adsk.fusion

from . import geometry
from . import profile as thread_profile
from . import standards

_app = adsk.core.Application.get()

_THREAD_KEYS = (
    'gender', 'build', 'family', 'size', 'mating', 'right', 'lead',
    'face', 'body', 'radius', 'label', 'prefix', 'id', 'kind',
)
_INSERT_KEYS = (
    'size', 'label', 'prefix', 'id', 'kind', 'face', 'body', 'center', 'planar', 'cylinder',
)


def _design():
    design = adsk.fusion.Design.cast(_app.activeProduct)
    if not design:
        raise geometry.GeometryError('Open a Fusion design first.')
    if design.designType != adsk.fusion.DesignTypes.ParametricDesignType:
        raise geometry.GeometryError('Switch the design to Parametric Modeling so thread sizes stay editable.')
    return design


def _expr_mm(value):
    return f'{float(value):.4f} mm'


def _expr_deg(value):
    return f'{float(value):.4f} deg'


def _ensure_param(design, name, expression, unit, comment):
    existing = design.userParameters.itemByName(name)
    if existing:
        existing.expression = expression
        return existing
    return design.userParameters.add(name, adsk.core.ValueInput.createByString(expression), unit, comment)


def _param_value_mm(design, name):
    parameter = design.userParameters.itemByName(name)
    if not parameter:
        return None
    # Length parameters report centimeters.
    return parameter.value * 10.0


def _param_value_deg(design, name):
    parameter = design.userParameters.itemByName(name)
    if not parameter:
        return None
    return math.degrees(parameter.value)


def _delete_param(design, name):
    parameter = design.userParameters.itemByName(name)
    if parameter:
        try:
            parameter.deleteMe()
        except Exception:
            pass


def ensure_printer(design, nozzle_mm, layer_mm):
    _ensure_param(design, 'thread_nozzle', _expr_mm(nozzle_mm), 'mm', 'Threader nozzle diameter')
    _ensure_param(design, 'thread_layer', _expr_mm(layer_mm), 'mm', 'Threader layer height')


def _next_prefix(design, letter):
    highest = 0
    pattern = re.compile(rf'^{letter}(\d+)_')
    for parameter in design.userParameters:
        match = pattern.match(parameter.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return f'{letter}{highest + 1}'


def _write_thread_params(design, prefix, spec):
    comment = f'Threader {prefix}'
    _ensure_param(design, f'{prefix}_clear', _expr_mm(spec['clearance_mm']), 'mm', comment)
    _ensure_param(design, f'{prefix}_pitch', _expr_mm(spec['pitch_mm']), 'mm', comment)
    _ensure_param(design, f'{prefix}_length', _expr_mm(spec['length_mm']), 'mm', comment)
    _ensure_param(design, f'{prefix}_offset', _expr_mm(spec.get('inset_mm', spec['offset_mm'])), 'mm', comment)
    _ensure_param(design, f'{prefix}_end', _expr_mm(spec.get('end_mm', 0)), 'mm', comment)
    _ensure_param(design, f'{prefix}_lead', _expr_mm(spec['lead_mm']), 'mm', comment)
    _ensure_param(design, f'{prefix}_chamfer', _expr_mm(spec.get('chamfer_mm', 0)), 'mm', comment)
    _ensure_param(design, f'{prefix}_flank', _expr_deg(spec['flank_deg']), 'deg', comment)


def _write_insert_params(design, prefix, hole_mm, depth_mm, chamfer_mm):
    comment = f'Threader {prefix}'
    _ensure_param(design, f'{prefix}_dia', _expr_mm(hole_mm), 'mm', comment)
    _ensure_param(design, f'{prefix}_depth', _expr_mm(depth_mm), 'mm', comment)
    _ensure_param(design, f'{prefix}_chamfer', _expr_mm(chamfer_mm), 'mm', comment)


def _delete_thread_params(design, prefix):
    for suffix in ('clear', 'pitch', 'length', 'offset', 'end', 'lead', 'chamfer', 'flank'):
        _delete_param(design, f'{prefix}_{suffix}')


def _delete_insert_params(design, prefix):
    for suffix in ('dia', 'depth', 'chamfer'):
        _delete_param(design, f'{prefix}_{suffix}')


def _attr_map(entity):
    values = {}
    attributes = entity.attributes
    for index in range(attributes.count):
        item = attributes.item(index)
        if item.groupName == geometry.ATTR_GROUP:
            values[item.name] = item.value
    return values


def _primary_features(design):
    found = []
    attributes = design.findAttributes(geometry.ATTR_GROUP, 'primary')
    if not attributes:
        return found
    for attribute in attributes:
        if attribute.value != '1':
            continue
        parent = attribute.parent
        if parent:
            found.append(parent)
    return found


def _thread_row(design, feature):
    fields = _attr_map(feature)
    prefix = fields.get('prefix') or fields.get('id')
    if not prefix:
        return None
    return {
        'id': prefix,
        'kind': 'thread',
        'label': fields.get('label') or prefix,
        'gender': fields.get('gender') or 'male',
        'build': fields.get('build') or 'outset',
        'family': fields.get('family') or 'printable',
        'size': fields.get('size') or 'Custom',
        'mating': fields.get('mating') or 'plastic',
        'rightHand': fields.get('right', '1') == '1',
        'lead': fields.get('lead', '1') == '1',
        'chamfer': fields.get('chamfer', '0') == '1',
        'clearanceMm': _round(_param_value_mm(design, f'{prefix}_clear')),
        'pitchMm': _round(_param_value_mm(design, f'{prefix}_pitch')),
        'lengthMm': _round(_param_value_mm(design, f'{prefix}_length')),
        'offsetMm': _round(_param_value_mm(design, f'{prefix}_offset')),
        'leadMm': _round(_param_value_mm(design, f'{prefix}_lead')),
        'chamferMm': _round(_param_value_mm(design, f'{prefix}_chamfer')),
        'flankDeg': _round(_param_value_deg(design, f'{prefix}_flank')),
    }


def _insert_row(design, feature):
    fields = _attr_map(feature)
    prefix = fields.get('prefix') or fields.get('id')
    if not prefix:
        return None
    return {
        'id': prefix,
        'kind': 'insert',
        'label': fields.get('label') or prefix,
        'size': fields.get('size') or 'Custom',
        'holeMm': _round(_param_value_mm(design, f'{prefix}_dia')),
        'depthMm': _round(_param_value_mm(design, f'{prefix}_depth')),
        'chamferMm': _round(_param_value_mm(design, f'{prefix}_chamfer')),
    }


def list_features():
    design = _design()
    rows = []
    for feature in _primary_features(design):
        fields = _attr_map(feature)
        kind = fields.get('kind')
        row = _thread_row(design, feature) if kind == 'thread' else _insert_row(design, feature) if kind == 'insert' else None
        if row:
            rows.append(row)
    rows.sort(key=lambda item: item['id'])
    return {'features': rows}


def _face_payload(data, frame):
    payload = dict(data or {})
    payload['face_radius_mm'] = frame['radius_mm']
    payload['face_length_mm'] = frame['length_mm']
    payload['axis_vertical'] = frame['axis_vertical']
    if not payload.get('gender'):
        payload['gender'] = frame['gender']
    return payload


def _printer_numbers(data, design):
    nozzle = data.get('nozzleMm', data.get('nozzle_mm'))
    layer = data.get('layerMm', data.get('layer_mm'))
    if nozzle in (None, ''):
        nozzle = _param_value_mm(design, 'thread_nozzle') or standards.catalog()['defaultNozzleMm']
    if layer in (None, ''):
        layer = _param_value_mm(design, 'thread_layer') or standards.catalog()['defaultLayerMm']
    return float(nozzle), float(layer)


def preview_thread(data):
    payload = dict(data or {})
    nozzle = payload.get('nozzleMm', payload.get('nozzle_mm', 0.4))
    layer = payload.get('layerMm', payload.get('layer_mm', 0.2))
    payload['nozzle_mm'] = nozzle
    payload['layer_mm'] = layer
    payload['face_radius_mm'] = payload.get('face_radius_mm', payload.get('faceRadiusMm'))
    payload['face_length_mm'] = payload.get('face_length_mm', payload.get('faceLengthMm'))
    payload['pitch_mm'] = payload.get('pitch_mm', payload.get('pitchMm'))
    payload['clearance_mm'] = payload.get('clearance_mm', payload.get('clearanceMm'))
    payload['flank_deg'] = payload.get('flank_deg', payload.get('flankDeg'))
    payload['length_mm'] = payload.get('length_mm', payload.get('lengthMm'))
    payload['offset_mm'] = payload.get('offset_mm', payload.get('offsetMm'))
    payload['end_mm'] = payload.get('end_mm', payload.get('endOffsetMm'))
    payload['chamfer_mm'] = payload.get('chamfer_mm', payload.get('chamferMm'))
    payload['axis_vertical'] = payload.get('axis_vertical', payload.get('axisVertical', True))
    if 'right_hand' not in payload and 'rightHand' in payload:
        payload['right_hand'] = payload['rightHand']
    spec = thread_profile.resolve(payload)
    return thread_profile.client_view(spec)


def create_thread(data):
    design = _design()
    data = dict(data or {})
    face = geometry.resolve_cylinder_face(data.get('faceToken') or data.get('token'))
    frame = geometry.inspect_cylinder(face)
    nozzle, layer = _printer_numbers(data, design)
    ensure_printer(design, nozzle, layer)
    payload = _camel_to_profile(data)
    payload['nozzle_mm'] = nozzle
    payload['layer_mm'] = layer
    spec = thread_profile.resolve(_face_payload(payload, frame))
    prefix = _next_prefix(design, 't')
    _write_thread_params(design, prefix, spec)
    try:
        _feature, warnings = geometry.build_thread(frame, spec, prefix)
    except Exception:
        _delete_thread_params(design, prefix)
        geometry.delete_named(frame['component'], prefix)
        raise
    row = _thread_row(design, _feature)
    return {'feature': row, 'preview': thread_profile.client_view(spec), 'warnings': warnings}


def _camel_to_profile(data):
    payload = dict(data)
    mapping = {
        'pitchMm': 'pitch_mm',
        'clearanceMm': 'clearance_mm',
        'flankDeg': 'flank_deg',
        'lengthMm': 'length_mm',
        'offsetMm': 'offset_mm',
        'endOffsetMm': 'end_mm',
        'chamferMm': 'chamfer_mm',
        'nozzleMm': 'nozzle_mm',
        'layerMm': 'layer_mm',
        'faceRadiusMm': 'face_radius_mm',
        'faceLengthMm': 'face_length_mm',
        'axisVertical': 'axis_vertical',
        'rightHand': 'right_hand',
    }
    for source, target in mapping.items():
        if source in payload and target not in payload:
            payload[target] = payload[source]
    return payload


def _find_primary(design, prefix):
    for feature in _primary_features(design):
        fields = _attr_map(feature)
        if fields.get('prefix') == prefix or fields.get('id') == prefix:
            return feature, fields
    raise geometry.GeometryError(f'Could not find {prefix}.')


def _component_of(feature):
    parent = getattr(feature, 'parentComponent', None)
    if not parent:
        raise geometry.GeometryError('The feature has no component.')
    return parent


def update_thread(data):
    design = _design()
    data = dict(data or {})
    prefix = data.get('id') or data.get('prefix')
    if not prefix:
        raise geometry.GeometryError('Choose a thread to update.')
    feature, fields = _find_primary(design, prefix)
    if fields.get('kind') != 'thread':
        raise geometry.GeometryError('That feature is not a thread.')
    return _rebuild_thread(design, feature, fields, _camel_to_profile(data))


def nudge_thread(data):
    design = _design()
    data = dict(data or {})
    prefix = data.get('id')
    direction = data.get('direction')
    feature, fields = _find_primary(design, prefix)
    if fields.get('kind') != 'thread':
        raise geometry.GeometryError('That feature is not a thread.')
    current = _param_value_mm(design, f'{prefix}_clear')
    if current is None:
        raise geometry.GeometryError('This thread has no clearance parameter.')
    updated = thread_profile.nudge_clearance(current, direction)
    return _rebuild_thread(design, feature, fields, {'clearance_mm': updated})


def _rebuild_thread(design, feature, fields, overrides):
    prefix = fields.get('prefix')
    component = _component_of(feature)
    nozzle, layer = _printer_numbers(overrides, design)
    payload = {
        'gender': fields.get('gender'),
        'build': fields.get('build'),
        'family': fields.get('family'),
        'size': fields.get('size'),
        'mating': fields.get('mating'),
        'right_hand': fields.get('right', '1') == '1',
        'lead': fields.get('lead', '1') == '1',
        'chamfer': fields.get('chamfer', '0') == '1',
        'flip': fields.get('flip', '0') == '1',
        'pitch_mm': _param_value_mm(design, f'{prefix}_pitch'),
        'clearance_mm': _param_value_mm(design, f'{prefix}_clear'),
        'length_mm': _param_value_mm(design, f'{prefix}_length'),
        'offset_mm': _param_value_mm(design, f'{prefix}_offset'),
        'end_mm': _param_value_mm(design, f'{prefix}_end') or 0,
        'chamfer_mm': _param_value_mm(design, f'{prefix}_chamfer') or 0,
        'flank_deg': _param_value_deg(design, f'{prefix}_flank'),
        'nozzle_mm': nozzle,
        'layer_mm': layer,
    }
    for key, value in overrides.items():
        if value is not None and value != '':
            payload[key] = value
    # Length stored on the parameter is already the snapped modeled length.
    # Re-applying it should not be treated as a fresh request that snaps again
    # unless the user sent a new length.
    if 'length_mm' not in overrides and 'lengthMm' not in overrides:
        payload['length_mm'] = _param_value_mm(design, f'{prefix}_length')

    previous = {
        'gender': fields.get('gender'),
        'build': fields.get('build'),
        'family': fields.get('family'),
        'size': fields.get('size'),
        'mating': fields.get('mating'),
        'right_hand': fields.get('right', '1') == '1',
        'lead': fields.get('lead', '1') == '1',
        'chamfer': fields.get('chamfer', '0') == '1',
        'flip': fields.get('flip', '0') == '1',
        'pitch_mm': _param_value_mm(design, f'{prefix}_pitch'),
        'clearance_mm': _param_value_mm(design, f'{prefix}_clear'),
        'length_mm': _param_value_mm(design, f'{prefix}_length'),
        'offset_mm': _param_value_mm(design, f'{prefix}_offset'),
        'end_mm': _param_value_mm(design, f'{prefix}_end') or 0,
        'chamfer_mm': _param_value_mm(design, f'{prefix}_chamfer') or 0,
        'flank_deg': _param_value_deg(design, f'{prefix}_flank'),
        'nozzle_mm': nozzle,
        'layer_mm': layer,
        'axis_vertical': True,
        'face_radius_mm': float(fields.get('radius') or 0),
        'face_length_mm': float(payload.get('offset_mm') or 0) + float(payload.get('length_mm') or 0) + float(payload.get('pitch_mm') or 1),
    }
    # Reject a bad edit before the existing thread is removed.
    preflight = dict(previous)
    preflight.update({key: value for key, value in payload.items() if value is not None and value != ''})
    thread_profile.resolve(preflight)

    geometry.delete_named(component, prefix)
    face = geometry.find_cylinder(
        design,
        fields.get('face'),
        fields.get('body'),
        fields.get('radius') or 0,
    )
    if not face:
        raise geometry.GeometryError(
            'The cylinder face could not be restored. Delete this thread and create it again.'
        )
    frame = geometry.inspect_cylinder(face)

    def _build(settings):
        spec = thread_profile.resolve(_face_payload(settings, frame))
        _write_thread_params(design, prefix, spec)
        feature, warnings = geometry.build_thread(frame, spec, prefix)
        return feature, warnings, spec

    try:
        feature, warnings, spec = _build(payload)
    except Exception as exc:
        try:
            _build(previous)
        except Exception:
            pass
        raise exc
    row = _thread_row(design, feature)
    return {'feature': row, 'preview': thread_profile.client_view(spec), 'warnings': warnings}


def delete_feature(data):
    design = _design()
    prefix = (data or {}).get('id')
    feature, fields = _find_primary(design, prefix)
    kind = fields.get('kind')
    geometry.delete_everywhere(prefix)
    if kind == 'insert':
        _delete_insert_params(design, prefix)
    else:
        _delete_thread_params(design, prefix)
    return {'deleted': prefix}


def create_insert(data):
    design = _design()
    data = dict(data or {})
    size = data.get('size') or 'Custom'
    preset = standards.insert_by_size(size) if size != 'Custom' else None
    hole = _float_or(data.get('holeMm'), preset['hole_mm'] if preset else None)
    depth = _float_or(data.get('depthMm'), preset['depth_mm'] if preset else None)
    chamfer = _float_or(data.get('chamferMm'), preset['chamfer_mm'] if preset else None)
    if hole is None or depth is None or chamfer is None:
        raise geometry.GeometryError('Enter a hole diameter, depth, and chamfer.')
    if hole <= 0 or depth <= 0 or chamfer < 0:
        raise geometry.GeometryError('Hole diameter and depth have to be greater than zero.')
    payload = {
        'size': size,
        'hole_mm': hole,
    }
    prefix = _next_prefix(design, 'i')
    _write_insert_params(design, prefix, hole, depth, chamfer)
    try:
        feature, warnings = geometry.build_insert(payload, prefix)
    except Exception:
        _delete_insert_params(design, prefix)
        raise
    return {'feature': _insert_row(design, feature), 'warnings': warnings}


def update_insert(data):
    design = _design()
    data = dict(data or {})
    prefix = data.get('id')
    feature, fields = _find_primary(design, prefix)
    if fields.get('kind') != 'insert':
        raise geometry.GeometryError('That feature is not a heat-set pocket.')
    hole = _float_or(data.get('holeMm'), _param_value_mm(design, f'{prefix}_dia'))
    depth = _float_or(data.get('depthMm'), _param_value_mm(design, f'{prefix}_depth'))
    chamfer = _float_or(data.get('chamferMm'), _param_value_mm(design, f'{prefix}_chamfer'))
    _write_insert_params(design, prefix, hole, depth, chamfer)
    size = data.get('size') or fields.get('size') or 'Custom'
    if size != fields.get('size'):
        geometry._tag(feature, {'size': size, 'label': f'{size} heat-set'})
    return {'feature': _insert_row(design, feature), 'warnings': []}


def nudge_insert(data):
    design = _design()
    data = dict(data or {})
    prefix = data.get('id')
    feature, fields = _find_primary(design, prefix)
    if fields.get('kind') != 'insert':
        raise geometry.GeometryError('That feature is not a heat-set pocket.')
    current = _param_value_mm(design, f'{prefix}_dia')
    if current is None:
        raise geometry.GeometryError('This pocket has no diameter parameter.')
    updated = thread_profile.nudge_hole(current, data.get('direction'))
    return update_insert({'id': prefix, 'holeMm': updated})


def _float_or(value, default):
    if value is None or value == '':
        return default
    return float(value)


def _round(value):
    if value is None:
        return None
    return round(float(value), 4)
