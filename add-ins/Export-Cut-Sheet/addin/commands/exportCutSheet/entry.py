import datetime
import os
import re
import subprocess
import sys
import traceback

import adsk.core
import adsk.fusion

from ...lib import fusion360utils as futil
from ... import config
from . import bodies as body_utils
from . import csv_export
from . import drawing

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_Export'
CMD_NAME = 'Export Cut Sheet'
CMD_DESCRIPTION = (
    'Export visible bodies to a CSV cut sheet and a PDF of dimensioned '
    'drawings, a shaded home view of each part, and a cut sheet table.'
)
IS_PROMOTED = True
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

INPUT_SCOPE = 'scope'
INPUT_BODIES = 'bodies'
INPUT_UNITS = 'units'
INPUT_DECIMALS = 'decimals'
INPUT_FRACTIONS = 'useFractions'
INPUT_FRACTION_PRECISION = 'fractionPrecision'
INPUT_CSV = 'exportCsv'
INPUT_PDF = 'exportPdf'
INPUT_PAGE = 'pageSize'

SCOPE_VISIBLE = 'All visible bodies'
SCOPE_SELECTED = 'Selected bodies'

# Remembered between runs while the add-in stays loaded.
_settings = {
    'scope': SCOPE_VISIBLE,
    'units': None,
    'decimals': 3,
    'fractions': False,
    'denominator': 16,
    'csv': False,
    'pdf': True,
    'page': 'Letter',
}

local_handlers = []


def start():
    existing = ui.commandDefinitions.itemById(CMD_ID)
    if existing:
        existing.deleteMe()

    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_DESCRIPTION, ICON_FOLDER
    )
    futil.add_handler(cmd_def.commandCreated, command_created, name='ExportCutSheet_commandCreated')

    try:
        if not _place_on_tab(cmd_def):
            futil.log('Export Cut Sheet could not find the Solid tab.', adsk.core.LogLevels.WarningLogLevel, True)
    except Exception:
        futil.log(
            f'Could not add Export Cut Sheet to the toolbar\n{traceback.format_exc()}',
            adsk.core.LogLevels.WarningLogLevel,
            True,
        )


def stop():
    try:
        _remove_from_tab()
    except Exception:
        futil.log(
            f'Could not remove Export Cut Sheet from the toolbar\n{traceback.format_exc()}',
            adsk.core.LogLevels.WarningLogLevel,
            True,
        )
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()


def command_created(args):
    event_args = adsk.core.CommandCreatedEventArgs.cast(args)
    cmd = event_args.command
    inputs = cmd.commandInputs

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        ui.messageBox('Open a design before exporting a cut sheet.', CMD_NAME)
        return

    scope = inputs.addDropDownCommandInput(
        INPUT_SCOPE, 'Bodies', adsk.core.DropDownStyles.TextListDropDownStyle
    )
    for name in (SCOPE_VISIBLE, SCOPE_SELECTED):
        scope.listItems.add(name, name == _settings['scope'])

    selection = inputs.addSelectionInput(INPUT_BODIES, 'Select', 'Select the bodies to export')
    selection.addSelectionFilter(adsk.core.SelectionCommandInput.SolidBodies)
    selection.setSelectionLimits(0)
    selection.isVisible = _settings['scope'] == SCOPE_SELECTED

    units = inputs.addDropDownCommandInput(
        INPUT_UNITS, 'Units', adsk.core.DropDownStyles.TextListDropDownStyle
    )
    current_units = _settings['units'] or _design_units(design)
    for unit in body_utils.UNIT_CHOICES:
        units.listItems.add(unit, unit == current_units)

    inputs.addBoolValueInput(INPUT_FRACTIONS, 'Use fractions', True, '', _settings['fractions'])

    precision = inputs.addDropDownCommandInput(
        INPUT_FRACTION_PRECISION, 'Fraction precision', adsk.core.DropDownStyles.TextListDropDownStyle
    )
    for denominator in drawing.FRACTION_DENOMINATORS:
        precision.listItems.add(_fraction_label(denominator), denominator == _settings['denominator'])

    inputs.addIntegerSpinnerCommandInput(INPUT_DECIMALS, 'Decimal places', 0, 6, 1, _settings['decimals'])
    _sync_number_inputs(inputs)

    inputs.addBoolValueInput(INPUT_CSV, 'CSV', True, '', _settings['csv'])
    inputs.addBoolValueInput(INPUT_PDF, 'PDF', True, '', _settings['pdf'])

    page = inputs.addDropDownCommandInput(
        INPUT_PAGE, 'Page size', adsk.core.DropDownStyles.TextListDropDownStyle
    )
    for name in drawing.PAGE_SIZES:
        page.listItems.add(name, name == _settings['page'])
    page.isEnabled = _settings['pdf']

    futil.add_handler(cmd.execute, command_execute, name='ExportCutSheet_execute', local_handlers=local_handlers)
    futil.add_handler(cmd.inputChanged, command_input_changed, name='ExportCutSheet_inputChanged', local_handlers=local_handlers)
    futil.add_handler(cmd.validateInputs, command_validate, name='ExportCutSheet_validate', local_handlers=local_handlers)
    futil.add_handler(cmd.destroy, command_destroy, name='ExportCutSheet_destroy', local_handlers=local_handlers)


def command_input_changed(args):
    event_args = adsk.core.InputChangedEventArgs.cast(args)
    inputs = event_args.inputs
    changed = event_args.input

    if changed.id == INPUT_SCOPE:
        selection = inputs.itemById(INPUT_BODIES)
        selection.isVisible = _selected_name(inputs, INPUT_SCOPE) == SCOPE_SELECTED
    elif changed.id in (INPUT_UNITS, INPUT_FRACTIONS):
        _sync_number_inputs(inputs)
    elif changed.id == INPUT_PDF:
        inputs.itemById(INPUT_PAGE).isEnabled = inputs.itemById(INPUT_PDF).value


def command_validate(args):
    event_args = adsk.core.ValidateInputsEventArgs.cast(args)
    inputs = event_args.inputs
    wants_output = inputs.itemById(INPUT_CSV).value or inputs.itemById(INPUT_PDF).value
    if not wants_output:
        event_args.areInputsValid = False
        return
    if _selected_name(inputs, INPUT_SCOPE) == SCOPE_SELECTED:
        event_args.areInputsValid = inputs.itemById(INPUT_BODIES).selectionCount > 0


def command_destroy(_args):
    global local_handlers
    local_handlers = []


def command_execute(args):
    event_args = adsk.core.CommandEventArgs.cast(args)
    inputs = event_args.command.commandInputs

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        ui.messageBox('Open a design before exporting a cut sheet.', CMD_NAME)
        return

    _settings['scope'] = _selected_name(inputs, INPUT_SCOPE)
    _settings['units'] = _selected_name(inputs, INPUT_UNITS)
    _settings['decimals'] = inputs.itemById(INPUT_DECIMALS).value
    _settings['fractions'] = inputs.itemById(INPUT_FRACTIONS).value
    _settings['denominator'] = _denominator_from_label(_selected_name(inputs, INPUT_FRACTION_PRECISION))
    _settings['csv'] = inputs.itemById(INPUT_CSV).value
    _settings['pdf'] = inputs.itemById(INPUT_PDF).value
    _settings['page'] = _selected_name(inputs, INPUT_PAGE)

    selected = None
    if _settings['scope'] == SCOPE_SELECTED:
        selection = inputs.itemById(INPUT_BODIES)
        selected = [selection.selection(i).entity for i in range(selection.selectionCount)]

    candidates = body_utils.collect(design, selected)
    if not candidates:
        ui.messageBox('No visible solid bodies were found to export.', CMD_NAME)
        return

    folder = _ask_folder()
    if not folder:
        return

    _run_export(design, candidates, folder)


def _run_export(design, candidates, folder):
    fmt = drawing.LengthFormat(
        unit=_settings['units'],
        decimals=_settings['decimals'],
        denominator=_settings['denominator'] if _settings['fractions'] else 0,
    )
    doc_name = _document_name(design)
    safe_name = _safe_filename(doc_name)

    measured = []
    failed = []
    progress = _show_progress('Measuring bodies', len(candidates))
    try:
        frame = _view_frame(design)
        for index, candidate in enumerate(candidates):
            _advance_progress(progress, f'Measuring {candidate.name}', index)
            try:
                measured.append(body_utils.measure(candidate, frame))
            except Exception:
                failed.append((candidate.name, 'could not be measured'))
                futil.log(
                    f'Export Cut Sheet: failed to measure {candidate.name}\n{traceback.format_exc()}',
                    adsk.core.LogLevels.ErrorLogLevel,
                )
    finally:
        _hide_progress(progress)

    lines = []
    written = []
    drawn_keys = set()

    if _settings['pdf']:
        if measured:
            pdf_path = os.path.join(folder, f'{safe_name}_drawings.pdf')
            overview = _build_overview(design, candidates, doc_name, failed)
            pages, pdf_failed, drawn_keys = _write_pdf(pdf_path, measured, doc_name, fmt, overview, design)
            failed.extend(pdf_failed)
            if pages:
                written.append(pdf_path)
                lines.append(f'PDF: {pages} pages')
                lines.append(f'  {pdf_path}')
        else:
            lines.append('PDF: no bodies to draw, so no PDF was written.')

    if _settings['csv']:
        csv_path = os.path.join(folder, f'{safe_name}_cut_sheet.csv')

        try:
            count, complex_count = csv_export.write(
                csv_path, measured, fmt, lambda info: _note_for(info, drawn_keys)
            )
            written.append(csv_path)
            lines.append(f'CSV: {count} bodies ({complex_count} complex shapes noted)')
            lines.append(f'  {csv_path}')
        except Exception:
            failed.append(('CSV', _short_error()))
            futil.log(f'Export Cut Sheet: CSV failed\n{traceback.format_exc()}', adsk.core.LogLevels.ErrorLogLevel)

    if failed:
        lines.append('')
        lines.append('Problems:')
        lines.extend(f'  {name}: {reason}' for name, reason in failed)

    if not lines:
        lines.append('Nothing was exported.')

    message = '\n'.join(lines)
    futil.log(f'Export Cut Sheet\n{message}', force_console=True)

    if written:
        result = ui.messageBox(
            message + '\n\nOpen the output folder?',
            CMD_NAME,
            adsk.core.MessageBoxButtonTypes.YesNoButtonType,
            adsk.core.MessageBoxIconTypes.InformationIconType,
        )
        if result == adsk.core.DialogResults.DialogYes:
            _open_folder(folder)
    else:
        ui.messageBox(
            message,
            CMD_NAME,
            adsk.core.MessageBoxButtonTypes.OKButtonType,
            adsk.core.MessageBoxIconTypes.WarningIconType,
        )


def _part_home_frame(design):
    """Home axes for part pages, or None when the design has no ViewCube to read."""
    if design is None:
        return None
    try:
        return body_utils.part_home_frame(design)
    except Exception:
        futil.log(
            f'Export Cut Sheet: could not read the Home view, using the standard isometric\n{traceback.format_exc()}',
            adsk.core.LogLevels.WarningLogLevel,
        )
        return None


def _home_view(info, frame):
    """Shaded home view of one part. A failure still leaves the orthographic views."""
    try:
        return body_utils.extract_home_view(info, frame)
    except Exception:
        futil.log(
            f'Export Cut Sheet: could not shade the home view of {info.name}\n{traceback.format_exc()}',
            adsk.core.LogLevels.WarningLogLevel,
        )
        return None


def _view_frame(design):
    try:
        return body_utils.view_frame(design)
    except Exception:
        futil.log(
            f'Export Cut Sheet: could not read the Front view, drawing parts in their own frame\n{traceback.format_exc()}',
            adsk.core.LogLevels.WarningLogLevel,
        )
        return None


def _build_overview(design, candidates, doc_name, failed):
    """Overview of every visible body, even when only some bodies were selected."""
    progress = _show_progress('Drawing model overview', 1)
    try:
        _advance_progress(progress, 'Drawing model overview', 0)
        if _settings['scope'] == SCOPE_SELECTED:
            candidates = body_utils.collect(design) or candidates
        views = body_utils.extract_overview(design, candidates)
        if all(view.is_empty() for view in views.values()):
            return None
        return drawing.OverviewSheet(views=views, document_name=doc_name, body_count=len(candidates))
    except Exception:
        failed.append(('Model overview', 'could not be drawn'))
        futil.log(f'Export Cut Sheet: overview failed\n{traceback.format_exc()}', adsk.core.LogLevels.ErrorLogLevel)
        return None
    finally:
        _hide_progress(progress)


def _write_pdf(path, infos, doc_name, fmt, overview=None, design=None):
    groups = sorted(
        body_utils.group_identical(infos),
        key=lambda group: (group[0].name.lower(), group[0].name),
    )
    failed = []
    sheets = []
    home_frame = _part_home_frame(design)
    progress = _show_progress('Drawing parts', len(groups))
    try:
        for index, (info, quantity) in enumerate(groups):
            _advance_progress(progress, f'Drawing {info.name}', index)
            try:
                views = body_utils.extract_views(info)
                home = _home_view(info, home_frame)
                sheets.append((views, home, info, quantity))
            except Exception:
                failed.append((info.name, 'could not be drawn'))
                futil.log(
                    f'Export Cut Sheet: failed to draw {info.name}\n{traceback.format_exc()}',
                    adsk.core.LogLevels.ErrorLogLevel,
                )
    finally:
        _hide_progress(progress)

    if not sheets and overview is None:
        return 0, failed, set()

    date_text = datetime.date.today().isoformat()
    drawn_keys = {body_utils.identity_key(info) for _views, _home, info, _quantity in sheets}
    table = (
        csv_export.HEADER,
        list(csv_export.rows(infos, fmt, lambda info: _note_for(info, drawn_keys))),
    )
    parts = [
        drawing.PartSheet(
            views=views,
            body_name=info.name,
            component_name=info.component_name,
            document_name=doc_name,
            size=info.size,
            quantity=quantity,
            view_size=info.view_size,
            home=home,
        )
        for views, home, info, quantity in sheets
    ]
    try:
        document = drawing.build_document(parts, fmt, _settings['page'], date_text, overview, table)
        document.save(path)
    except Exception:
        failed.append(('PDF', _short_error()))
        futil.log(f'Export Cut Sheet: PDF failed\n{traceback.format_exc()}', adsk.core.LogLevels.ErrorLogLevel)
        return 0, failed, set()
    return len(document.pages), failed, drawn_keys


def _note_for(info, drawn_keys):
    """Same note the CSV uses: the drawing when this body has a page, otherwise the design."""
    if body_utils.identity_key(info) in drawn_keys:
        return csv_export.NOTE_SEE_PDF
    return csv_export.NOTE_SEE_DESIGN


def _sync_number_inputs(inputs):
    """Fractions only apply to inches and feet; decimals apply otherwise."""
    imperial = _selected_name(inputs, INPUT_UNITS) in drawing.IMPERIAL_UNITS
    fractions = inputs.itemById(INPUT_FRACTIONS)
    precision = inputs.itemById(INPUT_FRACTION_PRECISION)
    decimals = inputs.itemById(INPUT_DECIMALS)
    fractions.isVisible = imperial
    precision.isVisible = imperial
    precision.isEnabled = fractions.value
    if decimals:
        decimals.isEnabled = not (imperial and fractions.value)


def _fraction_label(denominator):
    return f'1/{denominator}'


def _denominator_from_label(label):
    try:
        return int(label.split('/')[1])
    except (IndexError, ValueError):
        return 16


def _design_units(design):
    try:
        unit = design.unitsManager.defaultLengthUnits
    except Exception:
        unit = ''
    return unit if unit in body_utils.UNIT_CHOICES else 'mm'


def _document_name(design):
    try:
        return design.parentDocument.name or 'Untitled'
    except Exception:
        return 'Untitled'


def _safe_filename(name):
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .')
    return cleaned or 'Untitled'


def _ask_folder():
    dialog = ui.createFolderDialog()
    dialog.title = 'Choose a folder for the cut sheet'
    downloads = _downloads_folder()
    if downloads and os.path.isdir(downloads):
        try:
            dialog.initialDirectory = downloads
        except Exception:
            futil.log(
                f'Export Cut Sheet: could not open in Downloads\n{traceback.format_exc()}',
                adsk.core.LogLevels.WarningLogLevel,
            )
    if dialog.showDialog() != adsk.core.DialogResults.DialogOK:
        return None
    return dialog.folder


def _downloads_folder():
    """The current user's Downloads folder, including a relocated Windows folder."""
    if sys.platform == 'win32':
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [
                    ('Data1', wintypes.DWORD),
                    ('Data2', wintypes.WORD),
                    ('Data3', wintypes.WORD),
                    ('Data4', ctypes.c_ubyte * 8),
                ]

            folder_id = GUID(
                0x374DE290,
                0x123F,
                0x4565,
                (ctypes.c_ubyte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B),
            )
            path_ptr = ctypes.c_wchar_p()
            shell32 = ctypes.WinDLL('shell32', use_last_error=True)
            shell32.SHGetKnownFolderPath.argtypes = [
                ctypes.POINTER(GUID),
                wintypes.DWORD,
                wintypes.HANDLE,
                ctypes.POINTER(ctypes.c_wchar_p),
            ]
            shell32.SHGetKnownFolderPath.restype = ctypes.c_long
            if shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(path_ptr)) == 0:
                folder = path_ptr.value
                ctypes.WinDLL('ole32').CoTaskMemFree(path_ptr)
                if folder:
                    return os.path.normpath(folder)
        except Exception:
            futil.log(
                f'Export Cut Sheet: could not resolve Downloads\n{traceback.format_exc()}',
                adsk.core.LogLevels.WarningLogLevel,
            )
    return os.path.normpath(os.path.join(os.path.expanduser('~'), 'Downloads'))


def _open_folder(folder):
    try:
        if sys.platform.startswith('win'):
            os.startfile(folder)
        else:
            subprocess.Popen(['open', folder])
    except Exception:
        futil.log(f'Export Cut Sheet: could not open {folder}', adsk.core.LogLevels.WarningLogLevel)


def _selected_name(inputs, input_id):
    dropdown = adsk.core.DropDownCommandInput.cast(inputs.itemById(input_id))
    item = dropdown.selectedItem
    return item.name if item else ''


def _short_error():
    detail = str(sys.exc_info()[1]).strip() or 'unknown error'
    return detail if len(detail) <= 180 else detail[:177] + '...'


def _show_progress(title, maximum):
    try:
        progress = ui.progressBar
        progress.show(title, 0, max(maximum, 1), False)
        return progress
    except Exception:
        return None


def _advance_progress(progress, message, value):
    if not progress:
        return
    try:
        progress.message = message
        progress.progressValue = value
        adsk.doEvents()
    except Exception:
        pass


def _hide_progress(progress):
    if not progress:
        return
    try:
        progress.hide()
    except Exception:
        pass


def _toolbar_tab():
    workspace = ui.workspaces.itemById(config.WORKSPACE_ID)
    if workspace:
        tab = workspace.toolbarTabs.itemById(config.RIBBON_TAB_ID)
        if tab:
            return tab
    all_tabs = getattr(ui, 'allToolbarTabs', None)
    if all_tabs:
        return all_tabs.itemById(config.RIBBON_TAB_ID)
    return None


def _place_on_tab(cmd_def):
    tab = _toolbar_tab()
    if not tab:
        return False
    panel = tab.toolbarPanels.itemById(config.RIBBON_PANEL_ID)
    if not panel:
        try:
            panel = tab.toolbarPanels.add(
                config.RIBBON_PANEL_ID, config.RIBBON_PANEL_NAME, config.RIBBON_AFTER_PANEL_ID, False
            )
        except Exception:
            panel = tab.toolbarPanels.add(config.RIBBON_PANEL_ID, config.RIBBON_PANEL_NAME, '', False)
    if panel.controls.itemById(CMD_ID):
        return True
    control = panel.controls.addCommand(cmd_def)
    for attribute in ('isPromoted', 'isPromotedByDefault'):
        try:
            setattr(control, attribute, IS_PROMOTED)
        except Exception:
            pass
    return True


def _remove_from_tab():
    tab = _toolbar_tab()
    if not tab:
        return
    panel = tab.toolbarPanels.itemById(config.RIBBON_PANEL_ID)
    if not panel:
        return
    control = panel.controls.itemById(CMD_ID)
    if control:
        control.deleteMe()
    if panel.controls.count == 0:
        panel.deleteMe()
