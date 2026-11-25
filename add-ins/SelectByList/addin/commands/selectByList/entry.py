"""Select By List palette command and message router."""

import json
import os
import time
import traceback

import adsk.core

from ... import config
from ...lib import fusionAddInUtils as futil
from . import design
from . import operations
from . import visibility

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_PaletteShow'
CMD_NAME = 'Select By List'
CMD_DESCRIPTION = 'Find, sort, select, and operate on components, bodies, and faces by name'
PALETTE_NAME = 'Select By List'
PALETTE_ID = config.PALETTE_ID
PALETTE_DOCKING = adsk.core.PaletteDockingStates.PaletteDockStateRight
PALETTE_WIDTH = 380
PALETTE_HEIGHT = 760
IS_PROMOTED = True

WORKSPACE_ID = config.WORKSPACE_ID
PANEL_ID = config.PANEL_ID
COMMAND_BESIDE_ID = config.COMMAND_BESIDE_ID
RIBBON_TABS = config.RIBBON_TABS
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# Commands that never change the model, so finishing them should not refresh the list.
QUIET_COMMANDS = {
    CMD_ID,
    'SelectCommand',
    'CommitCommand',
    'PanCommand',
    'OrbitCommand',
    'ZoomCommand',
    'FitCommand',
    'ViewCubeCommand',
}

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
    """Add the command to the shared CHE panel on a Design toolbar tab."""
    tab = _toolbar_tab(tab_id)
    if not tab:
        futil.log(f'Select By List: toolbar tab {tab_id} was not found.')
        return
    panel = tab.toolbarPanels.itemById(panel_id)
    if not panel:
        try:
            panel = tab.toolbarPanels.add(panel_id, config.RIBBON_PANEL_NAME, after_panel_id, False)
        except Exception:
            futil.log(f'Select By List: could not place a panel after {after_panel_id} on {tab_id}.')
            try:
                panel = tab.toolbarPanels.add(panel_id, config.RIBBON_PANEL_NAME, '', False)
            except Exception:
                futil.log(f'Select By List: could not create panel on {tab_id}: {traceback.format_exc()}')
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
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_DESCRIPTION, ICON_FOLDER)
    futil.add_handler(cmd_def.commandCreated, command_created)
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)
    control.isPromoted = IS_PROMOTED

    for tab_id, panel_id, after_panel_id in RIBBON_TABS:
        try:
            _place_on_tab(cmd_def, tab_id, panel_id, after_panel_id)
        except Exception:
            futil.log(f'Select By List: could not add the command to {tab_id}: {traceback.format_exc()}')

    operations.start()

    events = (
        (app.documentActivated, on_document_changed, 'documentActivated'),
        (app.documentOpened, on_document_changed, 'documentOpened'),
        (app.documentClosed, on_document_changed, 'documentClosed'),
        (ui.commandTerminated, on_command_terminated, 'commandTerminated'),
        (ui.activeSelectionChanged, on_selection_changed, 'activeSelectionChanged'),
    )
    for event, callback, name in events:
        try:
            futil.add_handler(event, callback, name=name)
        except Exception:
            futil.log(f'Select By List: could not attach {name}: {traceback.format_exc()}')


def stop():
    try:
        operations.stop()
        visibility.reset()
    except Exception:
        futil.log(f'Select By List: cleanup failed: {traceback.format_exc()}')
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID) if workspace else None
    command_control = panel.controls.itemById(CMD_ID) if panel else None
    if command_control:
        command_control.deleteMe()
    for tab_id, panel_id, _after_panel_id in RIBBON_TABS:
        try:
            _remove_tab_panel(tab_id, panel_id)
        except Exception:
            futil.log(f'Select By List: could not remove the panel from {tab_id}: {traceback.format_exc()}')
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
            showCloseButton=True,
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
    _push('themeChanged', {'theme': design.ui_theme()})
    _push('designChanged', {'reason': 'shown'})


def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []


def palette_closed(args: adsk.core.UserInterfaceGeneralEventArgs):
    futil.log('Select By List palette closed.')


def palette_incoming(html_args: adsk.core.HTMLEventArgs):
    message_data = None
    if html_args.data:
        try:
            message_data = json.loads(html_args.data)
        except Exception:
            message_data = html_args.data
    started = time.perf_counter()
    try:
        html_args.returnData = route_message(html_args.action, message_data)
    except ValueError as exc:
        futil.log(f"Rejected '{html_args.action}': {exc}")
        html_args.returnData = _err(exc)
    except Exception:
        futil.log(f"Error handling '{html_args.action}': {traceback.format_exc()}")
        html_args.returnData = _err('Something went wrong in Fusion. Details are in the Text Commands window.')
    elapsed = time.perf_counter() - started
    if elapsed > 1:
        futil.log(f"Select By List: '{html_args.action}' took {elapsed:.1f}s")


def _tokens(payload):
    tokens = payload.get('tokens')
    if not isinstance(tokens, list):
        return []
    return [token for token in tokens if isinstance(token, str) and token]


def route_message(action, data):
    payload = data if isinstance(data, dict) else {}
    if action == 'ready':
        result = design.ready(payload)
        result['lastOp'] = operations.last_op()
        result['isolated'] = visibility.is_isolated()
        return _ok(result)
    if action == 'items:list':
        return _ok(design.list_items(payload))
    if action == 'faces:list':
        return _ok(design.list_items({'mode': 'face', 'tokens': _tokens(payload)}))
    if action == 'select:viewport':
        return _ok(design.select_in_viewport(_tokens(payload)))
    if action == 'selection:get':
        return _ok(design.viewport_selection())
    if action == 'vis:show':
        return _ok(visibility.show(_tokens(payload)))
    if action == 'vis:hide':
        return _ok(visibility.hide(_tokens(payload)))
    if action == 'vis:isolate':
        return _ok(visibility.isolate(_tokens(payload)))
    if action == 'vis:restoreAll':
        return _ok(visibility.restore_all())
    if action == 'item:rename':
        return _ok(design.rename(payload))
    if action == 'op:run':
        return _ok(operations.run({'op': payload.get('op'), 'tokens': _tokens(payload)}))
    if action == 'op:repeat':
        return _ok(operations.repeat_last())
    if action == 'palette:close':
        palette = ui.palettes.itemById(PALETTE_ID)
        if palette:
            palette.isVisible = False
        return _ok({'closed': True})
    if action == 'jsLog':
        _handle_js_log(payload)
        return _ok()
    return _err(f'Unknown action: {action}')


def _palette_visible():
    palette = ui.palettes.itemById(PALETTE_ID)
    return bool(palette and palette.isVisible)


def on_document_changed(args):
    if not _palette_visible():
        return
    _push('themeChanged', {'theme': design.ui_theme()})
    if design.active_design():
        _push('designChanged', {'reason': 'document'})
    else:
        _push('noDocument', {})


def on_command_terminated(args):
    if not _palette_visible():
        return
    try:
        if args.terminationReason != adsk.core.CommandTerminationReason.CompletedTerminationReason:
            return
        if args.commandId in QUIET_COMMANDS:
            return
    except Exception:
        return
    _push('designChanged', {'reason': 'command', 'commandId': args.commandId})


def on_selection_changed(args):
    if not _palette_visible():
        return
    _push('viewportSelectionChanged', design.viewport_selection())


def _push(action, payload):
    palette = ui.palettes.itemById(PALETTE_ID)
    if not palette:
        return
    try:
        palette.sendInfoToHTML(action, json.dumps(payload))
    except Exception:
        futil.log(f'Could not push {action}: {traceback.format_exc()}')


def _palette_url():
    if config.REACT_DEV:
        return config.DEV_PALETTE_URL
    url = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', 'html', 'index.html')
    return url.replace('\\', '/')


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
