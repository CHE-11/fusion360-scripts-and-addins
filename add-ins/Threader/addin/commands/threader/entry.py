"""Threader palette command and message router."""

import json
import os
import subprocess
import sys
import traceback

import adsk.core

from ... import config
from ...lib import fusionAddInUtils as futil
from . import geometry
from . import recipes
from . import standards

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_PalleteShow'
CMD_NAME = 'Threader'
CMD_DESCRIPTION = 'Parametric threads and heat-set inserts for 3D printing'
PALETTE_NAME = 'Threader'
PALETTE_ID = config.PALETTE_ID
PALETTE_DOCKING = adsk.core.PaletteDockingStates.PaletteDockStateRight
PALETTE_WIDTH = 420
PALETTE_HEIGHT = 760
IS_PROMOTED = True

WORKSPACE_ID = config.WORKSPACE_ID
PANEL_ID = config.PANEL_ID
COMMAND_BESIDE_ID = config.COMMAND_BESIDE_ID
RIBBON_TABS = config.RIBBON_TABS
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

local_handlers = []


def _toolbar_tab(tab_id):
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    if workspace:
        tab = workspace.toolbarTabs.itemById(tab_id)
        if tab:
            return tab
    all_tabs = getattr(ui, 'allToolbarTabs', None)
    if all_tabs:
        return all_tabs.itemById(tab_id)
    return None


def _place_on_tab(cmd_def, tab_id, panel_id, after_panel_id):
    """Add a Threader control to the shared CHE solid panel."""
    tab = _toolbar_tab(tab_id)
    if not tab:
        futil.log(f'Threader: toolbar tab {tab_id} was not found.')
        return
    panel = tab.toolbarPanels.itemById(panel_id)
    if not panel:
        try:
            panel = tab.toolbarPanels.add(panel_id, config.RIBBON_PANEL_NAME, after_panel_id, False)
        except Exception:
            futil.log(f'Threader: could not place a panel after {after_panel_id} on {tab_id}.')
            try:
                panel = tab.toolbarPanels.add(panel_id, config.RIBBON_PANEL_NAME, '', False)
            except Exception:
                futil.log(f'Threader: could not create panel on {tab_id}: {traceback.format_exc()}')
                return
    if panel.controls.itemById(CMD_ID):
        return
    control = panel.controls.addCommand(cmd_def)
    control.isPromoted = IS_PROMOTED
    control.isPromotedByDefault = IS_PROMOTED


def _remove_tab_panel(tab_id, panel_id):
    tab = _toolbar_tab(tab_id)
    if not tab:
        return
    panel = tab.toolbarPanels.itemById(panel_id)
    if not panel:
        return
    control = panel.controls.itemById(CMD_ID)
    if control:
        control.deleteMe()
    if panel.controls.count == 0:
        panel.deleteMe()


def start():
    existing = ui.commandDefinitions.itemById(CMD_ID)
    if existing:
        existing.deleteMe()
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_DESCRIPTION, ICON_FOLDER)
    futil.add_handler(cmd_def.commandCreated, command_created)
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    control = panel.controls.itemById(CMD_ID) if panel else None
    if panel and not control:
        control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)
    if control:
        control.isPromoted = IS_PROMOTED

    for tab_id, panel_id, after_panel_id in RIBBON_TABS:
        try:
            _place_on_tab(cmd_def, tab_id, panel_id, after_panel_id)
        except Exception:
            futil.log(f'Threader: could not add the command to {tab_id}: {traceback.format_exc()}')

    try:
        futil.add_handler(app.documentActivated, on_document_activated)
    except Exception:
        futil.log(f'Could not attach documentActivated handler: {traceback.format_exc()}')

    selection_event = getattr(ui, 'activeSelectionChanged', None)
    if selection_event is not None:
        try:
            futil.add_handler(selection_event, on_selection_changed)
        except Exception:
            futil.log(f'Could not attach activeSelectionChanged handler: {traceback.format_exc()}')


def stop():
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID) if workspace else None
    command_control = panel.controls.itemById(CMD_ID) if panel else None
    if command_control:
        command_control.deleteMe()
    for tab_id, panel_id, _after_panel_id in RIBBON_TABS:
        try:
            _remove_tab_panel(tab_id, panel_id)
        except Exception:
            futil.log(f'Threader: could not remove the panel from {tab_id}: {traceback.format_exc()}')
    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    palette = ui.palettes.itemById(PALETTE_ID)
    if command_definition:
        command_definition.deleteMe()
    if palette:
        palette.deleteMe()


def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


def command_execute(args: adsk.core.CommandEventArgs):
    palettes = ui.palettes
    palette = palettes.itemById(PALETTE_ID)
    if palette is None:
        palette = palettes.add(
            id=PALETTE_ID,
            name=PALETTE_NAME,
            htmlFileURL=_palette_url(),
            isVisible=True,
            showCloseButton=False,
            isResizable=True,
            width=PALETTE_WIDTH,
            height=PALETTE_HEIGHT,
            useNewWebBrowser=True,
        )
        futil.add_handler(palette.closed, palette_closed)
        futil.add_handler(palette.incomingFromHTML, palette_incoming)
    palette.width = PALETTE_WIDTH
    palette.height = PALETTE_HEIGHT
    palette.dockingState = PALETTE_DOCKING
    palette.isVisible = True


def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []


def palette_closed(args: adsk.core.UserInterfaceGeneralEventArgs):
    futil.log('Threader palette closed.')


def palette_incoming(html_args: adsk.core.HTMLEventArgs):
    message_data = None
    if html_args.data:
        try:
            message_data = json.loads(html_args.data)
        except Exception:
            message_data = html_args.data
    try:
        html_args.returnData = route_message(html_args.action, message_data)
    except (geometry.GeometryError, ValueError) as exc:
        futil.log(f"Rejected '{html_args.action}': {exc}")
        html_args.returnData = _err(exc)
    except Exception:
        futil.log(f"Error handling '{html_args.action}': {traceback.format_exc()}")
        html_args.returnData = _err(traceback.format_exc())


def route_message(action, data):
    payload = data if isinstance(data, dict) else {}
    if action == 'ready':
        return _ok(_document_context())
    if action == 'palette:minimize':
        return _ok(_minimize_palette())
    if action == 'jsLog':
        _handle_js_log(data)
        return _ok()
    if action == 'clipboard:copy':
        text = payload.get('text')
        if not isinstance(text, str):
            return _err('clipboard:copy expects text')
        _copy_to_clipboard(text)
        return _ok({'copied': True})
    if action == 'face:readSelection':
        return _ok(geometry.read_selection())
    if action == 'standards:list':
        return _ok(standards.catalog())
    if action == 'thread:preview':
        return _ok(recipes.preview_thread(payload))
    if action == 'thread:create':
        return _ok(recipes.create_thread(payload))
    if action == 'thread:list':
        return _ok(recipes.list_features())
    if action == 'thread:update':
        return _ok(recipes.update_thread(payload))
    if action == 'thread:nudge':
        return _ok(recipes.nudge_thread(payload))
    if action == 'thread:delete':
        return _ok(recipes.delete_feature(payload))
    if action == 'insert:preview':
        return _ok(_insert_preview(payload))
    if action == 'insert:create':
        return _ok(recipes.create_insert(payload))
    if action == 'insert:list':
        return _ok(recipes.list_features())
    if action == 'insert:update':
        return _ok(recipes.update_insert(payload))
    if action == 'insert:nudge':
        return _ok(recipes.nudge_insert(payload))
    if action == 'insert:delete':
        return _ok(recipes.delete_feature(payload))
    return _err(f'Unknown action: {action}')


def _insert_preview(payload):
    size = payload.get('size') or 'M3'
    preset = standards.insert_by_size(size) if size != 'Custom' else None
    hole = payload.get('holeMm', preset['hole_mm'] if preset else None)
    depth = payload.get('depthMm', preset['depth_mm'] if preset else None)
    chamfer = payload.get('chamferMm', preset['chamfer_mm'] if preset else None)
    notes = [
        'A tight insert means the hole was small. Too tight opens it by 0.10 mm.',
        'Melt the insert in with a soldering iron. Do not force it in cold.',
    ]
    return {
        'size': size,
        'holeMm': hole,
        'depthMm': depth,
        'chamferMm': chamfer,
        'notes': notes,
        'warnings': [],
    }


def on_document_activated(args):
    geometry.clear_held_selection()
    context = _document_context()
    _push('docActivated', context)
    _push('selectionChanged', {**geometry.empty_selection(), 'document': context})


def on_selection_changed(args):
    try:
        selection = geometry.read_selection()
    except Exception:
        futil.log(f'Could not read the selection: {traceback.format_exc()}')
        selection = geometry.empty_selection()
    selection['document'] = _document_context()
    _push('selectionChanged', selection)


def _push(action, payload):
    palette = ui.palettes.itemById(PALETTE_ID)
    if not palette:
        return
    try:
        palette.sendInfoToHTML(action, json.dumps(payload))
    except Exception:
        futil.log(f'Could not push {action}: {traceback.format_exc()}')


def _minimize_palette():
    palette = ui.palettes.itemById(PALETTE_ID)
    if palette:
        palette.isVisible = False
    return {'minimized': True}


def _palette_url():
    if config.REACT_DEV:
        return config.DEV_PALETTE_URL
    url = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', 'html', 'index.html')
    return url.replace('\\', '/')


def _active_doc_name():
    try:
        document = app.activeDocument
        return document.name if document else ''
    except Exception:
        return ''


def _document_context():
    return {
        'doc': _active_doc_name(),
        'standards': standards.catalog(),
    }


def _copy_to_clipboard(text):
    """Write text to the OS clipboard. The palette webview cannot."""
    if sys.platform == 'win32':
        clip = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'clip.exe')
        subprocess.run(
            [clip],
            input=text.encode('utf-16le'),
            check=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        return
    if sys.platform == 'darwin':
        subprocess.run(['pbcopy'], input=text.encode('utf-8'), check=True)
        return
    raise ValueError(f'Clipboard copy is not supported on {sys.platform}')


def _handle_js_log(message_data):
    try:
        if isinstance(message_data, dict):
            level = message_data.get('level', 'info')
            message = message_data.get('message', '')
            extra = message_data.get('extra', None)
            futil.log(f"[palette.js:{level}] {message} {json.dumps(extra) if extra is not None else ''}".strip())
        else:
            futil.log(f'[palette.js] {message_data}')
    except Exception:
        futil.log(f'Error handling jsLog: {traceback.format_exc()}')


def _ok(data=None):
    return json.dumps({'ok': True, 'data': data})


def _err(message):
    return json.dumps({'ok': False, 'error': str(message)})
