import json
import adsk.core, adsk.fusion
import os
import re
import csv
import subprocess
import sys
import threading
import time
import traceback
from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_PalleteShow'
CMD_NAME = 'ProParams Manager'
CMD_Description = 'Manage Global, Project, and Feature parameters'
PALETTE_NAME = 'ProParams Manager'
IS_PROMOTED = True

PALETTE_ID = config.sample_palette_id
PALETTE_URL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', 'html', 'index.html')
PALETTE_URL = PALETTE_URL.replace('\\', '/')
PALETTE_DOCKING = adsk.core.PaletteDockingStates.PaletteDockStateTop  # Options are PaletteDockStateTop, PaletteDockStateBottom, PaletteDockStateLeft, PaletteDockStateRight
PALETTE_DOCK_WIDTH = 520  # Width of the palette
PALETTE_DOCK_HEIGHT = 640  # Height of the palette
PALETTE_DOCK_POSITION_X = 385  # X position of the palette
PALETTE_DOCK_POSITION_Y = 214  # Y position of the palette

WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidScriptsAddinsPanel'
COMMAND_BESIDE_ID = 'ScriptsManagerCommand'
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# ---------------------------------------------------------------------------
# Data file locations
# ---------------------------------------------------------------------------
# Default global store lives in the user data dir (cross-document, app-wide).
# A settings file in that same dir can point DATA_FILE_GLOBAL at a shared drive.
DEFAULT_DATA_FILE_GLOBAL = os.path.join(config.USER_DIR_PATH, 'ProParams_global.json')
SETTINGS_FILE = os.path.join(config.USER_DIR_PATH, 'ProParams_settings.json')
DATA_FILE_GLOBAL = DEFAULT_DATA_FILE_GLOBAL
GLOBAL_PARAMS_FILENAME = 'ProParams_global.json'
# Legacy stores kept for one-time migration.
LEGACY_DATA_FILE_CSV = os.path.join(os.path.dirname(os.path.abspath(config.__file__)), 'ProParams_data.csv')
LEGACY_DATA_FILE_JSON = os.path.join(os.path.dirname(os.path.abspath(config.__file__)), 'ProParams_data.json')

# Attribute group used to associate user parameters with a selected entity.
FEATURE_ATTR_GROUP = 'ProParamsFeature'

WATCHER_EVENT_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_FileWatcher'

local_handlers = []
watcher_thread = None
stop_watcher_event = threading.Event()
last_mtime = 0

# The entity captured by the most recent `feature:readSelection`, reused by the
# feature add/update/delete actions.
selected_feature_entity = None


# ===========================================================================
# Lifecycle
# ===========================================================================
def start():
    _load_settings()
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)
    futil.add_handler(cmd_def.commandCreated, command_created)
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)
    control.isPromoted = IS_PROMOTED

    # Register Custom Event for File Watcher (global store changes on disk).
    custom_event = app.registerCustomEvent(WATCHER_EVENT_ID)
    if custom_event:
        futil.add_handler(custom_event, on_global_file_changed)

    # React to document changes so the Project tab stays in sync.
    try:
        futil.add_handler(app.documentActivated, on_document_activated)
    except Exception:
        futil.log(f"Could not attach documentActivated handler: {traceback.format_exc()}")

    # Start Watcher Thread
    global watcher_thread, last_mtime
    stop_watcher_event.clear()

    if os.path.exists(DATA_FILE_GLOBAL):
        last_mtime = os.path.getmtime(DATA_FILE_GLOBAL)

    watcher_thread = threading.Thread(target=watch_loop)
    watcher_thread.daemon = True
    watcher_thread.start()


def stop():
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    command_control = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    palette = ui.palettes.itemById(PALETTE_ID)
    if command_control: command_control.deleteMe()
    if command_definition: command_definition.deleteMe()
    if palette: palette.deleteMe()

    # Stop Watcher
    stop_watcher_event.set()
    try:
        app.unregisterCustomEvent(WATCHER_EVENT_ID)
    except Exception:
        pass


# ===========================================================================
# Global store file watcher
# ===========================================================================
def watch_loop():
    global last_mtime
    while not stop_watcher_event.is_set():
        if os.path.exists(DATA_FILE_GLOBAL):
            try:
                mtime = os.path.getmtime(DATA_FILE_GLOBAL)
                if last_mtime != 0 and mtime > last_mtime:
                    last_mtime = mtime
                    app.fireCustomEvent(WATCHER_EVENT_ID)
                elif last_mtime == 0:
                    last_mtime = mtime
            except Exception:
                pass
        time.sleep(1)


def on_global_file_changed(args):
    # Push the refreshed global store to the palette (if open).
    palette = ui.palettes.itemById(PALETTE_ID)
    if palette:
        try:
            palette.sendInfoToHTML('loadGlobal', json.dumps(load_global()))
        except Exception:
            futil.log(f"on_global_file_changed error: {traceback.format_exc()}")


def on_document_activated(args):
    # Selection does not survive a document change.
    global selected_feature_entity
    selected_feature_entity = None
    palette = ui.palettes.itemById(PALETTE_ID)
    if palette:
        try:
            palette.sendInfoToHTML('docActivated', json.dumps({'name': _active_doc_name()}))
        except Exception:
            futil.log(f"on_document_activated error: {traceback.format_exc()}")


# ===========================================================================
# Palette command / messaging
# ===========================================================================
def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


def command_execute(args: adsk.core.CommandEventArgs):
    futil.log(f"Command Execute: {CMD_NAME}")
    palettes = ui.palettes
    palette = palettes.itemById(PALETTE_ID)

    if palette is None:
        futil.log("Creating new palette...")
        palette = palettes.add(
            id=PALETTE_ID,
            name=PALETTE_NAME,
            htmlFileURL=PALETTE_URL,
            isVisible=True,
            showCloseButton=False,
            isResizable=True,
            width=PALETTE_DOCK_WIDTH,
            height=PALETTE_DOCK_HEIGHT,
            useNewWebBrowser=True
        )
    else:
        futil.log("Found existing palette.")

    futil.add_handler(palette.closed, palette_closed)
    futil.add_handler(palette.incomingFromHTML, palette_incoming)

    palette.width = PALETTE_DOCK_WIDTH
    palette.height = PALETTE_DOCK_HEIGHT
    palette.dockingState = PALETTE_DOCKING
    # setPosition undocks the palette, so screen coordinates only apply while floating.
    if palette.dockingState == adsk.core.PaletteDockingStates.PaletteDockStateFloating:
        palette.setPosition(PALETTE_DOCK_POSITION_X, PALETTE_DOCK_POSITION_Y)
    palette.isVisible = True


def palette_closed(args: adsk.core.UserInterfaceGeneralEventArgs):
    futil.log("Palette closed.")


def minimize_palette():
    """Hide the palette without deleting it. The toolbar command shows it again."""
    palette = ui.palettes.itemById(PALETTE_ID)
    if palette:
        palette.isVisible = False
    return {'minimized': True}


def _ok(data=None):
    return json.dumps({'ok': True, 'data': data})


def _err(message):
    return json.dumps({'ok': False, 'error': str(message)})


def palette_incoming(html_args: adsk.core.HTMLEventArgs):
    message_action = html_args.action
    futil.log(f"Incoming message from Palette: {message_action}")

    # Parse payload (JSON when possible).
    message_data = None
    if html_args.data:
        try:
            message_data = json.loads(html_args.data)
        except Exception:
            message_data = html_args.data

    try:
        html_args.returnData = route_message(message_action, message_data)
    except ValueError as e:
        futil.log(f"Rejected '{message_action}': {e}")
        html_args.returnData = _err(e)
    except Exception:
        futil.log(f"Error handling '{message_action}': {traceback.format_exc()}")
        html_args.returnData = _err(traceback.format_exc())


def route_message(action, data):
    # Housekeeping ---------------------------------------------------------
    if action == 'ready':
        return _ok({'global': load_global(), 'doc': _active_doc_name()})

    if action == 'palette:minimize':
        return _ok(minimize_palette())

    if action == 'jsLog':
        _handle_js_log(data)
        return _ok()

    if action == 'clipboard:copy':
        text = data.get('text') if isinstance(data, dict) else None
        if not isinstance(text, str):
            return _err('clipboard:copy expects text')
        copy_to_clipboard(text)
        return _ok({'copied': True})

    # Global ---------------------------------------------------------------
    if action == 'global:list':
        return _ok(load_global())
    if action == 'global:save':
        params = data.get('params') if isinstance(data, dict) else data
        if not isinstance(params, list):
            return _err('global:save expects a list of params')
        save_global(params)
        return _ok(load_global())
    if action == 'global:pushToDesign':
        params = data.get('params') if isinstance(data, dict) else None
        return _ok(push_global_to_design(params))

    # Settings -------------------------------------------------------------
    if action == 'settings:get':
        return _ok(settings_snapshot())
    if action == 'settings:browse':
        current = data.get('globalParamsPath') if isinstance(data, dict) else ''
        return _ok(browse_params_folder(current if isinstance(current, str) else ''))
    if action == 'settings:reveal':
        current = data.get('globalParamsPath') if isinstance(data, dict) else ''
        return _ok(reveal_params_file(current if isinstance(current, str) else ''))
    if action == 'settings:set':
        path = data.get('globalParamsPath') if isinstance(data, dict) else ''
        snapshot = set_global_params_path(path if isinstance(path, str) else '')
        _notify_global_reloaded()
        return _ok(snapshot)

    # Project (native design parameters) ----------------------------------
    if action == 'project:list':
        return _ok(list_project_params())
    if action == 'project:add':
        return _ok(add_project_param(data))
    if action == 'project:update':
        return _ok(update_project_param(data))
    if action == 'project:delete':
        return _ok(delete_project_param(data))

    # Feature (entity-attached params) ------------------------------------
    if action == 'feature:readSelection':
        return _ok(read_feature_selection())
    if action == 'feature:add':
        return _ok(add_feature_param(data))
    if action == 'feature:update':
        return _ok(update_feature_param(data))
    if action == 'feature:delete':
        return _ok(delete_feature_param(data))
    if action == 'feature:listAll':
        return _ok(list_all_feature_params())

    return _err(f"Unknown action: {action}")


def copy_to_clipboard(text):
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
            msg = message_data.get('message', '')
            extra = message_data.get('extra', None)
            ts = message_data.get('ts', '')
            futil.log(f"[palette.js:{level}] {msg} {json.dumps(extra) if extra is not None else ''} {ts}".strip())
        else:
            futil.log(f"[palette.js] {message_data}")
    except Exception:
        futil.log(f"Error handling jsLog: {traceback.format_exc()}")


# ===========================================================================
# Helpers
# ===========================================================================
def sanitize_name(name):
    s = re.sub(r'[^a-zA-Z0-9_]', '_', name or '')
    if s and s[0].isdigit():
        s = '_' + s
    return s


def _active_doc_name():
    try:
        doc = app.activeDocument
        return doc.name if doc else ''
    except Exception:
        return ''


def _get_design():
    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    return design


# ===========================================================================
# Global store (cross-document JSON file)
# ===========================================================================
def _paths_equal(left, right):
    return os.path.normcase(os.path.normpath(left)) == os.path.normcase(os.path.normpath(right))


def _load_settings():
    """Point the global store at the saved path, or the user-dir default."""
    global DATA_FILE_GLOBAL
    DATA_FILE_GLOBAL = DEFAULT_DATA_FILE_GLOBAL
    try:
        if not os.path.exists(SETTINGS_FILE):
            return
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        path = data.get('globalParamsPath') if isinstance(data, dict) else None
        if isinstance(path, str) and path.strip():
            DATA_FILE_GLOBAL = os.path.normpath(os.path.expanduser(path.strip()))
    except Exception:
        futil.log(f"Error loading settings: {traceback.format_exc()}")
        DATA_FILE_GLOBAL = DEFAULT_DATA_FILE_GLOBAL


def _write_settings(path):
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'globalParamsPath': path}, f, indent=2)
    except OSError as e:
        raise ValueError(f'Could not save settings: {e}') from e


def settings_snapshot():
    return {
        'globalParamsPath': DATA_FILE_GLOBAL,
        'defaultPath': DEFAULT_DATA_FILE_GLOBAL,
        'isCustom': not _paths_equal(DATA_FILE_GLOBAL, DEFAULT_DATA_FILE_GLOBAL),
    }


def _normalize_params_path(path):
    """Accept a JSON file path or a folder. Empty resets to the default file."""
    text = (path or '').strip().strip('"')
    if not text:
        return DEFAULT_DATA_FILE_GLOBAL
    text = os.path.expanduser(text)
    if not os.path.isabs(text):
        raise ValueError(
            'Enter a full path, for example \\\\server\\share\\ProParams_global.json'
        )
    if os.path.isdir(text) or not os.path.splitext(text)[1]:
        text = os.path.join(text, GLOBAL_PARAMS_FILENAME)
    elif os.path.splitext(text)[1].lower() != '.json':
        text = text + '.json'
    return os.path.normpath(text)


def _validate_params_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except OSError as e:
        raise ValueError(f'Could not read that file: {e}') from e
    except json.JSONDecodeError as e:
        raise ValueError('That file is not valid JSON.') from e
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise ValueError('That file is not a ProParams parameter list.')


def _notify_global_reloaded():
    palette = ui.palettes.itemById(PALETTE_ID)
    if not palette:
        return
    try:
        palette.sendInfoToHTML('loadGlobal', json.dumps(load_global()))
    except Exception:
        futil.log(f"_notify_global_reloaded error: {traceback.format_exc()}")


def browse_params_folder(current_path):
    """Pick a folder. The parameters file name is kept when the path is valid."""
    filename = GLOBAL_PARAMS_FILENAME
    initial = ''
    if isinstance(current_path, str) and current_path.strip():
        try:
            candidate = _normalize_params_path(current_path)
        except ValueError:
            candidate = ''
        if candidate:
            filename = os.path.basename(candidate) or filename
            folder = os.path.dirname(candidate)
            if os.path.isdir(folder):
                initial = folder

    dialog = ui.createFolderDialog()
    dialog.title = 'Folder for the parameters file'
    if initial:
        try:
            dialog.initialDirectory = initial
        except Exception:
            futil.log(f"Could not set folder dialog directory: {traceback.format_exc()}")

    if dialog.showDialog() != adsk.core.DialogResults.DialogOK:
        return {'cancelled': True, 'path': ''}
    folder = dialog.folder
    if not folder:
        return {'cancelled': True, 'path': ''}
    return {'cancelled': False, 'path': os.path.normpath(os.path.join(folder, filename))}


def _open_in_file_manager(path, select_file):
    """Open the OS file manager, selecting the file when it exists."""
    path = os.path.normpath(path)
    if sys.platform == 'win32':
        if select_file:
            # The comma is part of Explorer's /select switch.
            subprocess.Popen(['explorer', '/select,' + path])
        else:
            os.startfile(path)
        return
    if sys.platform == 'darwin':
        args = ['open', '-R', path] if select_file else ['open', path]
        subprocess.Popen(args)
        return
    folder = os.path.dirname(path) if select_file else path
    subprocess.Popen(['xdg-open', folder])


def reveal_params_file(path):
    """Open File Explorer at the parameters file, or its folder if the file is new."""
    text = (path or '').strip()
    target = _normalize_params_path(text) if text else DATA_FILE_GLOBAL
    if os.path.isfile(target):
        _open_in_file_manager(target, True)
        return {'opened': True}

    folder = target if os.path.isdir(target) else os.path.dirname(target)
    if not folder or not os.path.isdir(folder):
        raise ValueError('That folder does not exist yet.')
    _open_in_file_manager(folder, False)
    return {'opened': True}


def set_global_params_path(path):
    """Switch the global store. Existing files are loaded; missing files are created."""
    global DATA_FILE_GLOBAL, last_mtime
    normalized = _normalize_params_path(path)
    if _paths_equal(normalized, DATA_FILE_GLOBAL):
        _write_settings(normalized)
        return settings_snapshot()

    parent = os.path.dirname(normalized)
    if not parent:
        raise ValueError('Enter a full path to a .json file.')

    if os.path.exists(normalized):
        _validate_params_file(normalized)
    else:
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError as e:
            raise ValueError(f'Could not create that folder: {e}') from e
        if not os.path.isdir(parent):
            raise ValueError('That folder does not exist.')

    previous = DATA_FILE_GLOBAL
    previous_mtime = last_mtime
    current = load_global()
    DATA_FILE_GLOBAL = normalized
    try:
        if not os.path.exists(normalized):
            save_global(current)
            if not os.path.exists(normalized):
                raise ValueError('Could not create the parameters file in that folder.')
        else:
            last_mtime = os.path.getmtime(normalized)
        _write_settings(normalized)
    except Exception:
        DATA_FILE_GLOBAL = previous
        last_mtime = previous_mtime
        raise
    return settings_snapshot()


def load_global():
    """Return the global params list. Migrates the legacy CSV/JSON on first run."""
    if not os.path.exists(DATA_FILE_GLOBAL):
        migrated = _migrate_legacy()
        if migrated is not None:
            save_global(migrated)
            return migrated
        return []

    try:
        with open(DATA_FILE_GLOBAL, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return [_normalize_global(p) for p in data if isinstance(p, dict)]
        return []
    except Exception:
        futil.log(f"Error loading global store: {traceback.format_exc()}")
        return []


def _normalize_global(p):
    return {
        'name': p.get('name', ''),
        'expression': p.get('expression', p.get('value', '')),
        'unit': p.get('unit', ''),
        'comment': p.get('comment', ''),
        'category': p.get('category', ''),
    }


def save_global(params):
    global last_mtime
    normalized = [_normalize_global(p) for p in params if isinstance(p, dict) and p.get('name')]
    try:
        os.makedirs(os.path.dirname(DATA_FILE_GLOBAL), exist_ok=True)
        with open(DATA_FILE_GLOBAL, 'w', encoding='utf-8') as f:
            json.dump(normalized, f, indent=2)
        if os.path.exists(DATA_FILE_GLOBAL):
            last_mtime = os.path.getmtime(DATA_FILE_GLOBAL)
    except Exception:
        futil.log(f"Error saving global store: {traceback.format_exc()}")


def _migrate_legacy():
    """Convert the old per-project CSV/JSON into a flat global list.

    The old `Project` column becomes a `category` tag so no data is lost.
    """
    # Legacy CSV (preferred, it is what the add-in last wrote).
    if os.path.exists(LEGACY_DATA_FILE_CSV):
        try:
            out = []
            with open(LEGACY_DATA_FILE_CSV, 'r', newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = (row.get('Name') or '').strip()
                    if not name:
                        continue
                    out.append({
                        'name': name,
                        'expression': row.get('Value', ''),
                        'unit': row.get('Unit', ''),
                        'comment': row.get('Comment', ''),
                        'category': row.get('Project', '') or '',
                    })
            futil.log(f"Migrated {len(out)} params from legacy CSV.")
            return out
        except Exception:
            futil.log(f"Legacy CSV migration failed: {traceback.format_exc()}")

    # Legacy JSON ([{ name, params: [...] }]).
    if os.path.exists(LEGACY_DATA_FILE_JSON):
        try:
            out = []
            with open(LEGACY_DATA_FILE_JSON, 'r', encoding='utf-8') as f:
                projects = json.load(f)
            for proj in projects or []:
                category = proj.get('name', '')
                for p in proj.get('params', []):
                    if not p.get('name'):
                        continue
                    out.append({
                        'name': p.get('name', ''),
                        'expression': p.get('value', ''),
                        'unit': p.get('unit', ''),
                        'comment': p.get('comment', ''),
                        'category': category,
                    })
            futil.log(f"Migrated {len(out)} params from legacy JSON.")
            return out
        except Exception:
            futil.log(f"Legacy JSON migration failed: {traceback.format_exc()}")

    return None


def push_global_to_design(params=None):
    """Create/update user parameters in the active design from the global store."""
    design = _get_design()
    if not design:
        raise RuntimeError('No active design to push parameters into.')

    if params is None:
        params = load_global()

    user_params = design.userParameters
    created = 0
    updated = 0
    errors = []

    for p in params:
        name = sanitize_name(p.get('name', ''))
        if not name:
            continue
        expression = _normalize_expression(p.get('expression', p.get('value', '')))
        unit = p.get('unit', '') or ''
        comment = p.get('comment', '') or ''
        try:
            existing = user_params.itemByName(name)
            if existing:
                _assign_expression_and_unit(existing, expression, unit or _parameter_unit(existing))
                existing.comment = comment
                updated += 1
            else:
                _create_user_parameter(user_params, name, expression, unit, comment)
                created += 1
        except Exception as e:
            errors.append(f"{name}: {e}")

    return {'created': created, 'updated': updated, 'errors': errors}


# ===========================================================================
# Project parameters (native design parameters)
# ===========================================================================
def _expression_is_editable(param, is_user):
    """Driving dimensions and user parameters can change expression.

    A sketch dimension that is driven (a measurement, not an input) exposes
    isDriving=False on the object that created the parameter. Those stay
    read-only. Feature dimensions have no such flag and are editable.
    """
    if is_user:
        return True
    try:
        created_by = param.createdBy
    except Exception:
        return True
    if created_by is None:
        return True
    try:
        is_driving = created_by.isDriving
    except Exception:
        return True
    return bool(is_driving)


def _format_number(number):
    try:
        value = float(number)
    except (TypeError, ValueError):
        return '' if number is None else str(number)
    if value != value:
        return ''
    text = format(value, '.8f').rstrip('0').rstrip('.')
    if text in ('', '-0'):
        return '0'
    return text


def _parameter_unit(param):
    try:
        return param.unit or ''
    except Exception:
        return ''


def _display_value(design, param):
    """Expression result in the parameter's unit. `param.value` is internal (cm, rad)."""
    try:
        internal = param.value
    except Exception:
        return ''
    unit = _parameter_unit(param)
    if design is not None and unit:
        try:
            text = design.unitsManager.formatInternalValue(internal, unit, False)
            if text:
                return text
        except Exception:
            pass
    return _format_number(internal)


def _dimension_owner(param):
    """Driving sketch dimension that owns this parameter, when it has a value."""
    try:
        owner = param.createdBy
    except Exception:
        return None
    if owner is None:
        return None
    try:
        if owner.isDriving is False:
            return None
    except Exception:
        pass
    try:
        owner.value
    except Exception:
        return None
    return owner


def _values_close(left, right):
    return abs(left - right) <= 1e-8 * max(1.0, abs(right))


def _write_dimension_value(design, param, expression, unit):
    """Store the expression's numeric result on the dimension. False when it cannot."""
    owner = _dimension_owner(param)
    if owner is None or design is None or not expression:
        return False
    units = unit if unit else _parameter_unit(param)
    try:
        internal = design.unitsManager.evaluateExpression(expression, units or '')
    except Exception:
        futil.log(f"Could not evaluate '{expression}': {traceback.format_exc()}")
        return False
    try:
        current = float(owner.value)
        already = _values_close(current, internal)
    except Exception:
        already = False
    if already:
        return True
    try:
        saved_expression = param.expression or expression
    except Exception:
        saved_expression = expression
    try:
        owner.value = internal
    except Exception:
        futil.log(f"Could not set dimension value: {traceback.format_exc()}")
        return False
    # Writing the dimension value replaces the expression with a literal.
    # Put the user's expression back when the dimension keeps the result.
    if saved_expression:
        try:
            if (param.expression or '') != saved_expression:
                param.expression = saved_expression
        except Exception:
            futil.log(f"Could not restore expression '{saved_expression}': {traceback.format_exc()}")
        try:
            if not _values_close(float(owner.value), internal):
                owner.value = internal
        except Exception:
            futil.log(f"Dimension value did not stick: {traceback.format_exc()}")
    return True


def _serialize_param(param, is_user, is_deletable):
    try:
        expression = param.expression
    except Exception:
        expression = ''
    value = _display_value(_get_design(), param)
    try:
        unit = param.unit
    except Exception:
        unit = ''
    try:
        comment = param.comment
    except Exception:
        comment = ''
    return {
        'name': param.name,
        'expression': expression,
        'value': value,
        'unit': unit,
        'comment': comment,
        'isUserParam': is_user,
        'isDeletable': is_deletable,
        'isEditable': _expression_is_editable(param, is_user),
    }


def _global_user_param_names():
    """Names the global store writes into a design. They stay out of the project list."""
    names = set()
    for param in load_global():
        name = sanitize_name(param.get('name', ''))
        if name:
            names.add(name)
    return names


def list_project_params():
    design = _get_design()
    if not design:
        return []

    # Pushing the global store creates user parameters so expressions can
    # reference them. Those belong on the Global tab, not in this list.
    global_names = _global_user_param_names()
    result = []
    user_params = design.userParameters
    for i in range(user_params.count):
        p = user_params.item(i)
        if p.name in global_names:
            continue
        result.append(_serialize_param(p, True, p.isDeletable))

    # Model parameters belong to components, not Design. allParameters is the
    # design-wide list: user parameters plus sketch and feature dimensions from
    # every local component. Driving dimensions stay editable; driven ones do not.
    all_params = design.allParameters
    for i in range(all_params.count):
        model_param = adsk.fusion.ModelParameter.cast(all_params.item(i))
        if not model_param:
            continue
        result.append(_serialize_param(model_param, False, False))

    return result


def add_project_param(data):
    design = _get_design()
    if not design:
        raise RuntimeError('No active design.')
    name = sanitize_name(data.get('name', ''))
    expression = _normalize_expression(data.get('expression', ''))
    unit = data.get('unit', '') or ''
    comment = data.get('comment', '') or ''
    if not name or not expression:
        raise ValueError('Name and expression are required.')
    if name in _global_user_param_names():
        raise ValueError(
            f"Cannot create '{name}'. That name matches a global parameter."
        )

    user_params = design.userParameters
    if user_params.itemByName(name):
        raise ValueError(f"A parameter named '{name}' already exists.")

    new_param = _create_user_parameter(user_params, name, expression, unit, comment)
    return _serialize_param(new_param, True, new_param.isDeletable)


# One number, optionally one unit token. Anything else is a formula.
_SIMPLE_VALUE = re.compile(
    r'^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?'
    r'(?:[ \t]*[A-Za-zμµ°"″\'′][A-Za-z0-9μµ°"″\'′/^._-]*)?$'
)


def _normalize_expression(expression):
    """Fusion has no spreadsheet `=`. One leading equals sign is removed."""
    text = '' if expression is None else str(expression).strip()
    if text.startswith('=') and not text.startswith('=='):
        return text[1:].strip()
    return text


def _expression_is_formula(expression):
    text = (expression or '').strip()
    if not text:
        return False
    return _SIMPLE_VALUE.fullmatch(text) is None


def _read_expression(param):
    try:
        return param.expression or ''
    except Exception:
        return ''


def _expression_evaluates(design, expression, unit):
    if design is None or not expression:
        return False
    try:
        design.unitsManager.evaluateExpression(expression, unit or '')
        return True
    except Exception:
        return False


# Typed unit words and symbols that Fusion's converter may not accept directly.
_UNIT_ALIASES = {
    '"': 'in', '″': 'in', '“': 'in', '”': 'in',
    "'": 'ft', '′': 'ft', '‘': 'ft', '’': 'ft',
    '°': 'deg',
    'inch': 'in', 'inches': 'in',
    'foot': 'ft', 'feet': 'ft',
    'degree': 'deg', 'degrees': 'deg',
    'millimeter': 'mm', 'millimetre': 'mm',
}

# A number and the unit token written on it. Bare numbers and parameter names are ignored.
_NUMBER_UNIT = re.compile(
    r'(?<![A-Za-z0-9_.])'
    r'([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)'
    r'[ \t]*'
    r'([A-Za-zμµ°"″\'′“”‘’][A-Za-z0-9μµ°"″\'′/^._-]*)'
)


def _same_unit(left, right):
    return (left or '').lower() == (right or '').lower()


def _unit_sources(token):
    sources = []
    raw = (token or '').strip()
    if raw:
        sources.append(raw)
    alias = _UNIT_ALIASES.get(raw)
    if alias is None:
        alias = _UNIT_ALIASES.get(raw.lower())
    if alias and alias not in sources:
        sources.append(alias)
    return sources


def _literal_in_unit(design, number, token, unit):
    """Value of `number token` measured in `unit`, or None when it cannot convert."""
    for source in _unit_sources(token):
        if _same_unit(source, unit):
            return _format_number(float(number))
        internal = None
        for default_unit in (source, unit):
            try:
                internal = design.unitsManager.evaluateExpression(
                    f'{number} {source}', default_unit
                )
                break
            except Exception:
                internal = None
        if internal is None:
            continue
        try:
            text = design.unitsManager.formatInternalValue(internal, unit, False)
        except Exception:
            continue
        cleaned = str(text or '').strip()
        if not cleaned:
            continue
        if cleaned.lower().endswith(unit.lower()):
            cleaned = cleaned[: -len(unit)].strip()
        try:
            return _format_number(float(cleaned.replace(',', '')))
        except (TypeError, ValueError):
            continue
    return None


def _rewrite_literals(design, expression, unit, suffix):
    """Rewrite unit literals into `unit`.

    Fusion rejects `10 mm + 5 in` with "Expression is invalid". The same math
    with one unit, `10 mm + 127 mm` or `10 + 127`, is accepted. Parameter names
    are left as written. Returns None when a bare rewrite would drop a unit
    that could not be converted.
    """
    if not design or not unit or unit == 'Text' or not expression:
        return None
    pieces = []
    cursor = 0
    changed = False
    for match in _NUMBER_UNIT.finditer(expression):
        number, token = match.group(1), match.group(2)
        sources = _unit_sources(token)
        same = any(_same_unit(source, unit) for source in sources)
        if same:
            replacement = _format_number(float(number)) if not suffix else None
        else:
            converted = _literal_in_unit(design, number, token, unit)
            if converted is None:
                if not suffix:
                    return None
                continue
            replacement = f'{converted} {unit}' if suffix else converted
        if replacement is None:
            continue
        pieces.append(expression[cursor:match.start()])
        pieces.append(replacement)
        cursor = match.end()
        changed = True
    if not changed:
        return None
    pieces.append(expression[cursor:])
    return ''.join(pieces)


def _has_foreign_unit(expression, unit):
    """True when a literal uses a unit other than the parameter unit."""
    if not unit:
        return False
    for match in _NUMBER_UNIT.finditer(expression or ''):
        sources = _unit_sources(match.group(2))
        if sources and not any(_same_unit(source, unit) for source in sources):
            return True
    return False


def _expression_attempts(design, expression, unit):
    """Forms to try, rewritten ones first when the text mixes units.

    Assigning `10 mm + 5 in` directly makes Fusion show "Expression is invalid".
    The converted forms are sent instead of that string.
    """
    rewritten = []
    for suffix in (True, False):
        candidate = _rewrite_literals(design, expression, unit, suffix)
        if candidate and candidate not in rewritten:
            rewritten.append(candidate)
    if rewritten and _has_foreign_unit(expression, unit):
        return rewritten
    attempts = [expression]
    for candidate in rewritten:
        if candidate not in attempts:
            attempts.append(candidate)
    return attempts


def _try_set_unit(param, unit):
    """Set the parameter unit. Fusion's UserParameter.unit is often read-only.

    Returns True when the parameter already uses `unit` or the assignment stuck.
    A failed assignment is ignored so the expression can still be saved.
    """
    unit = unit or ''
    if _parameter_unit(param) == unit:
        return True
    try:
        param.unit = unit
    except Exception:
        futil.log(
            f"Parameter unit is read-only; left it as '{_parameter_unit(param)}': {traceback.format_exc()}"
        )
        return _parameter_unit(param) == unit
    return _parameter_unit(param) == unit


def _write_expression(param, expression, unit):
    """Store `expression`. Mixed-unit formulas are rewritten into the result unit.

    Fusion reports "Expression is invalid" for `10 mm + 5 in` even though the
    lengths are compatible. Each literal is converted into the parameter unit
    and the formula is saved as `10 mm + 127 mm`. The parameter unit itself is
    not assigned here; on current Fusion that property has no setter.
    """
    if not expression or _read_expression(param) == expression:
        return
    design = _get_design()
    target = _parameter_unit(param) or unit or ''
    attempts = _expression_attempts(design, expression, target)
    first_error = None
    for candidate in attempts:
        try:
            if _read_expression(param) != candidate:
                param.expression = candidate
            return
        except Exception as error:
            if first_error is None:
                first_error = error
    if first_error is None:
        return
    if not _expression_is_formula(expression) or not target or target == 'Text':
        raise first_error
    stored = attempts[-1]
    if not _expression_evaluates(design, stored, target):
        futil.log(
            f"Expression rejected: {expression!r} unit={target!r} attempts={attempts!r}: {first_error}",
            adsk.core.LogLevels.ErrorLogLevel,
        )
        raise first_error
    saved = _read_expression(param)
    placeholder_unit = _parameter_unit(param) or target
    try:
        param.expression = f'0 {placeholder_unit}' if placeholder_unit else '0'
        param.expression = stored
    except Exception:
        futil.log(f"Priming expression '{expression}' failed: {traceback.format_exc()}")
        try:
            if saved and _read_expression(param) != saved:
                param.expression = saved
        except Exception:
            futil.log(f"Could not restore expression '{saved}': {traceback.format_exc()}")
        raise first_error


def _assign_expression_and_unit(param, expression, unit):
    """Set a user parameter's expression and, when Fusion allows it, its unit.

    A plain number is applied by changing the unit first, so `5` becomes `5 mm`.
    A formula is written in the parameter's current unit. `10 mm + 5 in` is
    converted before it is stored. The unit property has no setter on current
    Fusion, so a refused unit change does not fail the save.
    """
    expression = _normalize_expression(expression)
    unit = unit or ''
    current_unit = _parameter_unit(param)
    current_expression = _read_expression(param)

    if expression == current_expression and unit == current_unit:
        return

    if _expression_is_formula(expression):
        target = current_unit
        if unit and unit != current_unit and _try_set_unit(param, unit):
            target = unit
        _write_expression(param, expression, target or unit)
        return

    if unit != current_unit and _try_set_unit(param, unit):
        current_unit = _parameter_unit(param)

    if not expression or expression == _read_expression(param):
        return
    try:
        param.expression = expression
    except Exception:
        futil.log(f"Setting expression failed: {traceback.format_exc()}")
        _write_expression(param, expression, current_unit or unit)


def _create_user_parameter(user_params, name, expression, unit, comment):
    """Add a user parameter. A mixed-unit formula is stored in `unit`."""
    expression = _normalize_expression(expression)
    unit = unit or ''
    design = _get_design()
    attempts = _expression_attempts(design, expression, unit)
    first_error = None
    for attempt in attempts:
        try:
            value_input = adsk.core.ValueInput.createByString(attempt)
            return user_params.add(name, value_input, unit, comment)
        except Exception as error:
            first_error = error
    if (
        first_error is None
        or not unit
        or unit == 'Text'
        or not _expression_is_formula(expression)
        or not _expression_evaluates(design, attempts[-1], unit)
    ):
        if first_error is None:
            raise RuntimeError(f"Could not create parameter '{name}'.")
        raise first_error
    placeholder = adsk.core.ValueInput.createByString(f'0 {unit}')
    created = user_params.add(name, placeholder, unit, comment)
    try:
        _write_expression(created, attempts[-1], unit)
    except Exception:
        try:
            created.deleteMe()
        except Exception:
            futil.log(
                f"Could not delete placeholder parameter '{name}': {traceback.format_exc()}"
            )
        raise first_error
    return created


def update_project_param(data):
    design = _get_design()
    if not design:
        raise RuntimeError('No active design.')
    original = data.get('originalName', '')
    # Model dimensions (sketch and feature sizes) live outside userParameters.
    param = design.allParameters.itemByName(original)
    if not param:
        raise ValueError(f"Parameter '{original}' not found.")

    is_user = design.userParameters.itemByName(original) is not None
    if not _expression_is_editable(param, is_user):
        raise ValueError(f"'{original}' is a driven dimension and cannot be edited.")

    new_name = sanitize_name(data.get('name', original))
    if new_name and new_name != param.name and new_name in _global_user_param_names():
        raise ValueError(
            f"Cannot rename '{original}' to '{new_name}'. That name matches a global parameter."
        )
    expression = _normalize_expression(data.get('expression', _read_expression(param)))
    comment = data.get('comment', '')
    unit_provided = isinstance(data, dict) and 'unit' in data

    unit_for_value = (data.get('unit') or '') if unit_provided else _parameter_unit(param)
    try:
        if is_user and unit_provided:
            _assign_expression_and_unit(param, expression, data.get('unit') or '')
        elif expression and expression != _read_expression(param):
            _write_expression(param, expression, unit_for_value or _parameter_unit(param))
        param.comment = comment or ''
        if new_name and new_name != param.name:
            param.name = new_name
    except Exception as e:
        wrote = (not is_user) and _write_dimension_value(design, param, expression, unit_for_value)
        if not wrote:
            raise ValueError(str(e)) from e
        try:
            param.comment = comment or ''
            if new_name and new_name != param.name:
                param.name = new_name
        except Exception as name_error:
            raise ValueError(str(name_error)) from name_error
    else:
        if not is_user:
            _write_dimension_value(design, param, expression, unit_for_value)

    still_user = design.userParameters.itemByName(param.name) is not None
    return _serialize_param(param, still_user, param.isDeletable if still_user else False)


def delete_project_param(data):
    design = _get_design()
    if not design:
        raise RuntimeError('No active design.')
    name = data.get('name', '')
    param = design.userParameters.itemByName(name)
    if not param:
        raise ValueError(f"Parameter '{name}' not found.")
    if not param.isDeletable:
        raise ValueError(f"Parameter '{name}' is in use and cannot be deleted.")
    param.deleteMe()
    return {'name': name}


# ===========================================================================
# Feature parameters (user params associated with a selected entity)
# ===========================================================================
def _entity_label(entity):
    try:
        type_name = entity.objectType.split('::')[-1]
    except Exception:
        type_name = 'Entity'
    name = ''
    try:
        name = entity.name
    except Exception:
        name = ''
    return (f"{type_name}: {name}" if name else type_name), type_name


def _feature_params_for_entity(entity):
    """Read the ProParams feature attributes on an entity and resolve each to its
    user parameter."""
    design = _get_design()
    params = []
    if not entity or not design:
        return params
    try:
        attrs = entity.attributes
    except Exception:
        return params

    user_params = design.userParameters
    for i in range(attrs.count):
        attr = attrs.item(i)
        if attr.groupName != FEATURE_ATTR_GROUP:
            continue
        param_name = attr.value or attr.name
        up = user_params.itemByName(param_name)
        if up:
            params.append({
                'name': up.name,
                'expression': up.expression,
                'value': _display_value(design, up),
                'unit': up.unit,
                'comment': up.comment,
            })
        else:
            # Attribute left dangling (param deleted elsewhere) - surface it anyway.
            params.append({
                'name': param_name,
                'expression': '',
                'value': '',
                'unit': '',
                'comment': '(missing parameter)',
            })
    return params


def read_feature_selection():
    global selected_feature_entity
    selections = ui.activeSelections
    if selections.count == 0:
        selected_feature_entity = None
        return {'hasSelection': False, 'params': []}

    entity = selections.item(0).entity
    selected_feature_entity = entity
    label, type_name = _entity_label(entity)
    return {
        'hasSelection': True,
        'entity': {'label': label, 'entityType': type_name},
        'params': _feature_params_for_entity(entity),
    }


def _require_selected_entity():
    entity = selected_feature_entity
    if entity is None:
        # Fall back to the live selection if still present.
        selections = ui.activeSelections
        if selections.count > 0:
            entity = selections.item(0).entity
    if entity is None:
        raise RuntimeError('No entity selected. Click "Read selection" after selecting a face, edge, or body.')
    return entity


def _tag_entity(entity, param_name):
    try:
        entity.attributes.add(FEATURE_ATTR_GROUP, param_name, param_name)
    except Exception:
        futil.log(f"Could not tag entity with '{param_name}': {traceback.format_exc()}")


def add_feature_param(data):
    design = _get_design()
    if not design:
        raise RuntimeError('No active design.')
    entity = _require_selected_entity()

    name = sanitize_name(data.get('name', ''))
    expression = _normalize_expression(data.get('expression', ''))
    unit = data.get('unit', '') or ''
    comment = data.get('comment', '') or ''
    if not name or not expression:
        raise ValueError('Name and expression are required.')

    user_params = design.userParameters
    existing = user_params.itemByName(name)
    if existing:
        # Reuse the existing user parameter but associate it with this entity.
        _assign_expression_and_unit(existing, expression, unit or _parameter_unit(existing))
        existing.comment = comment
    else:
        _create_user_parameter(user_params, name, expression, unit, comment)

    _tag_entity(entity, name)
    return read_feature_selection()


def update_feature_param(data):
    design = _get_design()
    if not design:
        raise RuntimeError('No active design.')
    entity = _require_selected_entity()
    original = data.get('originalName', '')
    user_params = design.userParameters
    param = user_params.itemByName(original)
    if not param:
        raise ValueError(f"Parameter '{original}' not found.")

    new_name = sanitize_name(data.get('name', original))
    expression = _normalize_expression(data.get('expression', param.expression))
    comment = data.get('comment', '')
    unit_provided = isinstance(data, dict) and 'unit' in data

    if unit_provided:
        _assign_expression_and_unit(param, expression, data.get('unit') or '')
    elif expression and expression != param.expression:
        param.expression = expression
    param.comment = comment or ''
    if new_name and new_name != param.name:
        # Re-tag the entity under the new name.
        _remove_entity_tag(entity, original)
        param.name = new_name
        _tag_entity(entity, new_name)

    return read_feature_selection()


def _remove_entity_tag(entity, param_name):
    try:
        attrs = entity.attributes
        attr = attrs.itemByName(FEATURE_ATTR_GROUP, param_name)
        if attr:
            attr.deleteMe()
    except Exception:
        futil.log(f"Could not remove tag '{param_name}': {traceback.format_exc()}")


def delete_feature_param(data):
    design = _get_design()
    if not design:
        raise RuntimeError('No active design.')
    entity = _require_selected_entity()
    name = data.get('name', '')

    # Remove the association from the entity.
    _remove_entity_tag(entity, name)

    # Delete the backing user parameter if it is no longer used elsewhere.
    param = design.userParameters.itemByName(name)
    if param and param.isDeletable:
        try:
            param.deleteMe()
        except Exception:
            futil.log(f"Could not delete user param '{name}': {traceback.format_exc()}")

    return read_feature_selection()


def list_all_feature_params():
    design = _get_design()
    if not design:
        return {'entities': []}
    entities = []
    try:
        attrs = design.findAttributes(FEATURE_ATTR_GROUP, '')
        seen = {}
        for attr in attrs:
            parent = attr.parent
            if parent is None:
                continue
            key = id(parent)
            if key not in seen:
                label, type_name = _entity_label(parent)
                seen[key] = {'label': label, 'entityType': type_name, 'params': _feature_params_for_entity(parent)}
        entities = list(seen.values())
    except Exception:
        futil.log(f"list_all_feature_params error: {traceback.format_exc()}")
    return {'entities': entities}


def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
