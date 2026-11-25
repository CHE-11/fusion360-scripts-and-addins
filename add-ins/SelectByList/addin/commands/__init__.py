# Commands registered by the Select By List add-in.

from .selectByList import entry as select_by_list

commands = [
    select_by_list,
]


def start():
    for command in commands:
        command.start()


def stop():
    for command in commands:
        command.stop()
