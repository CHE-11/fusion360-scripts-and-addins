"""Toolbar button that lists saved Fusion scripts and runs the one you pick.

A pinned list control does not open its menu when the toolbar icon is clicked,
and a standard list never marks the chosen row as selected. A normal button
opens a dialog instead, which is what the toolbar click runs.
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
DETAIL_INPUT = 'detail'
REFRESH_INPUT = 'refresh'
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

_dialog_actions = {}
_dialog_details = {}
_filling_dialog = False
_pending_folders = set()
_pending_lock = threading.Lock()
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
        cmd.setDialogInitialSize(420, 220)
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
        dropdown = adsk.core.DropDownCommandInput.cast(inputs.itemById(SCRIPT_INPUT))
        if dropdown is None:
            dropdown = inputs.addDropDownCommandInput(
                SCRIPT_INPUT,
                'Script',
                adsk.core.DropDownStyles.TextListDropDownStyle,
            )
        detail = adsk.core.TextBoxCommandInput.cast(inputs.itemById(DETAIL_INPUT))
        if detail is None:
            detail = inputs.addTextBoxCommandInput(DETAIL_INPUT, '', '', 4, True)
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
        _dialog_actions = dict(zip(labels, actions))
        _dialog_details = dict(zip(labels, details))
        _set_dropdown_labels(dropdown, labels)
        detail.formattedText = details[0]
        try:
            cmd.isOKButtonVisible = actions[0] != EMPTY_TOKEN
        except Exception:
            pass
    finally:
        _filling_dialog = False


def _add_refresh_button(inputs):
    try:
        inputs.addBoolValueInput(REFRESH_INPUT, 'Refresh', False, '', False)
    except Exception:
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
    if changed.id == SCRIPT_INPUT:
        _show_selected_detail(args.inputs)


def _on_validate(args: adsk.core.ValidateInputsEventArgs):
    action = _selected_action(args.inputs)
    args.areInputsValid = bool(action) and action != EMPTY_TOKEN


def _on_execute(args: adsk.core.CommandEventArgs):
    action = _selected_action(args.command.commandInputs)
    if not action or action == EMPTY_TOKEN:
        return
    _schedule_run(action)


def _selected_action(inputs):
    name = _selected_name(inputs)
    if not name:
        return ''
    return _dialog_actions.get(name, '')


def _selected_name(inputs):
    if inputs is None:
        return ''
    dropdown = adsk.core.DropDownCommandInput.cast(inputs.itemById(SCRIPT_INPUT))
    if dropdown is None or dropdown.selectedItem is None:
        return ''
    return dropdown.selectedItem.name or ''


def _show_selected_detail(inputs):
    detail = adsk.core.TextBoxCommandInput.cast(inputs.itemById(DETAIL_INPUT))
    name = _selected_name(inputs)
    if detail is None or not name:
        return
    text = _dialog_details.get(name)
    if text:
        detail.formattedText = text


def _set_dropdown_labels(dropdown, labels):
    """Replace the rows. The selected row cannot be deleted, so a temporary row is selected first."""
    items = dropdown.listItems
    items.add(' ', True)
    removed = 0
    while items.count > 1 and removed < 200:
        first = items.item(0)
        if first is None or first.isSelected:
            break
        if not first.deleteMe():
            break
        removed += 1
    for label in labels:
        items.add(label, False)
    if items.count < 2:
        return
    items.item(1).isSelected = True
    if not items.item(0).deleteMe():
        futil.log('Script Runner: could not remove the placeholder row from the script list.')


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

