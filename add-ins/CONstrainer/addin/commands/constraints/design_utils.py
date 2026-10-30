"""Design, occurrence, and entity helpers shared by the assembly constraint commands."""

import adsk.core
import adsk.fusion

app = adsk.core.Application.get()


def design_intent():
    """part, assembly, hybrid, or none when the active product is not a design."""
    try:
        active = design()
    except RuntimeError:
        return 'none'
    return intent_name(active)


def design():
    active = adsk.fusion.Design.cast(app.activeProduct)
    if not active:
        raise RuntimeError('No active design.')
    return active


def require_assembly():
    active = design()
    if intent_name(active) not in ('assembly', 'hybrid'):
        raise ValueError('Assembly constraints are available in assembly and hybrid designs.')
    return active


def intent_name(active):
    """Map Design.designIntent to part, assembly, or hybrid.

    Documents from before design intent existed stay hybrid, which is how those
    files behave: components and local geometry together.
    """
    try:
        value = active.designIntent
    except Exception:
        return 'hybrid'
    number = _enum_number(value)
    if number == 0:
        return 'part'
    if number == 1:
        return 'assembly'
    if number == 2:
        return 'hybrid'
    text = str(value)
    if 'Hybrid' in text:
        return 'hybrid'
    if 'Assembly' in text:
        return 'assembly'
    if 'Part' in text:
        return 'part'
    return 'hybrid'


def _enum_number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        pass
    try:
        return int(getattr(value, 'value'))
    except (TypeError, ValueError, AttributeError):
        return None


def components(active):
    collection = active.allComponents
    for index in range(collection.count):
        yield collection.item(index)


def relationships(item):
    collection = read_attr(item, 'geometricRelationships')
    if collection is None:
        return []
    try:
        return [collection.item(index) for index in range(collection.count)]
    except Exception:
        return []


def find_all(active, token):
    if not token:
        return []
    try:
        return _as_list(active.findEntityByToken(token))
    except Exception:
        return []


def _as_list(found):
    """findEntityByToken returns a SWIG vector in Python, not an adsk object."""
    if found is None:
        return []
    if isinstance(found, (list, tuple)):
        return [item for item in found if item is not None]
    try:
        if found.objectType == 'adsk::core::ObjectCollection':
            return [found.item(index) for index in range(found.count)]
        return [found]
    except Exception:
        pass
    try:
        return [item for item in list(found) if item is not None]
    except Exception:
        return []


def same(first, second):
    """Match two entities, including a proxy against its native object in the same occurrence."""
    if first is None or second is None:
        return False
    try:
        if first == second:
            return True
    except Exception:
        pass
    first_token = token(first)
    if first_token and first_token == token(second):
        return True
    native_first = read_attr(first, 'nativeObject') or first
    native_second = read_attr(second, 'nativeObject') or second
    if native_first is first and native_second is second:
        return False
    try:
        if not native_first == native_second:
            return False
    except Exception:
        return False
    context_first = read_attr(first, 'assemblyContext')
    context_second = read_attr(second, 'assemblyContext')
    if context_first is None or context_second is None:
        return True
    try:
        return context_first == context_second
    except Exception:
        return token(context_first) == token(context_second)


def occurrence_of(entity):
    occurrence = adsk.fusion.Occurrence.cast(entity)
    if occurrence:
        return occurrence
    try:
        context = entity.assemblyContext
    except Exception:
        return None
    return adsk.fusion.Occurrence.cast(context) if context else None


def proxy(entity, occurrence):
    try:
        return entity.createForAssemblyContext(occurrence)
    except Exception:
        return entity


def owner_occurrences(active, component, cache):
    """Root-level occurrences of a component. [None] means the root component itself."""
    root = active.rootComponent
    if component is None or same(component, root):
        return [None]
    key = token(component) or id(component)
    if key not in cache:
        occurrences = []
        try:
            found = root.allOccurrencesByComponent(component)
            occurrences = [found.item(index) for index in range(found.count)]
        except Exception:
            occurrences = []
        cache[key] = occurrences or [None]
    return cache[key]


def occurrence_path(occurrence):
    if occurrence is None:
        return ''
    try:
        return occurrence.fullPathName or ''
    except Exception:
        return safe_name(occurrence, '')


def join_path(path, prefix):
    if not path:
        return prefix
    if not prefix or path_within(path, prefix):
        return path
    return f'{prefix}+{path}'


def path_within(path, ancestor):
    return bool(path) and bool(ancestor) and (path == ancestor or path.startswith(ancestor + '+'))


def focus_kind(entity):
    if entity is None:
        return None
    if adsk.fusion.Occurrence.cast(entity):
        return 'component'
    if adsk.fusion.BRepBody.cast(entity):
        return 'body'
    if (
        adsk.fusion.JointOrigin.cast(entity)
        or adsk.fusion.BRepFace.cast(entity)
        or adsk.fusion.BRepEdge.cast(entity)
        or adsk.fusion.BRepVertex.cast(entity)
        or adsk.fusion.SketchPoint.cast(entity)
        or adsk.fusion.SketchCurve.cast(entity)
        or adsk.fusion.ConstructionPoint.cast(entity)
    ):
        return _geometry_kind(entity)
    return None


def describe_focus(entity, occurrence):
    return {
        'label': geometry_label(entity),
        'kind': focus_kind(entity),
        'token': token(entity),
        'occurrenceName': safe_name(occurrence, 'Component') if occurrence else '',
    }


def _geometry_kind(entity):
    if adsk.fusion.JointOrigin.cast(entity):
        return 'jointOrigin'
    face = adsk.fusion.BRepFace.cast(entity)
    if face:
        return 'planarFace' if _is_planar_face(face) else 'face'
    if adsk.fusion.BRepEdge.cast(entity) or adsk.fusion.SketchCurve.cast(entity):
        return 'curve'
    return 'point'


def geometry_label(entity):
    if adsk.fusion.JointOrigin.cast(entity):
        return f"Joint origin: {safe_name(entity, 'Joint origin')}"
    face = adsk.fusion.BRepFace.cast(entity)
    if face:
        return 'Planar face' if _is_planar_face(face) else 'Face'
    if adsk.fusion.BRepEdge.cast(entity):
        return 'Edge'
    if adsk.fusion.BRepVertex.cast(entity):
        return 'Vertex'
    if adsk.fusion.SketchPoint.cast(entity):
        return 'Sketch point'
    if adsk.fusion.SketchCurve.cast(entity):
        return 'Sketch curve'
    if adsk.fusion.ConstructionPoint.cast(entity):
        return 'Construction point'
    if adsk.fusion.ConstructionPlane.cast(entity):
        return f"Plane: {safe_name(entity, 'Plane')}"
    if adsk.fusion.ConstructionAxis.cast(entity):
        return f"Axis: {safe_name(entity, 'Axis')}"
    occurrence = adsk.fusion.Occurrence.cast(entity)
    if occurrence:
        return f"Component: {safe_name(occurrence, 'Component')}"
    body = adsk.fusion.BRepBody.cast(entity)
    if body:
        return f"Body: {safe_name(body, 'Body')}"
    return 'Geometry'


def _is_planar_face(face):
    try:
        return face.geometry.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType
    except Exception:
        return False


def side_label(occurrence):
    if occurrence is None:
        return 'Root'
    return safe_name(occurrence, 'Component')


def is_suppressed(item):
    try:
        return bool(item.isSuppressed)
    except Exception:
        return False


def is_light_bulb_on(item):
    try:
        return bool(item.isLightBulbOn)
    except Exception:
        return True


def is_visible(item):
    try:
        return bool(item.isVisible)
    except Exception:
        return is_light_bulb_on(item)


def expression(parameter):
    if parameter is None:
        return ''
    try:
        return parameter.expression or ''
    except Exception:
        return ''


def token(entity):
    if entity is None:
        return ''
    try:
        return entity.entityToken or ''
    except Exception:
        return ''


def safe_name(entity, fallback):
    try:
        name = entity.name
    except Exception:
        return fallback
    return name or fallback


def read_attr(obj, name):
    try:
        value = getattr(obj, name)
    except Exception:
        return None
    if value is None or callable(value):
        return None
    return value
