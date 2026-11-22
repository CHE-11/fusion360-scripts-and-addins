from .exportCutSheet import entry as export_cut_sheet

commands = [
    export_cut_sheet,
]


def start():
    for command in commands:
        command.start()


def stop():
    for command in commands:
        command.stop()
