from .restart import entry as restart

commands = [
    restart,
]


def start():
    for command in commands:
        command.start()


def stop():
    for command in commands:
        command.stop()
