import os
import sys
import threading
import traceback

import adsk.core

from ...lib import fusion360utils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_Restart'
CMD_NAME = 'Restart Add-Ins'
CMD_DESCRIPTION = 'Stop and start every running user add-in'
RESTART_EVENT_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_restart'
IS_PROMOTED = True
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# ScriptSourceLocations: Internal = 3, Samples = 4.
# Used only when the enum is missing from this Fusion build.
_FALLBACK_EXCLUDED_LOCATIONS = {3, 4}


local_handlers = []
_event_handlers = []
_restart_scheduled = False


def start():
    _register_restart_event()
    existing = ui.commandDefinitions.itemById(CMD_ID)
    if existing:
        existing.deleteMe()

    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_DESCRIPTION, ICON_FOLDER
    )
    futil.add_handler(cmd_def.commandCreated, command_created, name='RestartAddIns_commandCreated')

    added = 0
    try:
        workspace = ui.workspaces.itemById(config.WORKSPACE_ID)
        panel = workspace.toolbarPanels.itemById(config.PANEL_ID) if workspace else None
        if panel and _place_control(panel, cmd_def, config.COMMAND_BESIDE_ID, False):
            added += 1
    except Exception:
        futil.log(
            f'Could not add Restart Add-Ins to {config.PANEL_ID}\n{traceback.format_exc()}',
            adsk.core.LogLevels.WarningLogLevel,
            True,
        )

    for tab_id, panel_id, after_panel_id in config.RIBBON_TABS:
        try:
            if _place_on_tab(cmd_def, tab_id, panel_id, after_panel_id):
                added += 1
        except Exception:
            futil.log(
                f'Could not add Restart Add-Ins to {tab_id}\n{traceback.format_exc()}',
                adsk.core.LogLevels.WarningLogLevel,
                True,
            )

    added += _place_on_script_panels(cmd_def)
    if added == 0:
        futil.log(
            'Restart Add-Ins did not find a Scripts and Add-Ins panel.',
            adsk.core.LogLevels.WarningLogLevel,
            True,
        )


def stop():
    _remove_control(config.WORKSPACE_ID, config.PANEL_ID)
    for tab_id, panel_id, _after_panel_id in config.RIBBON_TABS:
        try:
            _remove_tab_panel(tab_id, panel_id)
        except Exception:
            futil.log(
                f'Could not remove Restart Add-Ins from {tab_id}\n{traceback.format_exc()}',
                adsk.core.LogLevels.WarningLogLevel,
                True,
            )
    _remove_script_controls()
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()
    try:
        app.unregisterCustomEvent(RESTART_EVENT_ID)
    except Exception:
        pass
    _event_handlers.clear()


def _register_restart_event():
    try:
        app.unregisterCustomEvent(RESTART_EVENT_ID)
    except Exception:
        pass
    _event_handlers.clear()
    event = app.registerCustomEvent(RESTART_EVENT_ID)
    futil.add_handler(
        event,
        _on_restart_event,
        name='RestartAddIns_restart',
        local_handlers=_event_handlers,
    )


def command_created(args):
    cmd = adsk.core.CommandCreatedEventArgs.cast(args).command
    futil.add_handler(
        cmd.execute, command_execute, name='RestartAddIns_execute', local_handlers=local_handlers
    )
    futil.add_handler(
        cmd.destroy, command_destroy, name='RestartAddIns_destroy', local_handlers=local_handlers
    )
    # No command inputs, so Fusion runs execute as soon as this returns.
    # doExecute() here crashes Fusion: it nests execute inside commandCreated
    # and then destroys the command before creation has finished.


def command_destroy(_args):
    global local_handlers
    local_handlers = []


def command_execute(_args):
    # Stop and start after this command is gone. Doing it here deletes other
    # add-ins' controls while Fusion is still inside this command.
    _schedule_restart()


def _schedule_restart():
    global _restart_scheduled
    if _restart_scheduled:
        return
    _restart_scheduled = True

    def _fire():
        global _restart_scheduled
        try:
            app.fireCustomEvent(RESTART_EVENT_ID)
        except Exception:
            _restart_scheduled = False
            futil.log(
                f'Restart Add-Ins could not be scheduled\n{traceback.format_exc()}',
                adsk.core.LogLevels.ErrorLogLevel,
                True,
            )

    timer = threading.Timer(0.2, _fire)
    timer.daemon = True
    timer.start()


def _on_restart_event(_args):
    global _restart_scheduled
    try:
        restarted, failed = restart_user_addins()
        _report(restarted, failed)
    except Exception:
        futil.handle_error('Restart Add-Ins', show_message_box=True)
    finally:
        _restart_scheduled = False


def restart_user_addins():
    """Stop, then start, every running user add-in except this one.

    This add-in stays loaded. Stopping it from its own command would unload
    the command before the other add-ins could be started again.
    """
    targets = _running_user_addins()
    if not targets:
        return [], []

    restarted = []
    failed = []
    ready = []
    progress = _show_progress(len(targets) * 2)

    try:
        for step, (name, folder) in enumerate(targets):
            _advance_progress(progress, f'Stopping {name}', step)
            script = _script_at(folder)
            if script is None:
                failed.append((name, 'Fusion could not find this add-in.'))
                continue
            try:
                if script.isRunning:
                    stopped = script.stop()
                    if stopped is False:
                        failed.append((name, 'Fusion did not stop it. It was left running.'))
                        continue
                ready.append((name, folder))
            except Exception as error:
                failed.append((name, _failure_text(error, 'Stop failed. It was left running.')))
                futil.log(
                    f'Failed to stop {name}\n{traceback.format_exc()}',
                    adsk.core.LogLevels.ErrorLogLevel,
                    True,
                )

        # Finish unloading handlers and palettes before dropping modules.
        _pump_events()
        for name, folder in ready:
            _purge_addin_modules(folder)

        for step, (name, folder) in enumerate(ready):
            _advance_progress(progress, f'Starting {name}', len(targets) + step)
            script = _script_at(folder)
            if script is None:
                failed.append((name, 'It was stopped and could not be found to start again.'))
                continue
            try:
                if script.isRunning:
                    restarted.append(name)
                    continue
                # run() only queues the add-in. isRunning stays false until this
                # handler returns, so checking it here reports a start that
                # succeeds a moment later.
                started = script.run()
                if started is False:
                    failed.append((name, 'Fusion did not start it. It is stopped.'))
                    continue
                restarted.append(name)
                _pump_events()
            except Exception as error:
                failed.append((name, _failure_text(error, 'Start failed. It is stopped.')))
                futil.log(
                    f'Failed to start {name}\n{traceback.format_exc()}',
                    adsk.core.LogLevels.ErrorLogLevel,
                    True,
                )
    finally:
        _hide_progress(progress)

    return restarted, failed


def _running_user_addins():
    scripts = getattr(app, 'scripts', None)
    if scripts is None:
        raise RuntimeError('This version of Fusion cannot list add-ins. Restart Add-Ins needs the scripts API from October 2023 or later.')

    found = []
    for index in range(scripts.count):
        script = scripts.item(index)
        if not _is_user_addin(script) or _is_this_addin(script) or not script.isRunning:
            continue
        found.append((script.name, script.folder))
    found.sort(key=lambda item: item[0].lower())
    return found


def _is_user_addin(script):
    try:
        if not script.isAddIn or script.isInternal:
            return False
    except Exception:
        return False

    location = _source_location_value(script)
    if location is None:
        return True
    return location not in _excluded_source_locations()


def _is_this_addin(script):
    try:
        if script.id == config.ADDIN_ID:
            return True
    except Exception:
        pass
    try:
        return _norm(script.folder) == _norm(config.ADDIN_FOLDER)
    except Exception:
        return False


def _source_location_value(script):
    if not hasattr(script, 'sourceLocation'):
        return None
    try:
        return int(script.sourceLocation)
    except Exception:
        return None


def _excluded_source_locations():
    locations = getattr(adsk.core, 'ScriptSourceLocations', None)
    if locations is None:
        return set(_FALLBACK_EXCLUDED_LOCATIONS)
    excluded = set()
    for name in ('InternalScriptSourceLocation', 'SamplesScriptSourceLocation'):
        value = getattr(locations, name, None)
        if value is None:
            continue
        try:
            excluded.add(int(value))
        except Exception:
            continue
    return excluded or set(_FALLBACK_EXCLUDED_LOCATIONS)


def _script_at(folder):
    scripts = app.scripts
    try:
        script = scripts.itemByPath(folder)
        if script:
            return script
    except Exception:
        pass

    target = _norm(folder)
    for index in range(scripts.count):
        candidate = scripts.item(index)
        try:
            if _norm(candidate.folder) == target:
                return candidate
        except Exception:
            continue
    return None


def _purge_addin_modules(folder):
    """Drop cached Python modules for an add-in so the next run loads fresh files."""
    root = _norm(folder)
    own_root = _norm(config.ADDIN_FOLDER)
    if not root or root == own_root:
        return

    prefix = root + os.sep
    stale = []
    for name, module in list(sys.modules.items()):
        if module is None or name is None:
            continue
        for path in _module_paths(module):
            normalized = _norm(path)
            if normalized == root or normalized.startswith(prefix):
                stale.append(name)
                break
    for name in stale:
        sys.modules.pop(name, None)


def _module_paths(module):
    paths = []
    file_path = getattr(module, '__file__', None)
    if isinstance(file_path, str):
        paths.append(file_path)
    module_paths = getattr(module, '__path__', None)
    if module_paths is None:
        return paths
    try:
        paths.extend(path for path in module_paths if isinstance(path, str))
    except TypeError:
        pass
    return paths


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


def _place_on_tab(cmd_def, tab_id, panel_id, after_panel_id):
    tab = _toolbar_tab(tab_id)
    if not tab:
        futil.log(f'Restart Add-Ins: toolbar tab {tab_id} was not found.', force_console=True)
        return False
    panel = tab.toolbarPanels.itemById(panel_id)
    if not panel:
        try:
            panel = tab.toolbarPanels.add(panel_id, config.RIBBON_PANEL_NAME, after_panel_id, False)
        except Exception:
            futil.log(f'Restart Add-Ins: could not place a panel after {after_panel_id} on {tab_id}.')
            try:
                panel = tab.toolbarPanels.add(panel_id, config.RIBBON_PANEL_NAME, '', False)
            except Exception:
                futil.log(f'Restart Add-Ins: could not create panel on {tab_id}: {traceback.format_exc()}')
                return False
    return _place_control(panel, cmd_def)


def _place_on_script_panels(cmd_def):
    added = 0
    workspaces = ui.workspaces
    for workspace_index in range(workspaces.count):
        workspace = workspaces.item(workspace_index)
        try:
            panels = workspace.toolbarPanels
            panel_count = panels.count
        except Exception:
            continue
        for panel_index in range(panel_count):
            panel = panels.item(panel_index)
            try:
                panel_id = panel.id or ''
            except Exception:
                continue
            if 'scriptsaddins' not in panel_id.lower():
                continue
            if panel.controls.itemById(CMD_ID):
                continue
            try:
                if _place_control(panel, cmd_def, 'ScriptsManagerCommand', False):
                    added += 1
            except Exception:
                futil.log(
                    f'Could not add Restart Add-Ins to {panel_id}\n{traceback.format_exc()}',
                    adsk.core.LogLevels.WarningLogLevel,
                    True,
                )
    return added


def _place_control(panel, cmd_def, beside_id='', is_before=False):
    if panel.controls.itemById(CMD_ID):
        return True
    if beside_id and panel.controls.itemById(beside_id):
        control = panel.controls.addCommand(cmd_def, beside_id, is_before)
    else:
        control = panel.controls.addCommand(cmd_def)
    _promote(control)
    return True


def _remove_control(workspace_id, panel_id):
    workspace = ui.workspaces.itemById(workspace_id)
    panel = workspace.toolbarPanels.itemById(panel_id) if workspace else None
    if not panel:
        return
    control = panel.controls.itemById(CMD_ID)
    if control:
        control.deleteMe()


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


def _remove_script_controls():
    workspaces = ui.workspaces
    for workspace_index in range(workspaces.count):
        workspace = workspaces.item(workspace_index)
        try:
            panels = workspace.toolbarPanels
            panel_count = panels.count
        except Exception:
            continue
        for panel_index in range(panel_count):
            panel = panels.item(panel_index)
            try:
                control = panel.controls.itemById(CMD_ID)
                if control:
                    control.deleteMe()
            except Exception:
                continue


def _promote(control):
    try:
        control.isPromoted = IS_PROMOTED
    except Exception:
        pass
    try:
        control.isPromotedByDefault = IS_PROMOTED
    except Exception:
        pass


def _report(restarted, failed):
    lines = []
    if restarted:
        lines.append('Restarted:')
        lines.extend(f'  {name}' for name in restarted)
    if failed:
        if lines:
            lines.append('')
        lines.append('Could not restart:')
        lines.extend(f'  {name}: {reason}' for name, reason in failed)
    if not lines:
        lines.append('No other user add-ins are running.')
    lines.append('')
    lines.append('Restart Add-Ins stays running.')

    message = '\n'.join(lines)
    futil.log(message, force_console=True)
    if not failed:
        return
    ui.messageBox(
        message,
        'Restart Add-Ins',
        adsk.core.MessageBoxButtonTypes.OKButtonType,
        adsk.core.MessageBoxIconTypes.WarningIconType,
    )


def _failure_text(error, fallback):
    detail = str(error).strip()
    if not detail:
        return fallback
    if len(detail) > 180:
        detail = detail[:177] + '...'
    return detail


def _show_progress(maximum):
    try:
        progress = ui.progressBar
        progress.show('Restarting user add-ins', 0, maximum, False)
        return progress
    except Exception:
        return None


def _advance_progress(progress, message, value):
    if not progress:
        return
    try:
        progress.message = message
        progress.progressValue = value
    except Exception:
        pass


def _hide_progress(progress):
    if not progress:
        return
    try:
        progress.hide()
    except Exception:
        pass


def _pump_events():
    try:
        adsk.doEvents()
    except Exception:
        pass


def _norm(path):
    return os.path.normcase(os.path.normpath(path or ''))
