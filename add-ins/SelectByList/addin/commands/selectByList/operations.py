"""Run Fusion's Move, Mirror, and pattern commands on items from the palette.

Native commands cannot start while Fusion is still inside the palette's HTML
event, so the request is queued and run from a custom event right after.
"""

import json
import traceback

import adsk.core

from ... import config
from ...lib import fusionAddInUtils as futil
from . import design as d

app = adsk.core.Application.get()
ui = app.userInterface

CUSTOM_EVENT_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_runCommand'

COMMANDS = {
    'move': ('FusionMoveCommand',),
    'mirror': ('FusionMirrorCommand', 'MirrorCommand'),
    'circPattern': ('FusionCircularPatternCommand', 'FusionPatternCircularCommand', 'CircularPatternCommand'),
    'rectPattern': ('FusionRectangularPatternCommand', 'FusionPatternRectangularCommand', 'RectangularPatternCommand'),
}

LABELS = {
    'move': 'Move',
    'mirror': 'Mirror',
    'circPattern': 'Circular Pattern',
    'rectPattern': 'Rectangular Pattern',
}

_custom_event = None
_handlers = []
_pending = None
_last = None


def start():
    global _custom_event
    try:
        app.unregisterCustomEvent(CUSTOM_EVENT_ID)
    except Exception:
        pass
    _custom_event = app.registerCustomEvent(CUSTOM_EVENT_ID)
    futil.add_handler(_custom_event, _on_run_command, local_handlers=_handlers)
    for op in COMMANDS:
        if not _command_id(op):
            futil.log(f'Select By List: no Fusion command found for {op}; tried {", ".join(COMMANDS[op])}')


def stop():
    global _custom_event, _pending
    _pending = None
    _handlers.clear()
    try:
        app.unregisterCustomEvent(CUSTOM_EVENT_ID)
    except Exception:
        pass
    _custom_event = None


def last_op():
    if not _last:
        return None
    return {'op': _last['op'], 'label': LABELS[_last['op']], 'count': len(_last['tokens'])}


def _command_id(op):
    for command_id in COMMANDS.get(op, ()):
        if ui.commandDefinitions.itemById(command_id):
            return command_id
    return ''


def run(payload, repeat=False):
    global _pending, _last
    op = str(payload.get('op') or '')
    if op not in COMMANDS:
        raise ValueError(f'Unknown operation: {op}')
    label = LABELS[op]
    tokens = [token for token in (payload.get('tokens') or []) if isinstance(token, str)]

    design = d.require_design()
    entities, missing = d.resolve_many(tokens, design)
    occurrences, bodies, faces = d.split_entities(entities)
    if faces:
        raise ValueError(f'{label} works on components and bodies, not faces. Switch the list back to Component or Body.')
    if not occurrences and not bodies:
        if repeat and tokens:
            raise ValueError('The items from the last operation no longer exist.')
        raise ValueError(f'Check at least one component or body to {label.lower()}.')
    if op != 'move' and occurrences and bodies:
        raise ValueError(f'{label} needs all components or all bodies. Do not mix types in one operation.')

    command_id = _command_id(op)
    if not command_id:
        raise ValueError(f"Fusion's {label} command was not found in this version.")

    # Only the targets are preselected so Move centres its gizmo on them.
    targets = occurrences + bodies
    resolved_tokens = [entity.entityToken for entity in targets]
    _pending = {'commandId': command_id, 'tokens': resolved_tokens}
    _last = {'op': op, 'tokens': resolved_tokens}
    app.fireCustomEvent(CUSTOM_EVENT_ID, json.dumps({'op': op}))
    return {
        'op': op,
        'label': label,
        'count': len(targets),
        'missing': missing,
        'lastOp': last_op(),
    }


def repeat_last():
    if not _last:
        raise ValueError('Run Move, Mirror, or a pattern first.')
    return run({'op': _last['op'], 'tokens': list(_last['tokens'])}, repeat=True)


def _on_run_command(args):
    global _pending
    pending, _pending = _pending, None
    if not pending:
        return
    try:
        design = d.active_design()
        selections = ui.activeSelections
        selections.clear()
        for token in pending['tokens']:
            entity = d.resolve(token, design)
            if entity is not None:
                selections.add(entity)
        command_definition = ui.commandDefinitions.itemById(pending['commandId'])
        if command_definition:
            command_definition.execute()
    except Exception:
        futil.log(f"Select By List: could not start {pending.get('commandId')}: {traceback.format_exc()}")
