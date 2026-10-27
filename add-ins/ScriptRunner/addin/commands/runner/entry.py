"""Toolbar button that lists saved Fusion scripts and runs the one you pick.

A pinned list control does not open its menu when the toolbar icon is clicked,
and a standard list never marks the chosen row as selected. A normal button
opens a dialog with a scrollable list instead, which is what the toolbar click runs.
"""

import os
import threading
import traceback

import adsk.core

from ... import config
from ...lib import fusion360utils as futil

app = adsk.core.Application.get()
ui = app.userInterface

CMD_PREFIX = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}'
LIST_CMD_ID = f'{CMD_PREFIX}_Scripts'
RUN_EVENT_ID = f'{CMD_PREFIX}_run'
EMPTY_TOKEN = f'{CMD_PREFIX}_empty'
SCRIPT_INPUT = 'script'
SCRIPT_ROW_PREFIX = 'script_row_'
DETAIL_INPUT = 'detail'
REFRESH_INPUT = 'refresh'
_LIST_VISIBLE_ROWS = 8
# Previous builds used drop-downs and a list command. Remove those controls on start.
_LEGACY_CONTROL_IDS = (
    f'{CMD_PREFIX}_UtilitiesDropdown',
    f'{CMD_PREFIX}_SolidTabDropdown',
    f'{CMD_PREFIX}_Refresh',
    f'{CMD_PREFIX}_Empty',
)
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# ScriptSourceLocations: user folder and scripts linked with the + button.
_USER_LOCATION_VALUES = {2, 5}

_dialog_actions = []
_dialog_details = []
_filling_dialog = False
_pending_folders = set()
_pending_lock = threading.Lock()
_run_attempts = {}
_MAX_RUN_ATTEMPTS = 15
_NO_SCRIPTS_DETAIL = (
    'No saved scripts yet.<br/><br/>'
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
    _create_command()
    _place_buttons()


def stop():
    _remove_ui()
    _delete_definition(LIST_CMD_ID)
    try:
        app.unregisterCustomEvent(RUN_EVENT_ID)
    except Exception:
        pass


def _register_run_event():
    try:
        app.unregisterCustomEvent(RUN_EVENT_ID)
    except Exception:
        pass
    event = app.registerCustomEvent(RUN_EVENT_ID)
    futil.add_handler(event, _on_run_script)


def _create_command():
    _delete_definition(LIST_CMD_ID)
    definition = ui.commandDefinitions.addButtonDefinition(
        LIST_CMD_ID,
        'Scripts',
        'Run a saved script',
        ICON_FOLDER,
    )
    futil.add_handler(definition.commandCreated, _on_created)


def _place_buttons():
    definition = ui.commandDefinitions.itemById(LIST_CMD_ID)
    if definition is None:
        futil.log('Script Runner: Scripts command was not created.', adsk.core.LogLevels.ErrorLogLevel, True)
        return
    panel = _utilities_panel()
    if panel:
        _place_button(panel, definition, config.COMMAND_BESIDE_ID)
    else:
        futil.log('Script Runner: Utilities ADD-INS panel was not found.', adsk.core.LogLevels.WarningLogLevel, True)

    for tab_id, panel_id, after_panel_id in config.RIBBON_TABS:
        try:
            host = _panel_on_tab(tab_id, panel_id, after_panel_id)
        except Exception:
            futil.log(f'Script Runner: could not add Scripts to {tab_id}: {traceback.format_exc()}')
            continue
        if not host:
            continue
        _place_button(host, definition, '')


def _place_button(panel, definition, beside_id):
    existing = panel.controls.itemById(LIST_CMD_ID)
    if existing:
        existing.deleteMe()
    try:
        if beside_id and panel.controls.itemById(beside_id):
            control = panel.controls.addCommand(definition, beside_id, False)
        else:
            control = panel.controls.addCommand(definition)
    except Exception:
        futil.log(f'Script Runner: could not place Scripts on {panel.id}: {traceback.format_exc()}')
        return
    try:
        control.isPromoted = True
    except Exception:
        futil.log(f'Script Runner: could not pin Scripts on {panel.id}: {traceback.format_exc()}')
    try:
        control.isPromotedByDefault = True
    except Exception:
        pass
    futil.log(f'Script Runner: pinned Scripts on {panel.id}.')


def _on_created(args: adsk.core.CommandCreatedEventArgs):
    cmd = args.command
    cmd.isRepeatable = False
    cmd.okButtonText = 'Run'
    cmd.cancelButtonText = 'Close'
    try:
        cmd.setDialogInitialSize(440, 360)
    except Exception:
        pass
    _populate(cmd)
    futil.add_handler(cmd.execute, _on_execute)
    futil.add_handler(cmd.inputChanged, _on_input_changed)
    futil.add_handler(cmd.validateInputs, _on_validate)
    futil.log('Script Runner: opened the script list.')


def _populate(cmd):
    """Fill the dialog from Fusion's saved scripts."""
    global _dialog_actions, _dialog_details, _filling_dialog
    _filling_dialog = True
    try:
        scripts, error = _load_scripts()
        inputs = cmd.commandInputs
        table = _script_table(inputs)
        detail = adsk.core.TextBoxCommandInput.cast(inputs.itemById(DETAIL_INPUT))
        if detail is None:
            detail = inputs.addTextBoxCommandInput(DETAIL_INPUT, '', '', 3, True)
        if inputs.itemById(REFRESH_INPUT) is None:
            _add_refresh_button(inputs)

        actions = []
        details = []
        labels = []
        if error:
            labels.append('Scripts unavailable')
            actions.append(EMPTY_TOKEN)
            details.append(error)
        elif not scripts:
            labels.append('No saved scripts')
            actions.append(EMPTY_TOKEN)
            details.append(_NO_SCRIPTS_DETAIL)
        else:
            used_names = set()
            for saved in scripts:
                labels.append(_unique_name(saved, used_names))
                actions.append(saved.folder)
                details.append(_script_detail(saved))
        _dialog_actions = actions
        _dialog_details = details
        _fill_script_list(inputs, table, labels)
        detail.formattedText = details[0]
    finally:
        _filling_dialog = False


def _add_refresh_button(inputs):
    inputs.addBoolValueInput(REFRESH_INPUT, 'Refresh', False, ICON_FOLDER, False)


def _load_scripts():
    try:
        scripts = _saved_scripts()
        futil.log(f'Script Runner: {len(scripts)} saved script(s).')
        return scripts, ''
    except Exception:
        futil.log(f'Script Runner: script list failed:\n{traceback.format_exc()}')
        return [], (
            'Fusion did not return the script list.<br/><br/>'
            'Use Utilities → Scripts and Add-Ins, then choose Refresh.'
        )


def _on_input_changed(args: adsk.core.InputChangedEventArgs):
    if _filling_dialog:
        return
    changed = args.input
    if changed.id == REFRESH_INPUT:
        button = adsk.core.BoolValueCommandInput.cast(changed)
        if button is not None and not button.value:
            return
        if button is not None:
            try:
                button.value = False
            except Exception:
                pass
        _populate(args.inputs.command)
        return
    if changed.id == SCRIPT_INPUT or changed.id.startswith(SCRIPT_ROW_PREFIX):
        _show_selected_detail(args.inputs)


def _on_validate(args: adsk.core.ValidateInputsEventArgs):
    action = _selected_action(args.inputs)
    args.areInputsValid = bool(action) and action != EMPTY_TOKEN


def _on_execute(args: adsk.core.CommandEventArgs):
    action = _selected_action(args.command.commandInputs)
    if not action or action == EMPTY_TOKEN:
        return
    _schedule_run(action)


def _script_table(inputs):
    table = adsk.core.TableCommandInput.cast(inputs.itemById(SCRIPT_INPUT))
    if table is not None:
        return table
    table = inputs.addTableCommandInput(SCRIPT_INPUT, '', 1, '1')
    table.hasGrid = False
    table.minimumVisibleRows = 1
    table.maximumVisibleRows = _LIST_VISIBLE_ROWS
    table.rowSpacing = 1
    table.columnSpacing = 0
    table.tablePresentationStyle = adsk.core.TablePresentationStyles.itemBorderTablePresentationStyle
    return table


def _fill_script_list(inputs, table, labels):
    """Show every script as its own row. The highlighted row is the one Run uses."""
    _remove_script_rows(inputs, table)
    for index, label in enumerate(labels):
        row = inputs.addTextBoxCommandInput(f'{SCRIPT_ROW_PREFIX}{index}', '', '', 1, True)
        row.text = label
        table.addCommandInput(row, index, 0, 0, 0)
    if labels:
        table.selectedRow = 0


def _remove_script_rows(inputs, table):
    try:
        table.selectedRow = -1
    except Exception:
        pass
    index = 0
    while True:
        row = inputs.itemById(f'{SCRIPT_ROW_PREFIX}{index}')
        if row is None:
            break
        row.deleteMe()
        index += 1
    if table.rowCount:
        table.clear()


def _selected_action(inputs):
    row = _selected_row(inputs)
    if row < 0:
        return ''
    return _dialog_actions[row]


def _selected_row(inputs):
    if inputs is None:
        return -1
    table = adsk.core.TableCommandInput.cast(inputs.itemById(SCRIPT_INPUT))
    if table is None:
        return -1
    row = table.selectedRow
    if row < 0 or row >= len(_dialog_actions):
        return -1
    return row


def _show_selected_detail(inputs):
    detail = adsk.core.TextBoxCommandInput.cast(inputs.itemById(DETAIL_INPUT))
    row = _selected_row(inputs)
    if detail is None or row < 0:
        return
    text = _dialog_details[row]
    if text:
        detail.formattedText = text


def _script_detail(saved):
    parts = []
    description = (saved.description or '').strip()
    if description and description != saved.name:
        parts.append(_html(description))
    if saved.folder:
        parts.append(_html(saved.folder))
    return '<br/>'.join(parts) or 'Run this script.'


def _html(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _unique_name(saved, used_names):
    name = saved.name
    if name not in used_names:
        used_names.add(name)
        return name
    suffix = os.path.basename(os.path.normpath(saved.folder)) or saved.folder
    unique = f'{name} ({suffix})'
    used_names.add(unique)
    return unique


def _schedule_run(folder):
    """Run after this command closes so the script can open its own dialog."""
    with _pending_lock:
        if folder in _pending_folders:
            return
        _pending_folders.add(folder)
    _run_attempts[folder] = 0
    _fire_run_later(folder)


def _fire_run_later(folder):
    def _fire():
        try:
            app.fireCustomEvent(RUN_EVENT_ID, folder)
        except Exception:
            _finish_run(folder)

    timer = threading.Timer(0.2, _fire)
    timer.daemon = True
    timer.start()


def _finish_run(folder):
    _run_attempts.pop(folder, None)
    with _pending_lock:
        _pending_folders.discard(folder)


def _command_is_idle():
    """script.run starts another command. Calling it while one is still open corrupts the heap."""
    try:
        active = ui.activeCommand or ''
    except Exception:
        return True
    return active in ('', 'SelectCommand')


def _on_run_script(args: adsk.core.CustomEventArgs):
    folder = args.additionalInfo or ''
    if not _command_is_idle():
        attempt = _run_attempts.get(folder, 0) + 1
        if attempt <= _MAX_RUN_ATTEMPTS:
            _run_attempts[folder] = attempt
            _fire_run_later(folder)
            return
        futil.log(f'Script Runner: Fusion was still in a command, so "{folder}" was not started.')
        try:
            ui.messageBox(
                'Fusion was still closing the script list, so nothing was started. Choose the script again.',
                'Script Runner',
            )
        except Exception:
            pass
        _finish_run(folder)
        return
    try:
        script = _script_at(folder)
        if script is None:
            ui.messageBox(
                'That script is no longer available. Open Scripts and choose Refresh.',
                'Script Runner',
            )
            return
        if getattr(script, 'isRunning', False):
            ui.messageBox(f'"{script.name}" is already running.', 'Script Runner')
            return
        started = script.run(False)
        if started is False:
            ui.messageBox(f'Fusion did not start "{script.name}".', 'Script Runner')
    except Exception:
        futil.handle_error('Run script', show_message_box=True)
    finally:
        _finish_run(folder)


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
    for tab_id, panel_id, _after_panel_id in config.RIBBON_TABS:
        tab = _toolbar_tab(tab_id)
        if not tab:
            continue
        panel = tab.toolbarPanels.itemById(panel_id)
        if not panel:
            continue
        _delete_panel_controls(panel)
        if panel.controls.count == 0:
            panel.deleteMe()
    panel = _utilities_panel()
    if panel:
        _delete_panel_controls(panel)


def _delete_panel_controls(panel):
    for control_id in (LIST_CMD_ID, *_LEGACY_CONTROL_IDS):
        try:
            control = panel.controls.itemById(control_id)
        except Exception:
            continue
        if control:
            control.deleteMe()


def _delete_definition(command_id):
    definition = ui.commandDefinitions.itemById(command_id)
    if definition:
        definition.deleteMe()

