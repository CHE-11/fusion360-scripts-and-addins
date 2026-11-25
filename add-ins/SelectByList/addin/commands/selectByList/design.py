"""Read the active design for the Select By List palette.

Every list item carries two identifiers:
- `id` is a stable key built from occurrence paths and body names. The palette
  uses it for checkbox state, because entity tokens for the same entity are not
  guaranteed to be identical strings between calls.
- `token` is the entity token, used to find the entity again in Fusion.
"""

import adsk.core
import adsk.fusion

app = adsk.core.Application.get()
ui = app.userInterface

MAX_FACES = 2000

_COLOR_PROPERTY_IDS = (
    'opaque_albedo',
    'metal_f0',
    'transparent_color',
    'layered_bottom_f0',
    'wood_early_color',
    'generic_diffuse',
    'solidglass_transmittance_custom_color',
)


def _surface_names():
    names = {}
    pairs = (
        ('PlaneSurfaceType', 'Planar'),
        ('CylinderSurfaceType', 'Cylindrical'),
        ('ConeSurfaceType', 'Conical'),
        ('SphereSurfaceType', 'Spherical'),
        ('TorusSurfaceType', 'Toroidal'),
        ('EllipticalCylinderSurfaceType', 'Elliptical cylinder'),
        ('EllipticalConeSurfaceType', 'Elliptical cone'),
        ('NurbsSurfaceType', 'Freeform'),
    )
    for attr, label in pairs:
        value = getattr(adsk.core.SurfaceTypes, attr, None)
        if value is not None:
            names[value] = label
    return names


_SURFACE_NAMES = _surface_names()


# ---------------------------------------------------------------------------
# Design access
# ---------------------------------------------------------------------------

def active_design():
    try:
        return adsk.fusion.Design.cast(app.activeProduct)
    except Exception:
        return None


def require_design():
    design = active_design()
    if not design:
        raise ValueError('Open a Fusion design first.')
    return design


def resolve(token, design=None):
    if not token:
        return None
    design = design or active_design()
    if not design:
        return None
    try:
        found = design.findEntityByToken(token)
    except Exception:
        return None
    return found[0] if found else None


def resolve_many(tokens, design=None):
    """Resolve tokens and return (entities, missing_count)."""
    design = design or require_design()
    entities = []
    missing = 0
    for token in tokens or []:
        entity = resolve(token, design)
        if entity is None:
            missing += 1
        else:
            entities.append(entity)
    return entities, missing


def split_entities(entities):
    occurrences, bodies, faces = [], [], []
    for entity in entities:
        occ = adsk.fusion.Occurrence.cast(entity)
        if occ:
            occurrences.append(occ)
            continue
        body = adsk.fusion.BRepBody.cast(entity)
        if body:
            bodies.append(body)
            continue
        face = adsk.fusion.BRepFace.cast(entity)
        if face:
            faces.append(face)
    return occurrences, bodies, faces


# ---------------------------------------------------------------------------
# Stable keys
# ---------------------------------------------------------------------------

def occ_key(occ):
    return 'o:' + occ.fullPathName


def body_key(body):
    context = body.assemblyContext
    return 'b:' + (context.fullPathName if context else '') + '/' + body.name


def face_key(face):
    return body_key(face.body) + '#' + str(face.tempId)


def entity_key(entity):
    occ = adsk.fusion.Occurrence.cast(entity)
    if occ:
        return occ_key(occ)
    body = adsk.fusion.BRepBody.cast(entity)
    if body:
        return body_key(body)
    face = adsk.fusion.BRepFace.cast(entity)
    if face:
        return face_key(face)
    return ''


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

class _Units:
    def __init__(self, design):
        self.unit = 'mm'
        self.factor = 10.0
        try:
            manager = design.fusionUnitsManager
            self.unit = manager.defaultLengthUnits or 'mm'
            self.factor = manager.convert(1.0, 'cm', self.unit)
        except Exception:
            pass

    def number(self, value_cm):
        value = value_cm * self.factor
        if self.unit == 'mm':
            text = f'{value:.0f}' if abs(value) >= 10 else f'{value:.1f}'
        else:
            text = f'{value:.2f}'
        if '.' in text:
            text = text.rstrip('0').rstrip('.')
        return text or '0'

    def dims(self, bbox):
        if not bbox:
            return ''
        try:
            low, high = bbox.minPoint, bbox.maxPoint
            sizes = (high.x - low.x, high.y - low.y, high.z - low.z)
        except Exception:
            return ''
        return 'x'.join(self.number(size) for size in sizes) + self.unit

    def area(self, area_cm2):
        value = area_cm2 * self.factor * self.factor
        text = f'{value:.0f}' if abs(value) >= 100 else f'{value:.2f}'.rstrip('0').rstrip('.')
        return f'{text}{self.unit}\u00b2'


def _appearance_color(appearance, cache):
    if appearance is None:
        return ''
    try:
        key = appearance.id
    except Exception:
        key = None
    if key and key in cache:
        return cache[key]
    color = ''
    try:
        props = appearance.appearanceProperties
        candidates = []
        for prop_id in _COLOR_PROPERTY_IDS:
            prop = props.itemById(prop_id)
            if prop:
                candidates.append(prop)
        for index in range(props.count):
            candidates.append(props.item(index))
        for prop in candidates:
            color_prop = adsk.core.ColorProperty.cast(prop)
            if not color_prop:
                continue
            value = color_prop.value
            if value:
                color = '#%02x%02x%02x' % (value.red, value.green, value.blue)
                break
    except Exception:
        color = ''
    if key:
        cache[key] = color
    return color


def _occurrence_appearance(occ):
    try:
        if occ.appearance:
            return occ.appearance
    except Exception:
        pass
    try:
        if occ.bRepBodies.count:
            return occ.bRepBodies.item(0).appearance
        for index in range(occ.childOccurrences.count):
            found = _occurrence_appearance(occ.childOccurrences.item(index))
            if found:
                return found
    except Exception:
        pass
    return None


def _context_label(full_path):
    parts = full_path.split('+')
    return ' / '.join(parts[:-1])


# ---------------------------------------------------------------------------
# Tree walks (browser order)
# ---------------------------------------------------------------------------

def _walk_occurrences(occurrences, depth, out):
    for index in range(occurrences.count):
        occ = occurrences.item(index)
        out.append((occ, depth))
        _walk_occurrences(occ.childOccurrences, depth + 1, out)


def bodies_in_occurrence(occ, out):
    for index in range(occ.bRepBodies.count):
        out.append(occ.bRepBodies.item(index))
    for index in range(occ.childOccurrences.count):
        bodies_in_occurrence(occ.childOccurrences.item(index), out)


def all_bodies(design):
    root = design.rootComponent
    bodies = [root.bRepBodies.item(index) for index in range(root.bRepBodies.count)]
    for index in range(root.occurrences.count):
        bodies_in_occurrence(root.occurrences.item(index), bodies)
    return bodies


# ---------------------------------------------------------------------------
# Item builders
# ---------------------------------------------------------------------------

def _occurrence_items(design):
    units = _Units(design)
    colors = {}
    walked = []
    _walk_occurrences(design.rootComponent.occurrences, 0, walked)
    items = []
    for order, (occ, depth) in enumerate(walked):
        try:
            child_count = occ.childOccurrences.count
            items.append({
                'id': occ_key(occ),
                'token': occ.entityToken,
                'kind': 'assembly' if child_count else 'component',
                'name': occ.name,
                'context': _context_label(occ.fullPathName),
                'depth': depth,
                'order': order,
                'dims': units.dims(occ.boundingBox),
                'color': _appearance_color(_occurrence_appearance(occ), colors),
                'visible': bool(occ.isLightBulbOn),
                'shown': bool(occ.isVisible),
                'linked': bool(occ.isReferencedComponent),
                'childCount': child_count,
            })
        except Exception:
            continue
    return items


def _body_items(design):
    units = _Units(design)
    colors = {}
    root_name = design.rootComponent.name
    items = []
    for order, body in enumerate(all_bodies(design)):
        try:
            context = body.assemblyContext
            items.append({
                'id': body_key(body),
                'token': body.entityToken,
                'kind': 'body',
                'name': body.name,
                'context': context.name if context else root_name,
                'depth': 0,
                'order': order,
                'dims': units.dims(body.boundingBox),
                'color': _appearance_color(body.appearance, colors),
                'visible': bool(body.isLightBulbOn),
                'shown': bool(body.isVisible),
                'linked': False,
                'childCount': body.faces.count,
            })
        except Exception:
            continue
    return items


def _face_target_bodies(design, tokens):
    if not tokens:
        return [body for body in all_bodies(design) if body.isVisible]
    entities, _missing = resolve_many(tokens, design)
    occurrences, bodies, faces = split_entities(entities)
    targets = list(bodies)
    for occ in occurrences:
        bodies_in_occurrence(occ, targets)
    for face in faces:
        targets.append(face.body)
    seen = set()
    unique = []
    for body in targets:
        key = body_key(body)
        if key not in seen:
            seen.add(key)
            unique.append(body)
    return unique


def _face_items(design, tokens):
    units = _Units(design)
    colors = {}
    items = []
    warning = ''
    for body in _face_target_bodies(design, tokens):
        context = body.assemblyContext
        context_label = f'{body.name} ({context.name})' if context else body.name
        base_key = body_key(body)
        faces = body.faces
        for index in range(faces.count):
            if len(items) >= MAX_FACES:
                warning = f'Showing the first {MAX_FACES} faces. Check fewer bodies to see the rest.'
                return items, warning
            face = faces.item(index)
            try:
                surface = _SURFACE_NAMES.get(face.geometry.surfaceType, 'Surface')
                items.append({
                    'id': base_key + '#' + str(face.tempId),
                    'token': face.entityToken,
                    'kind': 'face',
                    'name': f'{body.name} / Face {index + 1}',
                    'context': context_label,
                    'surface': surface,
                    'depth': 0,
                    'order': len(items),
                    'dims': f'{surface} \u00b7 {units.area(face.area)}',
                    'color': _appearance_color(face.appearance, colors),
                    'visible': bool(body.isLightBulbOn),
                    'shown': bool(body.isVisible),
                    'linked': False,
                    'childCount': 0,
                })
            except Exception:
                continue
    return items, warning


def list_items(payload):
    design = require_design()
    mode = str(payload.get('mode') or 'component')
    warning = ''
    if mode in ('component', 'assembly'):
        items = _occurrence_items(design)
    elif mode == 'body':
        items = _body_items(design)
    elif mode == 'face':
        tokens = payload.get('tokens') or []
        items, warning = _face_items(design, tokens)
    else:
        raise ValueError(f'Unknown list mode: {mode}')
    return {'mode': mode, 'items': items, 'warning': warning}


# ---------------------------------------------------------------------------
# Viewport selection
# ---------------------------------------------------------------------------

def select_in_viewport(tokens):
    design = require_design()
    entities, missing = resolve_many(tokens, design)
    selections = ui.activeSelections
    selections.clear()
    added = 0
    for entity in entities:
        try:
            selections.add(entity)
            added += 1
        except Exception:
            missing += 1
    return {'selected': added, 'missing': missing}


def viewport_selection():
    keys = []
    try:
        selections = ui.activeSelections
        for index in range(selections.count):
            key = entity_key(selections.item(index).entity)
            if key:
                keys.append(key)
        count = selections.count
    except Exception:
        count = 0
    return {'count': count, 'keys': keys}


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------

def rename(payload):
    design = require_design()
    name = str(payload.get('name') or '').strip()
    if not name:
        raise ValueError('Enter a name.')
    entity = resolve(payload.get('token'), design)
    if entity is None:
        raise ValueError('That item no longer exists. Refresh the list.')
    occ = adsk.fusion.Occurrence.cast(entity)
    try:
        if occ:
            if occ.isReferencedComponent:
                raise ValueError('Linked components must be renamed in their own design.')
            occ.component.name = name
            return {'id': occ_key(occ), 'token': occ.entityToken, 'name': occ.name}
        body = adsk.fusion.BRepBody.cast(entity)
        if body:
            body.name = name
            return {'id': body_key(body), 'token': body.entityToken, 'name': body.name}
    except RuntimeError as exc:
        raise ValueError(f'Fusion would not rename that: {exc}')
    raise ValueError('Only components and bodies can be renamed.')


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

def _enum_label(value):
    if isinstance(value, str):
        return value
    for enum_name in ('UserInterfaceThemes', 'UserInterfaceThemeTypes', 'UIThemeTypes', 'ThemeTypes'):
        enum = getattr(adsk.core, enum_name, None)
        if not enum:
            continue
        for name in dir(enum):
            if name.startswith('_'):
                continue
            try:
                if getattr(enum, name) == value:
                    return name
            except Exception:
                continue
    return str(value)


def ui_theme():
    """Return 'dark', 'light', or None when Fusion does not expose the theme."""
    try:
        prefs = app.preferences.generalPreferences
    except Exception:
        return None
    for attr in ('userInterfaceTheme', 'uiTheme', 'colorTheme', 'theme'):
        try:
            value = getattr(prefs, attr)
        except Exception:
            continue
        if value is None:
            continue
        label = _enum_label(value).lower()
        if 'dark' in label:
            return 'dark'
        if 'light' in label or 'gray' in label or 'classic' in label:
            return 'light'
    return None


def ready(payload):
    design = active_design()
    theme = ui_theme()
    if not design:
        return {
            'hasDocument': False,
            'designName': '',
            'theme': theme,
            'mode': str(payload.get('mode') or 'component'),
            'items': [],
            'warning': '',
            'viewport': {'count': 0, 'keys': []},
        }
    listing = list_items(payload)
    try:
        name = app.activeDocument.name
    except Exception:
        name = design.rootComponent.name
    return {
        'hasDocument': True,
        'designName': name,
        'theme': theme,
        'viewport': viewport_selection(),
        **listing,
    }
