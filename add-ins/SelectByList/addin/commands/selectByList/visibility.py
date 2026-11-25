"""Show, hide, isolate, and restore visibility for the Select By List palette."""

import adsk.core
import adsk.fusion

from . import design as d

# Light bulb states captured by the first Isolate, replayed by Restore All.
# Kept per document so switching designs does not mix them up.
_snapshots = {}


def _doc_key(design=None):
    design = design or d.active_design()
    if not design:
        return ''
    try:
        document = design.parentDocument
    except Exception:
        return ''
    for attr in ('creationId', 'name'):
        try:
            value = getattr(document, attr)
            if value:
                return str(value)
        except Exception:
            continue
    return ''


def is_isolated():
    return _doc_key() in _snapshots


def _turn_on_ancestors(occ):
    while occ:
        if not occ.isLightBulbOn:
            occ.isLightBulbOn = True
        occ = occ.assemblyContext


def _set_body(body, on):
    if body.isLightBulbOn != on:
        body.isLightBulbOn = on


def _targets(tokens, verb):
    design = d.require_design()
    entities, missing = d.resolve_many(tokens, design)
    occurrences, bodies, faces = d.split_entities(entities)
    for face in faces:
        bodies.append(face.body)
    if not occurrences and not bodies:
        raise ValueError(f'Check at least one component or body to {verb}.')
    return design, occurrences, bodies, missing


def show(tokens):
    _design, occurrences, bodies, missing = _targets(tokens, 'show')
    for occ in occurrences:
        occ.isLightBulbOn = True
        _turn_on_ancestors(occ.assemblyContext)
    for body in bodies:
        _set_body(body, True)
        context = body.assemblyContext
        try:
            component = context.component if context else body.parentComponent
            if not component.isBodiesFolderLightBulbOn:
                component.isBodiesFolderLightBulbOn = True
        except Exception:
            pass
        _turn_on_ancestors(context)
    return {'changed': len(occurrences) + len(bodies), 'missing': missing, 'isolated': is_isolated()}


def hide(tokens):
    _design, occurrences, bodies, missing = _targets(tokens, 'hide')
    for occ in occurrences:
        occ.isLightBulbOn = False
    for body in bodies:
        _set_body(body, False)
    return {'changed': len(occurrences) + len(bodies), 'missing': missing, 'isolated': is_isolated()}


def _capture(design):
    states = []
    root = design.rootComponent
    all_occurrences = root.allOccurrences
    for index in range(all_occurrences.count):
        occ = all_occurrences.item(index)
        states.append((occ.entityToken, bool(occ.isLightBulbOn)))
    components = design.allComponents
    for index in range(components.count):
        component = components.item(index)
        try:
            states.append((('folder', component.entityToken), bool(component.isBodiesFolderLightBulbOn)))
        except Exception:
            pass
        for body_index in range(component.bRepBodies.count):
            body = component.bRepBodies.item(body_index)
            states.append((body.entityToken, bool(body.isLightBulbOn)))
    return states


def isolate(tokens):
    design, occurrences, bodies, missing = _targets(tokens, 'isolate')

    keep_occ = {d.occ_key(occ) for occ in occurrences}
    keep_body = {d.body_key(body) for body in bodies}
    path_occ = set()

    def add_path(occ):
        while occ:
            path_occ.add(d.occ_key(occ))
            occ = occ.assemblyContext

    for occ in occurrences:
        add_path(occ.assemblyContext)
    for body in bodies:
        add_path(body.assemblyContext)

    doc_key = _doc_key(design)
    if doc_key not in _snapshots:
        _snapshots[doc_key] = _capture(design)

    root = design.rootComponent
    if keep_body:
        try:
            root.isBodiesFolderLightBulbOn = True
        except Exception:
            pass
    for index in range(root.bRepBodies.count):
        body = root.bRepBodies.item(index)
        _set_body(body, d.body_key(body) in keep_body)

    hidden = 0

    def apply(collection):
        nonlocal hidden
        for index in range(collection.count):
            occ = collection.item(index)
            key = d.occ_key(occ)
            if key in keep_occ:
                occ.isLightBulbOn = True
            elif key in path_occ:
                occ.isLightBulbOn = True
                for body_index in range(occ.bRepBodies.count):
                    body = occ.bRepBodies.item(body_index)
                    _set_body(body, d.body_key(body) in keep_body)
                apply(occ.childOccurrences)
            else:
                if occ.isLightBulbOn:
                    occ.isLightBulbOn = False
                    hidden += 1

    apply(root.occurrences)
    return {'changed': hidden, 'missing': missing, 'isolated': True}


def restore_all():
    design = d.require_design()
    restored = 0
    snapshot = _snapshots.pop(_doc_key(design), None)
    if snapshot is not None:
        for token, on in snapshot:
            if isinstance(token, tuple):
                component = adsk.fusion.Component.cast(d.resolve(token[1], design))
                if component:
                    try:
                        component.isBodiesFolderLightBulbOn = on
                    except Exception:
                        pass
                continue
            entity = d.resolve(token, design)
            if entity is None:
                continue
            try:
                if entity.isLightBulbOn != on:
                    entity.isLightBulbOn = on
                    restored += 1
            except Exception:
                continue
        return {'changed': restored, 'missing': 0, 'isolated': False}

    all_occurrences = design.rootComponent.allOccurrences
    for index in range(all_occurrences.count):
        occ = all_occurrences.item(index)
        if not occ.isLightBulbOn:
            occ.isLightBulbOn = True
            restored += 1
    components = design.allComponents
    for index in range(components.count):
        component = components.item(index)
        try:
            component.isBodiesFolderLightBulbOn = True
        except Exception:
            pass
        for body_index in range(component.bRepBodies.count):
            body = component.bRepBodies.item(body_index)
            if not body.isLightBulbOn:
                body.isLightBulbOn = True
                restored += 1
    return {'changed': restored, 'missing': 0, 'isolated': False}


def reset():
    _snapshots.clear()
