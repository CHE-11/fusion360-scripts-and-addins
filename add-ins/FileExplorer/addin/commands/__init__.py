# Commands registered by the File Explorer add-in.

from .explorer import entry as explorer

commands = [
    explorer,
]


def start():
    for command in commands:
        command.start()


def stop():
    for command in commands:
        command.stop()
