"""Thread section math for 3D-printed and metal-mating threads.

Lengths are millimeters. Nothing in this module imports the Fusion API.

The helix is swept along the selected cylindrical face. Clearance and a small
root overlap are radial offsets of the profile relative to that face, so a
looser fit moves a male thread inward and a female thread outward.
"""

from __future__ import annotations

import math

from . import standards

PLASTIC_CLEARANCE_MM = 0.20
METAL_CLEARANCE_MM = 0.15
THREAD_NUDGE_MM = 0.05
INSERT_NUDGE_MM = 0.10
# Just enough root overlap for a boolean. The helix itself stays on the face.
EMBED_MM = 0.10
LEAD_PITCH_FRACTION = 0.75
PRINTABLE_FLANK_DEG = 45.0
ISO_FLANK_DEG = 60.0
# ISO 68 / unified basic profile: H = (sqrt(3) / 2) * P, tooth height = 5/8 H.
ISO_TOOTH_HEIGHT_FACTOR = (5.0 / 8.0) * (math.sqrt(3.0) / 2.0)
ISO_CREST_FACTOR = 1.0 / 8.0
ISO_ROOT_WIDTH_FACTOR = 0.75
MIN_FLANK_DEG = 20.0
MAX_FLANK_DEG = 75.0

FACE_ROLE = {
    ('male', 'outset'): 'This face is the root. Teeth are added outside it.',
    ('male', 'inset'): 'This face is the major diameter. Grooves are cut into it.',
    ('female', 'outset'): 'This face is the major diameter of the hole. Teeth are added inside it.',
    ('female', 'inset'): 'This face is the minor diameter of the hole. Grooves are cut into the wall.',
}


class ProfileError(ValueError):
    """The inputs cannot make a printable thread."""


def snap_pitch(pitch_mm: float, layer_mm: float, enabled: bool) -> float:
    """Round a printable pitch onto a whole number of layers."""
    if pitch_mm <= 0:
        raise ProfileError('Pitch has to be greater than zero.')
    if not enabled or layer_mm <= 0:
        return pitch_mm
    steps = max(1, int(round(pitch_mm / layer_mm)))
    return steps * layer_mm


def samples_per_turn(radius_mm: float, tooth_mm: float) -> int:
    """Chord density so the helix stays close enough to the cylinder to guide a sweep."""
    tol = min(0.15, max(0.04, 0.15 * max(tooth_mm, 0.2)))
    if radius_mm <= tol:
        return 32
    ratio = max(-1.0, min(1.0, 1.0 - tol / radius_mm))
    count = math.pi / math.acos(ratio)
    return int(max(24, min(80, math.ceil(count))))


def _cot_from_axis(flank_deg: float) -> float:
    """Axial run per unit of radial height. Flank is measured from the thread axis."""
    if flank_deg < MIN_FLANK_DEG or flank_deg > MAX_FLANK_DEG:
        raise ProfileError(
            f'Flank angle has to stay between {MIN_FLANK_DEG:.0f}° and {MAX_FLANK_DEG:.0f}° from the axis.'
        )
    tangent = math.tan(math.radians(flank_deg))
    if abs(tangent) < 1e-6:
        raise ProfileError('Flank angle is too close to the axis.')
    return 1.0 / tangent


def _number(data: dict, key: str, default=None):
    value = data.get(key, default)
    if value is None or value == '':
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ProfileError(f'{key} is not a number.') from exc


def _choice(value, allowed, label):
    if value not in allowed:
        raise ProfileError(f'{label} must be one of: {", ".join(allowed)}.')
    return value


def printable_tooth(pitch_mm: float, flank_deg: float, nozzle_mm: float):
    """Symmetric trapezoid: nozzle-wide crest, equal tooth and gap, full flank height.

    At 45° from the axis the tallest tooth that still leaves a nozzle-wide crest
    and a nozzle-wide valley is ``pitch / 2 - nozzle``. Shorter teeth disappear
    into the cylinder once clearance is applied.
    """
    if nozzle_mm <= 0:
        raise ProfileError('Nozzle diameter has to be greater than zero.')
    cot = _cot_from_axis(flank_deg)
    if pitch_mm / 2 <= nozzle_mm:
        raise ProfileError(
            'Pitch is too fine for a crest as wide as the nozzle. '
            'Use a coarser pitch or a heat-set insert.'
        )
    height = (pitch_mm / 2 - nozzle_mm) / cot
    crest = nozzle_mm
    root = pitch_mm - crest
    if crest < nozzle_mm - 1e-6:
        raise ProfileError('Could not keep the crest at least as wide as the nozzle.')
    return height, crest, root


def standard_tooth(pitch_mm: float):
    """Truncated 60° profile shared by ISO metric and UNC."""
    height = ISO_TOOTH_HEIGHT_FACTOR * pitch_mm
    crest = ISO_CREST_FACTOR * pitch_mm
    root = ISO_ROOT_WIDTH_FACTOR * pitch_mm
    return height, crest, root


def _quad(left_a, right_a, left_b, right_b, radial_a, radial_b):
    return (
        (left_a, radial_a),
        (right_a, radial_a),
        (right_b, radial_b),
        (left_b, radial_b),
    )


def _placement(gender, build, face_radius, pitch, height, crest_w, root_w, clearance):
    """Radial offsets from the selected face. Positive is away from the axis.

    Outset teeth stand on the face. Clearance shortens the tip, it does not
    sink the root into the solid. Inset cuts a full groove and uses clearance
    as extra depth. A small embed gives the boolean real volume overlap.
    """
    into = -1.0 if gender == 'male' else 1.0
    if build == 'outset':
        proud = height - clearance
        if proud < 0.2:
            raise ProfileError(
                'Clearance leaves almost no tooth. Lower the clearance or use a coarser pitch.'
            )
        root_off = into * EMBED_MM
        crest_off = -into * proud
        corners = _quad(-root_w / 2, root_w / 2, crest_w / 2, -crest_w / 2, root_off, crest_off)
        if gender == 'male':
            root_r = face_radius
            crest_r = face_radius + proud
        else:
            root_r = face_radius
            crest_r = face_radius - proud
        operation = 'join'
    else:
        mouth_w = pitch - crest_w
        floor_w = pitch - root_w
        if mouth_w <= 0.1 or floor_w <= 0.1 or floor_w >= mouth_w:
            raise ProfileError('The groove does not fit in one pitch. Increase the pitch or reduce the tooth.')
        mouth_off = -into * EMBED_MM
        floor_off = into * (height + clearance)
        corners = _quad(-mouth_w / 2, mouth_w / 2, floor_w / 2, -floor_w / 2, mouth_off, floor_off)
        if gender == 'male':
            crest_r = face_radius
            root_r = face_radius - height - clearance
        else:
            crest_r = face_radius
            root_r = face_radius + height + clearance
        operation = 'cut'

    if min(root_r, crest_r) <= 0.2:
        raise ProfileError('The thread crosses the axis. Use a larger diameter or a shorter tooth.')
    if root_w <= 0 or crest_w <= 0 or root_w >= pitch or crest_w >= pitch:
        raise ProfileError('The tooth does not fit in one pitch. Increase the pitch or reduce the tooth.')

    return {
        'root_radius_mm': root_r,
        'crest_radius_mm': crest_r,
        'corners': corners,
        'operation': operation,
    }


def _expected_face_diameter(family, gender, build, nominal_major, tooth_height):
    if family == 'printable':
        return None
    minor = nominal_major - 2 * tooth_height
    if (gender == 'male' and build == 'inset') or (gender == 'female' and build == 'outset'):
        return nominal_major
    return minor


def resolve(data: dict) -> dict:
    """Turn a palette payload plus the measured face into a sweep recipe."""
    if not isinstance(data, dict):
        raise ProfileError('Thread settings are missing.')

    gender = _choice(data.get('gender', 'male'), ('male', 'female'), 'Gender')
    build = _choice(data.get('build', 'outset'), ('inset', 'outset'), 'Build')
    family = _choice(data.get('family', 'printable'), ('printable', 'iso', 'unc'), 'Thread family')
    warnings = []
    notes = []

    face_radius = _number(data, 'face_radius_mm')
    face_length = _number(data, 'face_length_mm')
    if face_radius is None or face_radius <= 0:
        raise ProfileError('Select a cylindrical face.')
    if face_length is None or face_length <= 0:
        raise ProfileError('The selected face has no usable length.')

    layer = _number(data, 'layer_mm', 0.2)
    nozzle = _number(data, 'nozzle_mm', 0.4)
    if layer <= 0 or nozzle <= 0:
        raise ProfileError('Layer height and nozzle diameter have to be greater than zero.')

    mating = data.get('mating')
    if family == 'printable':
        mating = mating or 'plastic'
        size = 'Custom'
        nominal_major = 2 * face_radius
        flank = _number(data, 'flank_deg', PRINTABLE_FLANK_DEG)
        requested_pitch = _number(data, 'pitch_mm')
        if requested_pitch is None:
            requested_pitch = max(1.0, nominal_major / 8.0)
        pitch = snap_pitch(requested_pitch, layer, True)
        if abs(pitch - requested_pitch) > 1e-6:
            notes.append(
                f'Pitch snapped from {requested_pitch:.2f} mm to {pitch:.2f} mm so it matches the layer height.'
            )
        clearance = _number(data, 'clearance_mm', PLASTIC_CLEARANCE_MM)
        height, crest_w, root_w = printable_tooth(pitch, flank, nozzle)
    else:
        mating = mating or 'metal'
        size = str(data.get('size') or '')
        row = standards.iso_by_size(size) if family == 'iso' else standards.unc_by_size(size)
        if not row:
            raise ProfileError('Choose a thread size.')
        size = row['size']
        nominal_major = row['major_mm']
        pitch = row['pitch_mm']
        flank = ISO_FLANK_DEG
        clearance = _number(data, 'clearance_mm', METAL_CLEARANCE_MM)
        height, crest_w, root_w = standard_tooth(pitch)
        if nominal_major < standards.SMALL_THREAD_MAJOR_MM:
            warnings.append(
                'Modeled threads smaller than M5 or #10 rarely print cleanly. '
                'A heat-set insert or a tapped hole is the more reliable choice.'
            )
        if crest_w < nozzle:
            warnings.append(
                f'The {size} crest is {crest_w:.2f} mm, finer than the {nozzle:.2f} mm nozzle. '
                'The tip will not form fully. Plan on a clearance nudge after the test print.'
            )

    mating = _choice(mating, ('plastic', 'metal'), 'Mating')
    if clearance < 0:
        raise ProfileError('Clearance cannot be negative.')

    if data.get('axis_vertical') is False:
        warnings.append('Print this with the thread axis vertical. A sideways thread is weaker and less accurate.')

    if family != 'printable' and pitch > 0 and layer > 0 and abs(pitch / layer - round(pitch / layer)) > 0.08:
        notes.append(
            'This pitch is not a multiple of the layer height. Leave it unchanged so it still matches the metal fastener.'
        )

    placed = _placement(gender, build, face_radius, pitch, height, crest_w, root_w, clearance)
    if gender == 'female' and height >= face_radius - 0.2:
        raise ProfileError('The tooth is deeper than the hole radius.')
    if gender == 'female' and height > face_radius * 0.45:
        warnings.append('The tooth is deep for this hole. Leave enough wall outside the thread.')

    expected = _expected_face_diameter(family, gender, build, nominal_major, height)
    face_diameter = 2 * face_radius
    if expected is not None and abs(face_diameter - expected) > 0.4:
        warnings.append(
            f'Selected face is Ø{face_diameter:.2f} mm. {size} expects about Ø{expected:.2f} mm for this build. '
            'The thread follows the selected face.'
        )

    start = _number(data, 'offset_mm', 0.0) or 0.0
    end_gap = _number(data, 'end_mm', 0.0) or 0.0
    if start < 0 or end_gap < 0:
        raise ProfileError('Offsets cannot be negative.')
    chamfer_on = bool(data.get('chamfer', False))
    chamfer_mm = _number(data, 'chamfer_mm', 1.0 if chamfer_on else 0.0) or 0.0
    if not chamfer_on or chamfer_mm <= 0:
        chamfer_mm = 0.0
    if chamfer_mm < 0:
        raise ProfileError('Chamfer cannot be negative.')
    flip = bool(data.get('flip', False))
    requested_length = _number(data, 'length_mm')
    if requested_length is not None and requested_length <= 0:
        raise ProfileError('Length has to be greater than zero.')
    # The chamfer is cut on both rims first. The thread starts after it.
    edge = chamfer_mm
    end_inset = 0.0 if flip and end_gap == 0 else end_gap
    span = face_length - start - end_inset - 2.0 * edge
    usable = span if requested_length is None else min(span, requested_length)
    if usable <= 0:
        if edge > 0:
            raise ProfileError('The chamfer leaves no room for a thread on this face.')
        raise ProfileError('The offsets leave no room for a thread on this face.')
    turns = int(math.floor(usable / pitch + 1e-9))
    if turns < 1:
        raise ProfileError('The face is shorter than one pitch. Use a coarser pitch or a longer face.')
    length = turns * pitch
    capped = span if requested_length is None else min(requested_length, span)
    if abs(length - capped) > 0.05:
        notes.append(f'Length snapped to {turns} whole turn{"s" if turns != 1 else ""} ({length:.2f} mm).')
    offset = (face_length - start - edge - length) if flip and end_gap == 0 else start + edge
    if chamfer_mm > 0:
        notes.append(f'Both ends are chamfered {chamfer_mm:.2f} mm, then the thread starts.')
    if offset < -1e-6:
        raise ProfileError('The thread does not fit on this face.')
    offset = max(0.0, offset)

    lead_on = bool(data.get('lead', True))
    lead = min(LEAD_PITCH_FRACTION * pitch, length * 0.45) if lead_on else 0.0
    right_hand = bool(data.get('right_hand', True))

    if gender == 'male':
        major = 2 * placed['crest_radius_mm']
        minor = 2 * placed['root_radius_mm']
    else:
        major = 2 * placed['root_radius_mm']
        minor = 2 * placed['crest_radius_mm']

    label_size = size if family != 'printable' else f'Ø{face_diameter:.1f}'
    label = f'{label_size} {gender} {build}'

    return {
        'gender': gender,
        'build': build,
        'family': family,
        'size': size,
        'mating': mating,
        'pitch_mm': pitch,
        'flank_deg': flank,
        'clearance_mm': clearance,
        'tooth_height_mm': height,
        'crest_width_mm': crest_w,
        'root_width_mm': root_w,
        'root_radius_mm': placed['root_radius_mm'],
        'crest_radius_mm': placed['crest_radius_mm'],
        'corners': placed['corners'],
        'operation': placed['operation'],
        'major_mm': major,
        'minor_mm': minor,
        'turns': turns,
        'length_mm': length,
        'offset_mm': offset,
        'inset_mm': start,
        'end_mm': end_gap,
        'chamfer_mm': chamfer_mm,
        'chamfer': chamfer_mm > 0,
        'flip': flip,
        'lead_mm': lead,
        'lead': lead_on,
        'right_hand': right_hand,
        'samples_per_turn': samples_per_turn(face_radius, height),
        'nozzle_mm': nozzle,
        'layer_mm': layer,
        'face_role': FACE_ROLE[(gender, build)],
        'label': label,
        'warnings': warnings,
        'notes': notes,
        'nominal_major_mm': nominal_major,
    }


def client_view(spec: dict) -> dict:
    """Palette-facing preview. Drops the sweep corners."""
    return {
        'gender': spec['gender'],
        'build': spec['build'],
        'family': spec['family'],
        'size': spec['size'],
        'mating': spec['mating'],
        'pitchMm': _round(spec['pitch_mm']),
        'flankDeg': _round(spec['flank_deg']),
        'clearanceMm': _round(spec['clearance_mm']),
        'toothMm': _round(spec['tooth_height_mm']),
        'crestMm': _round(spec['crest_width_mm']),
        'majorMm': _round(spec['major_mm']),
        'minorMm': _round(spec['minor_mm']),
        'turns': spec['turns'],
        'lengthMm': _round(spec['length_mm']),
        'offsetMm': _round(spec['offset_mm']),
        'chamferMm': _round(spec['chamfer_mm']),
        'leadMm': _round(spec['lead_mm']),
        'rightHand': spec['right_hand'],
        'faceRole': spec['face_role'],
        'label': spec['label'],
        'warnings': list(spec['warnings']),
        'notes': list(spec['notes']),
        'operation': spec['operation'],
    }


def nudge_clearance(current_mm: float, direction: str) -> float:
    if direction == 'tight':
        return current_mm + THREAD_NUDGE_MM
    if direction == 'loose':
        return max(0.0, current_mm - THREAD_NUDGE_MM)
    raise ProfileError('Nudge direction must be tight or loose.')


def nudge_hole(current_mm: float, direction: str) -> float:
    if direction == 'tight':
        return current_mm + INSERT_NUDGE_MM
    if direction == 'loose':
        updated = current_mm - INSERT_NUDGE_MM
        if updated < 0.5:
            raise ProfileError('The hole is already at the smallest step.')
        return updated
    raise ProfileError('Nudge direction must be tight or loose.')


def _round(value: float) -> float:
    return round(float(value), 4)
