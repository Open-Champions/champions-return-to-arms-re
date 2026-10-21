"""buildid.py - the build id a program says about itself (app/testerkit.h: the build line, bug and crash reports).

    "<commit>[+] <date> <time>"   e.g. "79dbdc1+ 2026-10-21 18:02"

The commit is the source's: `git rev-parse --short HEAD` of the checkout, "+" when its tracked files differ from
it; a source without git (a setup's copy, tools/install/setup/build_setups.py) has a file SOURCE_ID at its top
with the commit the setup was made from.  The time is the build's.  Nothing else (no names, no paths).
"""
import os
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def commit(root=ROOT):
    try:
        rev = subprocess.run(['git', '-C', root, 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True, timeout=10)
        if rev.returncode == 0 and rev.stdout.strip():
            dirty = subprocess.run(['git', '-C', root, 'diff', '--quiet', 'HEAD', '--'], capture_output=True, timeout=30).returncode != 0
            return rev.stdout.strip() + ('+' if dirty else '')
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        with open(os.path.join(root, 'SOURCE_ID')) as f:
            text = f.read().strip().split()[0]
            if text:
                return text
    except (OSError, IndexError):
        pass
    return 'unknown'


def build_id(root=ROOT):
    # a build inside a container (build_linux.py --docker) is given the id made outside, where git sees the checkout
    return os.environ.get('RTA_BUILD_ID') or commit(root) + ' ' + time.strftime('%Y-%m-%d %H:%M')


def define(root=ROOT):
    """The compiler's argument (a list element; no shell)."""
    return '-DRTA_BUILD_ID="%s"' % build_id(root)


if __name__ == '__main__':
    print(build_id())
