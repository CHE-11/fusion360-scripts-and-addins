"""CONstrainer palette command and message router."""

import json
import os
import subprocess
import sys
import traceback

import adsk.core

from ... import config
from ...lib import fusionAddInUtils as futil
from . import assembly_constraints
from . import design_utils
from . import sketch_constraints

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_PalleteShow'
CMD_NAME = 'CONstrainer'
CMD_DESCRIPTION = 'Create and manage sketch constraints and assembly constraints'
PALETTE_NAME = 'CONstrainer'
PALETTE_ID = config.PALETTE_ID
PALETTE_DOCKING = adsk.core.PaletteDockingStates.PaletteDockStateRight
PALETTE_WIDTH = 420
PALETTE_HEIGHT = 720
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
    """Add a CONstrainer panel to a Design toolbar tab and pin the command on it."""
    tab = _toolbar_tab(tab_id)
    if not tab:
        futil.log(f'CONstrainer: toolbar tab {tab_id} was not found.')
        return
    panel = tab.toolbarPanels.itemById(panel_id)
    if not panel:
        try:
            panel = tab.toolbarPanels.add(panel_id, config.RIBBON_PANEL_NAME, after_panel_id, False)
        except Exception:
            futil.log(f'CONstrainer: could not place a panel after {after_panel_id} on {tab_id}.')
            try:
                panel = tab.toolbarPanels.add(panel_id, config.RIBBON_PANEL_NAME, '', False)
            except Exception:
                futil.log(f'CONstrainer: could not create panel on {tab_id}: {traceback.format_exc()}')
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
            futil.log(f'CONstrainer: could not add the command to {tab_id}: {traceback.format_exc()}')

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
    try:
        sketch_constraints.clear_highlight()
        assembly_constraints.clear_highlight()
    except Exception:
        pass
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID) if workspace else None
    command_control = panel.controls.itemById(CMD_ID) if panel else None
    if command_control:
        command_control.deleteMe()
    for tab_id, panel_id, _after_panel_id in RIBBON_TABS:
        try:
            _remove_tab_panel(tab_id, panel_id)
        except Exception:
            futil.log(f'CONstrainer: could not remove the panel from {tab_id}: {traceback.format_exc()}')
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
    try:
        sketch_constraints.clear_highlight()
        assembly_constraints.clear_highlight()
    except Exception:
        pass
    futil.log('CONstrainer palette closed.')


def palette_incoming(html_args: adsk.core.HTMLEventArgs):
    message_data = None
    if html_args.data:
        try:
            message_data = json.loads(html_args.data)
        except Exception:
            message_data = html_args.data
    try:
        html_args.returnData = route_message(html_args.action, message_data)
    except ValueError as exc:
        futil.log(f"Rejected '{html_args.action}': {exc}")
        html_args.returnData = _err(exc)
    except Exception:
        futil.log(f"Error handling '{html_args.action}': {traceback.format_exc()}")
        html_args.returnData = _err(traceback.format_exc())


def route_message(action, data):
    if action == 'ready':
        return _ok(_document_context())
    if action == 'palette:minimize':
        return _ok(_minimize_palette())
    if action == 'jsLog':
        _handle_js_log(data)
        return _ok()
    if action == 'clipboard:copy':
        text = data.get('text') if isinstance(data, dict) else None
        if not isinstance(text, str):
            return _err('clipboard:copy expects text')
        _copy_to_clipboard(text)
        return _ok({'copied': True})

    if action == 'sketch:list':
        return _ok(sketch_constraints.list_sketches())
    if action == 'sketch:delete':
        return _ok(sketch_constraints.delete_constraint(data))
    if action == 'sketch:select':
        return _ok(sketch_constraints.select_item(data if isinstance(data, dict) else {'token': data or ''}))
    if action == 'sketch:highlight':
        return _ok(sketch_constraints.highlight_constraint(data))
    if action == 'sketch:clearHighlight':
        return _ok(sketch_constraints.clear_highlight())
    if action == 'sketch:readSelection':
        return _ok(sketch_constraints.read_selection())
    if action == 'sketch:add':
        return _ok(sketch_constraints.add_constraint(data))

    if action == 'constraint:list':
        return _ok(assembly_constraints.list_constraints())
    if action == 'constraint:readSelection':
        return _ok(assembly_constraints.read_selection())
    if action == 'constraint:rename':
        return _ok(assembly_constraints.rename(data))
    if action == 'constraint:setSuppressed':
        return _ok(assembly_constraints.set_suppressed(data))
    if action == 'constraint:setVisible':
        return _ok(assembly_constraints.set_visible(data))
    if action == 'constraint:delete':
        return _ok(assembly_constraints.delete(data))
    if action == 'constraint:highlight':
        return _ok(assembly_constraints.highlight(data))
    if action == 'constraint:clearHighlight':
        return _ok(assembly_constraints.clear_highlight(data if isinstance(data, dict) else {}))
    if action == 'constraint:select':
        return _ok(assembly_constraints.select(data))

    return _err(f'Unknown action: {action}')


def on_document_activated(args):
    try:
        sketch_constraints.clear_highlight()
        assembly_constraints.clear_highlight()
    except Exception:
        pass
    context = _document_context()
    _push('docActivated', context)
    _push('selectionChanged', {
        'sketch': sketch_constraints.empty_selection(),
        'constraint': assembly_constraints.empty_selection(),
        'document': context,
    })


def on_selection_changed(args):
    if assembly_constraints.selection_suspended():
        return
    context = _document_context()
    allowed = context['assemblyAllowed']
    _push('selectionChanged', {
        'sketch': sketch_constraints.read_selection(),
        'constraint': assembly_constraints.read_selection() if allowed else assembly_constraints.empty_selection(),
        'document': context,
    })


def _push(action, payload):
    palette = ui.palettes.itemById(PALETTE_ID)
    if not palette:
        return
    try:
        palette.sendInfoToHTML(action, json.dumps(payload))
    except Exception:
        futil.log(f'Could not push {action}: {traceback.format_exc()}')


def _minimize_palette():
    try:
        sketch_constraints.clear_highlight()
        assembly_constraints.clear_highlight()
    except Exception:
        pass
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
    intent = design_utils.design_intent()
    return {
        'doc': _active_doc_name(),
        'intent': intent,
        'assemblyAllowed': intent in ('assembly', 'hybrid'),
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
