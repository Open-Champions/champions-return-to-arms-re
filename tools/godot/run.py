#!/usr/bin/env python3
"""run.py - start Godot on the staged project (local/godot-spike/project), keeping everything it writes under local/.

  python3 tools/godot/run.py import                 # once, and after the project's files change: the bounded
                                                    # headless editor start that fills Godot's import cache
  python3 tools/godot/run.py -- --disc IMAGE        # the game in a Godot window (options: head of project/main.gd)
  python3 tools/godot/run.py --headless -- --script FILE --unpaced ...      # no window (picture mode only)
  python3 tools/godot/run.py --editor               # the editor on the project
  RTA_GODOT_OUT=local/NAME  the project staged by build.py with the same variable
  RTA_GODOT=/path/to/Godot  names another Godot 4.5.2 binary (default: the one under local/godot-spike/deps)

Godot's own directories (editor settings, user://, caches) are put under local/godot-spike/godot-home through
XDG_CONFIG_HOME / XDG_DATA_HOME / XDG_CACHE_HOME, which Godot honours on macOS too: nothing lands in ~/Library.
On Windows APPDATA and LOCALAPPDATA are isolated there as well.
On POSIX the process is started at nice 10 unless RTA_NICE says otherwise ("0": as the player's own).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.abspath(os.environ.get('RTA_GODOT_OUT', os.path.join(ROOT, 'local', 'godot-spike')))    # as build.py
PROJECT = os.path.join(OUT, 'project')


def default_godot():
    editor = os.path.join(ROOT, 'local', 'godot-spike', 'deps', 'godot-editor')
    if sys.platform == 'win32':
        return os.path.join(editor, 'Godot_v4.5.2-stable_win64.exe')
    return os.path.join(editor, 'Godot.app', 'Contents', 'MacOS', 'Godot')


GODOT = os.environ.get('RTA_GODOT', default_godot())


def environment():
    env = dict(os.environ)
    home = os.path.join(OUT, 'godot-home')
    directories = [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'), ('XDG_CACHE_HOME', 'cache')]
    if sys.platform == 'win32':
        directories += [('APPDATA', 'appdata'), ('LOCALAPPDATA', 'localappdata')]
    for key, name in directories:
        env[key] = os.path.join(home, name)
        os.makedirs(env[key], exist_ok=True)
    env['RTA_CWD'] = os.getcwd()            # Godot moves into the project's directory; main.gd moves back
    return env


def main():
    args = sys.argv[1:]
    if args and args[0] in ('-h', '--help'):
        print(__doc__)
        return 0
    if not os.path.exists(GODOT):
        print('no Godot at %s (docs/issues/native-godot.md, "From nothing")' % GODOT)
        return 1
    if not os.path.exists(os.path.join(PROJECT, 'project.godot')):
        print('no staged project: python3 tools/godot/build.py project')
        return 1
    nice = os.environ.get('RTA_NICE', '10')
    prefix = ['nice', '-n', nice] if sys.platform != 'win32' and nice != '0' else []
    if args and args[0] == 'import':
        # Godot 4.5.2 can crash when it shuts down after its first import (godotengine/godot#111645);
        # a bounded editor start avoids it (as open-champions-godot's CI does)
        command = prefix + [GODOT, '--headless', '--path', PROJECT, '--editor', '--quit-after', '120', '--frame-delay', '50']
    else:
        command = prefix + [GODOT, '--path', PROJECT] + args
    return subprocess.call(command, env=environment())


if __name__ == '__main__':
    sys.exit(main())
