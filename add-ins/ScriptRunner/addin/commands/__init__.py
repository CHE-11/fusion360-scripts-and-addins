# Commands registered by the Script Runner add-in.

from .runner import entry as runner

commands = [
    runner,
]


def start():
    for command in commands:
        command.start()


def stop():
    for command in commands:
        command.stop()
