"""File Explorer palette command and message router."""

import json
import os
import subprocess
import sys
import traceback

import adsk.core

from ... import config
from ...lib import fusionAddInUtils as futil
from . import browser

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_PalleteShow'
CMD_NAME = 'File Explorer'
CMD_DESCRIPTION = 'Browse, search, and manage Fusion projects and files'
PALETTE_NAME = 'File Explorer'
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
    """Add the command to the shared CHE panel on a Design toolbar tab."""
    tab = _toolbar_tab(tab_id)
    if not tab:
        futil.log(f'File Explorer: toolbar tab {tab_id} was not found.')
        return
    panel = tab.toolbarPanels.itemById(panel_id)
    if not panel:
        try:
            panel = tab.toolbarPanels.add(panel_id, config.RIBBON_PANEL_NAME, after_panel_id, False)
        except Exception:
            futil.log(f'File Explorer: could not place a panel after {after_panel_id} on {tab_id}.')
            try:
                panel = tab.toolbarPanels.add(panel_id, config.RIBBON_PANEL_NAME, '', False)
            except Exception:
                futil.log(f'File Explorer: could not create panel on {tab_id}: {traceback.format_exc()}')
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
    browser.attach(_push)
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
            futil.log(f'File Explorer: could not add the command to {tab_id}: {traceback.format_exc()}')

    try:
        futil.add_handler(app.documentActivated, on_document_activated)
    except Exception:
        futil.log(f'Could not attach documentActivated handler: {traceback.format_exc()}')


def stop():
    try:
        browser.detach()
    except Exception:
        futil.log(f'Could not detach File Explorer: {traceback.format_exc()}')
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID) if workspace else None
    command_control = panel.controls.itemById(CMD_ID) if panel else None
    if command_control:
        command_control.deleteMe()
    for tab_id, panel_id, _after_panel_id in RIBBON_TABS:
        try:
            _remove_tab_panel(tab_id, panel_id)
        except Exception:
            futil.log(f'File Explorer: could not remove the panel from {tab_id}: {traceback.format_exc()}')
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
    futil.log('File Explorer palette closed.')


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
        html_args.returnData = _err('Something went wrong in Fusion. Details are in the Text Commands window.')


def route_message(action, data):
    payload = data if isinstance(data, dict) else {}
    if action == 'ready':
        return _ok(browser.ready())
    if action == 'folder:list':
        return _ok(browser.list_location(payload))
    if action == 'file:open':
        return _ok(browser.open_file(payload.get('id', '')))
    if action == 'file:insert':
        return _ok(browser.insert_file(payload.get('id', '')))
    if action == 'item:rename':
        return _ok(browser.rename_item(payload))
    if action == 'item:delete':
        return _ok(browser.delete_item(payload))
    if action == 'folder:create':
        return _ok(browser.create_folder(payload))
    if action == 'file:move':
        return _ok(browser.move_file(payload))
    if action == 'file:references':
        return _ok(browser.references(payload.get('id', '')))
    if action == 'nav:activeFile':
        return _ok(browser.nav_active_file())
    if action == 'search:start':
        return _ok(browser.start_search(payload))
    if action == 'search:cancel':
        return _ok(browser.cancel_search(payload))
    if action == 'jsLog':
        _handle_js_log(payload)
        return _ok()
    if action == 'clipboard:copy':
        text = payload.get('text')
        if not isinstance(text, str):
            return _err('clipboard:copy expects text')
        _copy_to_clipboard(text)
        return _ok({'copied': True})
    return _err(f'Unknown action: {action}')


def on_document_activated(args):
    _push('activeFileChanged', {'activeFileId': browser.active_file_id()})


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
