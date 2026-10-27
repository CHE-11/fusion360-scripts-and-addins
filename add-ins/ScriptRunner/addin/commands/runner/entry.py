"""Toolbar dropdown that lists saved Fusion scripts and runs the one you pick."""

import hashlib
import os
import threading
import traceback

import adsk.core

from ... import config
from ...lib import fusion360utils as futil

app = adsk.core.Application.get()
ui = app.userInterface

CMD_PREFIX = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}'
REFRESH_CMD_ID = f'{CMD_PREFIX}_Refresh'
EMPTY_CMD_ID = f'{CMD_PREFIX}_Empty'
RUN_EVENT_ID = f'{CMD_PREFIX}_run'
REFRESH_TOKEN = f'{CMD_PREFIX}_refresh_token'
UTILITIES_DROPDOWN_ID = f'{CMD_PREFIX}_UtilitiesDropdown'
DROPDOWN_TEXT = 'Scripts'
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# ScriptSourceLocations: user folder and scripts linked with the + button.
_USER_LOCATION_VALUES = {2, 5}

_dropdowns = []
_script_handlers = []
_command_folders = {}
_pending_folders = set()
_pending_lock = threading.Lock()
_empty_message = (
    'No saved scripts yet.\n\n'
    'Create or link one with Utilities → Scripts and Add-Ins, then choose Refresh.'
)


class SavedScript:
    def __init__(self, name, folder, description):
        self.name = name
        self.folder = folder
        self.description = description


def start():
    _remove_ui()
    _register_run_event()
    _create_static_commands()
    _create_dropdowns()
    rebuild()


def stop():
    _remove_ui()
    for command_id in (REFRESH_CMD_ID, EMPTY_CMD_ID):
        _delete_definition(command_id)
    _delete_script_commands()
    try:
        app.unregisterCustomEvent(RUN_EVENT_ID)
    except Exception:
        pass


def rebuild():
    """Reload the dropdown from Fusion's saved scripts."""
    global _empty_message
    list_failed = False
    try:
        scripts = _saved_scripts()
        _empty_message = (
            'No saved scripts yet.\n\n'
            'Create or link one with Utilities → Scripts and Add-Ins, then choose Refresh.'
        )
        futil.log(f'Script Runner: {len(scripts)} saved script(s).')
    except Exception:
        scripts = []
        list_failed = True
        futil.log(f'Script Runner: script list failed:\n{traceback.format_exc()}')
        _empty_message = (
            'Fusion did not return the script list.\n\n'
            'Use Utilities → Scripts and Add-Ins, then choose Refresh.'
        )

    for dropdown in list(_dropdowns):
        if _is_valid(dropdown):
            _clear_controls(dropdown.controls)
    _replace_script_commands(scripts)

    empty_definition = ui.commandDefinitions.itemById(EMPTY_CMD_ID)
    if empty_definition:
        empty_definition.name = 'Scripts unavailable' if list_failed else 'No saved scripts'

    for dropdown in list(_dropdowns):
        if _is_valid(dropdown):
            _fill_dropdown(dropdown, scripts)


def _register_run_event():
    try:
        app.unregisterCustomEvent(RUN_EVENT_ID)
    except Exception:
        pass
    event = app.registerCustomEvent(RUN_EVENT_ID)
    futil.add_handler(event, _on_run_script)


def _create_static_commands():
    refresh = ui.commandDefinitions.itemById(REFRESH_CMD_ID)
    if refresh is None:
        refresh = ui.commandDefinitions.addButtonDefinition(
            REFRESH_CMD_ID,
            'Refresh',
            'Reload the list of saved scripts',
            ICON_FOLDER,
        )
        futil.add_handler(refresh.commandCreated, _on_refresh_created)

    empty = ui.commandDefinitions.itemById(EMPTY_CMD_ID)
    if empty is None:
        empty = ui.commandDefinitions.addButtonDefinition(
            EMPTY_CMD_ID,
            'No saved scripts',
            'No saved scripts are available to run',
            ICON_FOLDER,
        )
        futil.add_handler(empty.commandCreated, _on_empty_created)


def _create_dropdowns():
    panel = _utilities_panel()
    if panel:
        dropdown = _add_dropdown(panel.controls, UTILITIES_DROPDOWN_ID, config.COMMAND_BESIDE_ID)
        if dropdown:
            _promote(dropdown)
    else:
        futil.log('Script Runner: Utilities ADD-INS panel was not found.')

    for tab_id, panel_id, after_panel_id in config.RIBBON_TABS:
        try:
            host = _panel_on_tab(tab_id, panel_id, after_panel_id)
        except Exception:
            futil.log(f'Script Runner: could not add the dropdown to {tab_id}: {traceback.format_exc()}')
            continue
        if not host:
            continue
        dropdown_id = f'{CMD_PREFIX}_{tab_id}Dropdown'
        dropdown = _add_dropdown(host.controls, dropdown_id, '')
        if dropdown:
            _promote(dropdown)


def _add_dropdown(controls, dropdown_id, beside_id):
    existing = controls.itemById(dropdown_id)
    if existing:
        existing.deleteMe()
    try:
        if beside_id:
            dropdown = controls.addDropDown(DROPDOWN_TEXT, ICON_FOLDER, dropdown_id, beside_id, False)
        else:
            dropdown = controls.addDropDown(DROPDOWN_TEXT, ICON_FOLDER, dropdown_id)
    except Exception:
        futil.log(f'Script Runner: could not place dropdown {dropdown_id}: {traceback.format_exc()}')
        if not beside_id:
            return None
        leftover = controls.itemById(dropdown_id)
        if leftover:
            leftover.deleteMe()
        try:
            dropdown = controls.addDropDown(DROPDOWN_TEXT, ICON_FOLDER, dropdown_id)
        except Exception:
            futil.log(f'Script Runner: could not create dropdown {dropdown_id}: {traceback.format_exc()}')
            return None
    if dropdown:
        try:
            dropdown.name = DROPDOWN_TEXT
        except Exception:
            pass
        _dropdowns.append(dropdown)
    return dropdown


def _fill_dropdown(dropdown, scripts):
    controls = dropdown.controls
    if scripts:
        for command_id in _command_folders:
            definition = ui.commandDefinitions.itemById(command_id)
            if definition:
                controls.addCommand(definition)
    else:
        empty = ui.commandDefinitions.itemById(EMPTY_CMD_ID)
        if empty:
            controls.addCommand(empty)
    try:
        controls.addSeparator(f'{dropdown.id}_separator')
    except Exception:
        futil.log(f'Script Runner: could not add a separator: {traceback.format_exc()}')
    refresh = ui.commandDefinitions.itemById(REFRESH_CMD_ID)
    if refresh:
        controls.addCommand(refresh)


def _replace_script_commands(scripts):
    _delete_script_commands()
    for saved in scripts:
        command_id = _command_id(saved.folder)
        definition = ui.commandDefinitions.addButtonDefinition(
            command_id,
            saved.name,
            _tooltip(saved),
            ICON_FOLDER,
        )
        futil.add_handler(
            definition.commandCreated,
            _on_script_created,
            local_handlers=_script_handlers,
        )
        _command_folders[command_id] = saved.folder


def _delete_script_commands():
    for command_id in list(_command_folders):
        _delete_definition(command_id)
    _command_folders.clear()
    _script_handlers.clear()


def _on_refresh_created(args: adsk.core.CommandCreatedEventArgs):
    futil.add_handler(args.command.execute, _on_refresh_execute)


def _on_refresh_execute(args: adsk.core.CommandEventArgs):
    # Rebuild after this command closes. Deleting its control during execute is unsafe.
    _schedule_run(REFRESH_TOKEN)


def _on_empty_created(args: adsk.core.CommandCreatedEventArgs):
    futil.add_handler(args.command.execute, _on_empty_execute)


def _on_empty_execute(args: adsk.core.CommandEventArgs):
    ui.messageBox(_empty_message, 'Script Runner')


def _on_script_created(args: adsk.core.CommandCreatedEventArgs):
    futil.add_handler(
        args.command.execute,
        _on_script_execute,
        local_handlers=_script_handlers,
    )


def _on_script_execute(args: adsk.core.CommandEventArgs):
    command_id = args.command.parentCommandDefinition.id
    folder = _command_folders.get(command_id)
    if not folder:
        ui.messageBox('That script is no longer in the list. Choose Refresh.', 'Script Runner')
        return
    _schedule_run(folder)


def _schedule_run(folder):
    """Run after this command closes so the script can open its own dialog."""
    with _pending_lock:
        if folder in _pending_folders:
            return
        _pending_folders.add(folder)

    def _fire():
        try:
            app.fireCustomEvent(RUN_EVENT_ID, folder)
        except Exception:
            with _pending_lock:
                _pending_folders.discard(folder)

    timer = threading.Timer(0.2, _fire)
    timer.daemon = True
    timer.start()


def _on_run_script(args: adsk.core.CustomEventArgs):
    folder = args.additionalInfo or ''
    if folder == REFRESH_TOKEN:
        try:
            rebuild()
        except Exception:
            futil.handle_error('Refresh scripts', show_message_box=True)
        finally:
            with _pending_lock:
                _pending_folders.discard(folder)
        return
    try:
        script = _script_at(folder)
        if script is None:
            ui.messageBox(
                'That script is no longer available. Choose Refresh in the Scripts menu.',
                'Script Runner',
            )
            rebuild()
            return
        if getattr(script, 'isRunning', False):
            ui.messageBox(f'"{script.name}" is already running.', 'Script Runner')
            return
        started = script.run()
        if started is False:
            ui.messageBox(f'Fusion did not start "{script.name}".', 'Script Runner')
    except Exception:
        futil.handle_error('Run script', show_message_box=True)
    finally:
        with _pending_lock:
            _pending_folders.discard(folder)


def _saved_scripts():
    scripts = getattr(app, 'scripts', None)
    if scripts is None:
        raise RuntimeError('This version of Fusion has no scripts collection.')

    saved = []
    seen = set()
    for index in range(scripts.count):
        try:
            script = scripts.item(index)
            if not _is_saved_script(script):
                continue
            folder = script.folder or ''
            if not folder:
                continue
            key = os.path.normcase(os.path.normpath(folder))
            if key in seen:
                continue
            seen.add(key)
            name = (script.name or 'Script').replace('\n', ' ').strip() or 'Script'
            description = (getattr(script, 'description', '') or '').strip()
            saved.append(SavedScript(name, folder, description))
        except Exception:
            futil.log(f'Script Runner: skipped a script at index {index}:\n{traceback.format_exc()}')
    saved.sort(key=lambda item: item.name.casefold())
    return saved


def _is_saved_script(script):
    if getattr(script, 'isAddIn', True):
        return False
    if hasattr(script, 'isVisible') and not script.isVisible:
        return False
    location = getattr(script, 'location', None)
    if location is None:
        return not bool(getattr(script, 'isInternal', False))
    return _location_is_saved(location)


def _location_is_saved(location):
    values, members = _saved_locations()
    if members and location in members:
        return True
    try:
        return int(location) in values
    except Exception:
        return False


def _saved_locations():
    """User scripts folder, plus scripts linked from the Scripts and Add-Ins dialog."""
    locations = getattr(adsk.core, 'ScriptSourceLocations', None)
    if locations is not None:
        values = set()
        members = []
        for name in ('UserDefinedScriptSourceLocation', 'LinkedScriptSourceLocation'):
            member = getattr(locations, name, None)
            if member is None:
                continue
            members.append(member)
            try:
                values.add(int(member))
            except Exception:
                pass
        if values or members:
            return values, members
    return set(_USER_LOCATION_VALUES), []


def _script_at(folder):
    scripts = getattr(app, 'scripts', None)
    if scripts is None or not folder:
        return None
    try:
        found = scripts.itemByPath(folder)
        if found:
            return found
    except Exception:
        futil.log(f'Script Runner: itemByPath failed for {folder}: {traceback.format_exc()}')
    target = os.path.normcase(os.path.normpath(folder))
    for index in range(scripts.count):
        script = scripts.item(index)
        try:
            current = os.path.normcase(os.path.normpath(script.folder or ''))
        except Exception:
            continue
        if current == target:
            return script
    return None


def _command_id(folder):
    digest = hashlib.sha1(os.path.normcase(os.path.normpath(folder)).encode('utf-8')).hexdigest()[:16]
    return f'{CMD_PREFIX}_Run_{digest}'


def _tooltip(saved):
    text = saved.description
    if not text or text == saved.name:
        text = saved.folder or f'Run {saved.name}'
    elif saved.folder and saved.folder not in text:
        text = f'{text}\n{saved.folder}'
    if len(text) > 400:
        text = text[:397] + '...'
    return text


def _utilities_panel():
    workspace = ui.workspaces.itemById(config.WORKSPACE_ID)
    if not workspace:
        return None
    return workspace.toolbarPanels.itemById(config.PANEL_ID)


def _toolbar_tab(tab_id):
    workspace = ui.workspaces.itemById(config.WORKSPACE_ID)
    if workspace:
        tab = workspace.toolbarTabs.itemById(tab_id)
        if tab:
            return tab
    all_tabs = getattr(ui, 'allToolbarTabs', None)
    if all_tabs:
        return all_tabs.itemById(tab_id)
    return None


def _panel_on_tab(tab_id, panel_id, after_panel_id):
    tab = _toolbar_tab(tab_id)
    if not tab:
        futil.log(f'Script Runner: toolbar tab {tab_id} was not found.')
        return None
    panel = tab.toolbarPanels.itemById(panel_id)
    if panel:
        return panel
    try:
        return tab.toolbarPanels.add(panel_id, config.RIBBON_PANEL_NAME, after_panel_id, False)
    except Exception:
        futil.log(f'Script Runner: could not place a panel after {after_panel_id} on {tab_id}.')
    try:
        return tab.toolbarPanels.add(panel_id, config.RIBBON_PANEL_NAME, '', False)
    except Exception:
        futil.log(f'Script Runner: could not create panel on {tab_id}: {traceback.format_exc()}')
        return None


def _remove_ui():
    global _dropdowns
    for tab_id, panel_id, _after_panel_id in config.RIBBON_TABS:
        tab = _toolbar_tab(tab_id)
        if not tab:
            continue
        panel = tab.toolbarPanels.itemById(panel_id)
        if not panel:
            continue
        dropdown = panel.controls.itemById(f'{CMD_PREFIX}_{tab_id}Dropdown')
        if dropdown:
            dropdown.deleteMe()
        if panel.controls.count == 0:
            panel.deleteMe()
    panel = _utilities_panel()
    if panel:
        control = panel.controls.itemById(UTILITIES_DROPDOWN_ID)
        if control:
            control.deleteMe()
    _dropdowns = []


def _clear_controls(controls):
    for _ in range(controls.count):
        control = controls.item(controls.count - 1)
        if not control:
            break
        control.deleteMe()


def _delete_definition(command_id):
    definition = ui.commandDefinitions.itemById(command_id)
    if definition:
        definition.deleteMe()


def _promote(control):
    for prop in ('isPromoted', 'isPromotedByDefault'):
        if hasattr(control, prop):
            try:
                setattr(control, prop, True)
            except Exception:
                pass


def _is_valid(obj):
    try:
        return bool(obj.isValid)
    except Exception:
        return False
