# Commands registered by the Threader add-in.

from .threader import entry as threader

commands = [
    threader,
]


def start():
    for command in commands:
        command.start()


def stop():
    for command in commands:
        command.stop()
