from .PrintedAppearance import entry as cmd1
commands = [cmd1]

def start():
    for command in commands:
        command.start()

def stop():
    for command in commands:
        command.stop()