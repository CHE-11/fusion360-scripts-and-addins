from . import commands
from .lib import fusion360utils as futil


def run(context):
    try:
        commands.start()
    except:
        futil.handle_error('run')


def stop(context):
    try:
        commands.stop()
    except:
        futil.handle_error('stop')
    finally:
        # Drop handlers only after the custom event is unregistered.
        # Releasing them first frees the callback Fusion is still calling.
        futil.clear_handlers()
