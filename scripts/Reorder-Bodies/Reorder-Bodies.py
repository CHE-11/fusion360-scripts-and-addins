"""
Sort bodies A to Z in the Fusion browser, inside the folder each one is in.

The public API has no body groups and no browser reorder, so this drives
Fusion's own group commands through text commands. Two Fusion behaviours
make it work:

- Move to Group only accepts a preselected target while that group is empty,
  and it keeps the bodies' existing browser order.
- New groups are added to the browser in creation order.

So every body first goes into its own new staging group, in A-Z order. Bodies
from one of your groups then move back into that group together, which is
empty by then. Finally every staging group is deleted with "Expand contents",
which drops the bodies that started in the root Bodies folder back there in
the staging order.

Geometry is not changed.
"""

import json
import re
import time
import traceback

import adsk.core
import adsk.fusion

STAGING_PREFIX = '_reorder_'
TITLE = 'Reorder Bodies'


def run(context):
    ui = None
    app = adsk.core.Application.get()
    try:
        ui = app.userInterface
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox('No active Fusion design found.', TITLE)
            return

        component = design.activeComponent
        occurrence = design.activeOccurrence
        bodies = [_in_context(body, occurrence) for body in component.bRepBodies]
        if len(bodies) < 2:
            ui.messageBox('{} needs at least two bodies to sort.'.format(component.name), TITLE)
            return

        ids = _Ids(app)
        layout = ids.layout(bodies)

        leftovers = [
            name for name in (ids.user_name(group_id) for group_id in ids.group_ids(layout))
            if name.startswith(STAGING_PREFIX)
        ]
        if leftovers:
            ui.messageBox(
                '{} already has groups from an earlier run: {}.\n\n'
                'Drag their bodies back where they belong and delete those groups, '
                'then run the script again.'.format(component.name, ', '.join(leftovers)),
                TITLE,
            )
            return

        plan = []
        skipped = []
        for folder_id, members in layout.folders.items():
            if len(members) < 2:
                continue
            is_root = folder_id == layout.bodies_id
            label = 'Bodies' if is_root else ids.user_name(folder_id)
            if not is_root:
                member_ids = set(entity_id for entity_id, _body in members)
                others = [child for child in ids.group_children(folder_id) if child not in member_ids]
                if others:
                    skipped.append('{} (it has groups inside it)'.format(label))
                    continue
            ordered = [
                pair for _key, _index, pair in sorted(
                    (_natural_key(pair[1].name), index, pair) for index, pair in enumerate(members)
                )
            ]
            plan.append(_FolderPlan(folder_id, label, is_root, ordered))

        if not plan:
            message = 'Nothing to sort in {}.'.format(component.name)
            if skipped:
                message += '\n\nSkipped: ' + ', '.join(skipped)
            ui.messageBox(message, TITLE)
            return

        body_total = sum(len(folder.ordered) for folder in plan)
        answer = ui.messageBox(
            'Sort {} bodies A to Z in {}?\n\n'
            'Folders: {}\n\n'
            'Each body stays in the folder it is in now. At the end Fusion asks once how to '
            'delete the temporary groups. Choose "Expand contents".{}'.format(
                body_total,
                component.name,
                ', '.join(folder.label for folder in plan),
                '\n\nSkipped: ' + ', '.join(skipped) if skipped else '',
            ),
            TITLE,
            adsk.core.MessageBoxButtonTypes.YesNoButtonType,
            adsk.core.MessageBoxIconTypes.QuestionIconType,
        )
        if answer != adsk.core.DialogResults.DialogYes:
            return

        body_count_before = component.bRepBodies.count
        staging = []
        progress = ui.createProgressDialog()
        progress.isCancelButtonShown = False
        progress.show(TITLE, 'Staging %v of %m', 0, body_total)
        try:
            step = 0
            for folder in plan:
                for _entity_id, body in folder.ordered:
                    progress.progressValue = step
                    progress.message = 'Staging {}: %v of %m'.format(body.name)
                    adsk.doEvents()
                    step += 1
                    name = '{}{:02d}'.format(STAGING_PREFIX, len(staging) + 1)
                    try:
                        stage_id = _create_group(app, ids, layout, name)
                        staging.append(stage_id)
                        _move_all_to_group(app, ids, [body], ids.group_path(layout, stage_id), stage_id)
                    except Exception as error:
                        raise RuntimeError('Stopped while moving {} into {}: {}'.format(body.name, name, error))

                if not folder.is_root:
                    progress.message = 'Moving bodies back into {}'.format(folder.label)
                    adsk.doEvents()
                    bodies_in_order = [body for _entity_id, body in folder.ordered]
                    try:
                        _move_all_to_group(
                            app, ids, bodies_in_order, ids.group_path(layout, folder.folder_id), folder.folder_id,
                        )
                    except Exception as error:
                        raise RuntimeError('Stopped while moving bodies back into {}: {}'.format(folder.label, error))
        finally:
            progress.hide()
            ui.activeSelections.clear()

        not_deleted = _delete_staging_groups(app, ids, layout, staging)

        lines = []
        lost = body_count_before - component.bRepBodies.count
        if lost > 0:
            lines.append(
                '{} bodies were deleted along with the temporary groups. '
                'Press Ctrl+Z to bring them back, then run the script again and choose '
                '"Expand contents".'.format(lost)
            )
        elif not_deleted:
            lines.append(
                'These temporary groups are still there: {}.\n\n'
                'Delete them and choose "Expand contents" to put their bodies back in Bodies.'.format(
                    ', '.join(not_deleted),
                )
            )
        else:
            lines.append('Sorted {} bodies A to Z.'.format(body_total))

        for folder in plan:
            if folder.is_root:
                continue
            wanted = [body.name for _entity_id, body in folder.ordered]
            actual = ids.group_body_names(folder.folder_id)
            if actual != wanted:
                lines.append('{} ended up in this order:\n{}'.format(folder.label, '\n'.join(actual)))
        if skipped:
            lines.append('Skipped: ' + ', '.join(skipped))
        ui.messageBox('\n\n'.join(lines), TITLE)

    except Exception:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()), TITLE)


class _Layout:
    def __init__(self, component_path, bodies_id, groups_id):
        self.component_path = component_path
        self.bodies_id = bodies_id
        self.groups_id = groups_id
        self.folders = {}


class _FolderPlan:
    def __init__(self, folder_id, label, is_root, ordered):
        self.folder_id = folder_id
        self.label = label
        self.is_root = is_root
        self.ordered = ordered


class _Ids:
    def __init__(self, app):
        self.app = app

    def properties(self, entity_id):
        raw = self.app.executeTextCommand('PEntity.Properties {}'.format(int(entity_id)))
        return json.loads(_json_object(raw))

    def user_name(self, entity_id):
        try:
            raw = self.app.executeTextCommand('PInterfaces.GetUserName {}'.format(int(entity_id))) or ''
        except Exception:
            raw = ''
        name = raw.strip().strip('"')
        return name or self.properties(entity_id).get('userName', '')

    def body_path(self, body):
        selections = self.app.userInterface.activeSelections
        selections.clear()
        if not selections.add(body):
            raise RuntimeError('could not select {}'.format(body.name))
        listing = self.app.executeTextCommand('Selections.List') or ''
        selections.clear()
        lines = [line.strip() for line in listing.splitlines() if line.strip()]
        if not lines:
            raise RuntimeError('could not read the path of {}'.format(body.name))
        return [int(part) for part in lines[-1].split(':')]

    def layout(self, bodies):
        """Group the bodies by the folder they sit in: the Bodies folder or a body group."""
        layout = None
        for body in bodies:
            parts = self.body_path(body)
            entity_id = parts[-1]
            props = self.properties(entity_id)
            if layout is None:
                layout = self._component_layout(parts, props, body)
            folder_id = _entry_id(props.get('rGroupParent'))
            if folder_id is None or folder_id == layout.bodies_id or not self.is_group(folder_id):
                folder_id = layout.bodies_id
            layout.folders.setdefault(folder_id, []).append((entity_id, body))
        return layout

    def _component_layout(self, parts, body_props, body):
        current = body_props
        for _depth in range(10):
            parent_id = _entry_id(current.get('rParent'))
            if parent_id is None:
                break
            current = self.properties(parent_id)
            bodies_id = _entry_id(current.get('rBodies'))
            groups_id = _entry_id(current.get('rSurfaceGroups'))
            if bodies_id is not None and groups_id is not None:
                if parent_id not in parts:
                    break
                component_path = ':'.join(str(part) for part in parts[:parts.index(parent_id) + 1])
                return _Layout(component_path, bodies_id, groups_id)
        raise RuntimeError('Could not find the component that owns {}.'.format(body.name))

    def is_group(self, entity_id):
        try:
            interfaces = self.app.executeTextCommand('PEntity.GetEntityInterfaces {}'.format(int(entity_id))) or ''
        except Exception:
            return False
        return re.search(r'(^|[^A-Za-z0-9_])SurfaceGroup([^A-Za-z0-9_]|$)', interfaces) is not None

    def group_ids(self, layout):
        return [_entry_id(entry) for entry in _as_entries(self.properties(layout.groups_id).get('children'))]

    def group_path(self, layout, group_id):
        chain = []
        current = group_id
        while current is not None and current != layout.groups_id and len(chain) < 20:
            chain.append(current)
            current = _entry_id(self.properties(current).get('rParent'))
        if current != layout.groups_id:
            raise RuntimeError('Could not build the selection path for group {}.'.format(group_id))
        return '{}:{}:{}'.format(layout.component_path, layout.groups_id, ':'.join(str(part) for part in reversed(chain)))

    def group_children(self, group_id):
        props = self.properties(group_id)
        entries = _as_entries(props.get('groupChildren')) or _as_entries(props.get('children'))
        return [entity_id for entity_id in (_entry_id(entry) for entry in entries) if entity_id is not None]

    def group_size(self, group_id):
        return len(self.group_children(group_id))

    def group_body_names(self, group_id):
        return [self.user_name(entity_id) for entity_id in self.group_children(group_id)]


def _create_group(app, ids, layout, name):
    before = set(ids.group_ids(layout))
    selections = app.userInterface.activeSelections
    selections.clear()
    app.executeTextCommand('Selections.Add {}:{}'.format(layout.component_path, layout.bodies_id))
    app.executeTextCommand('Commands.Start FusionCreateSurfaceGroupCommand')
    selections.clear()

    created = [group_id for group_id in ids.group_ids(layout) if group_id not in before]
    if not created:
        raise RuntimeError('Fusion did not create the {} group.'.format(name))
    group_id = created[-1]
    app.executeTextCommand('PInterfaces.Rename {} {}'.format(group_id, name))
    actual = ids.user_name(group_id)
    if actual != name:
        raise RuntimeError('Fusion created the group but named it "{}" instead of {}.'.format(actual, name))
    if ids.group_size(group_id) != 0:
        raise RuntimeError('The new {} group is not empty. Undo it and try again.'.format(name))
    return group_id


def _move_all_to_group(app, ids, bodies, group_path, group_id):
    ui = app.userInterface
    if ids.group_size(group_id) != 0:
        raise RuntimeError('the target group is not empty')
    _wait_until_idle(ui)
    notes = []

    selections = ui.activeSelections
    selections.clear()
    for body in bodies:
        if not selections.add(body):
            raise RuntimeError('Could not select {}.'.format(body.name))
    app.executeTextCommand('Selections.Add {}'.format(group_path))
    notes.append('selected {} items'.format(selections.count))

    try:
        app.executeTextCommand('Commands.Start FusionMoveToSurfaceGroupCommand')
        notes.append('start: ok, active command {}'.format(ui.activeCommand))
    except Exception as error:
        notes.append('start: {}'.format(error))

    if ids.group_size(group_id) != len(bodies):
        try:
            app.executeTextCommand('NuCommands.CommitCmd')
            notes.append('commit: ok')
        except Exception as error:
            notes.append('commit: {}'.format(error))

    deadline = time.time() + 5
    while ids.group_size(group_id) != len(bodies) and time.time() < deadline:
        _pause(0.1)

    if ui.activeCommand == 'FusionMoveToSurfaceGroupCommand':
        ui.terminateActiveCommand()
    selections.clear()
    _wait_until_idle(ui)

    size = ids.group_size(group_id)
    if size != len(bodies):
        raise RuntimeError('Fusion moved {} of {} bodies into the group. {}'.format(
            size, len(bodies), '; '.join(notes),
        ))


def _delete_staging_groups(app, ids, layout, group_ids):
    """Delete every staging group in one Delete so Fusion asks about their contents only once."""
    ui = app.userInterface
    if not group_ids:
        return []
    crowded = [ids.user_name(group_id) for group_id in group_ids if ids.group_size(group_id) > 1]
    if crowded:
        raise RuntimeError('These temporary groups hold more than one body: {}'.format(', '.join(crowded)))

    _wait_until_idle(ui)
    paths = [ids.group_path(layout, group_id) for group_id in group_ids]
    ui.activeSelections.clear()
    for path in paths:
        app.executeTextCommand('Selections.Add {}'.format(path))
    listing = app.executeTextCommand('Selections.List') or ''
    selected = [line.strip() for line in listing.splitlines() if line.strip()]
    if sorted(selected) != sorted(paths):
        ui.activeSelections.clear()
        raise RuntimeError('Could not select only the temporary groups.')

    try:
        app.executeTextCommand('Commands.Start FusionDeleteCommand')
    finally:
        _pause(0.1)
        if set(ids.group_ids(layout)).intersection(group_ids) and ui.activeCommand == 'FusionDeleteCommand':
            try:
                app.executeTextCommand('NuCommands.CommitCmd')
            except Exception:
                pass
        if ui.activeCommand == 'FusionDeleteCommand':
            ui.terminateActiveCommand()
        ui.activeSelections.clear()
        _wait_until_idle(ui)

    remaining = set(ids.group_ids(layout))
    return [ids.user_name(group_id) for group_id in group_ids if group_id in remaining]


def _wait_until_idle(ui, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        adsk.doEvents()
        if ui.activeCommand in ('', 'SelectCommand'):
            return
        time.sleep(0.05)


def _pause(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        adsk.doEvents()
        time.sleep(0.02)


def _in_context(body, occurrence):
    if occurrence is None:
        return body
    return body.createForAssemblyContext(occurrence)


def _natural_key(name):
    parts = re.split(r'(\d+)', (name or '').casefold())
    key = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
        elif part:
            key.append((1, part))
    return key


def _json_object(raw):
    text = (raw or '').strip()
    start = text.find('{')
    end = text.rfind('}')
    if start < 0 or end < start:
        raise RuntimeError('Unexpected entity properties: {}'.format(text[:200]))
    return text[start:end + 1]


def _as_entries(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        if 'entityId' in value:
            return [value]
        return [value[key] for key in value if isinstance(value[key], dict)]
    return []


def _entry_id(entry):
    if not isinstance(entry, dict):
        return None
    try:
        return int(entry.get('entityId'))
    except (TypeError, ValueError):
        return None
