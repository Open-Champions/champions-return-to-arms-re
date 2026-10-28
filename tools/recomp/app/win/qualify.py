#!/usr/bin/env python3
"""Repeatable Windows native checks using the player's own US v2.00 disc.

python tools/recomp/app/win/qualify.py --disc IMAGE [--package DIR] [--out DIR]
Original data, logs, cards and screenshots remain in private output. This checks
software input routes, not physical switches, audible quality or a full campaign.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tools' / 'recomp'))
from disc import Iso  # noqa: E402

ELF_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
CPU_CHECKSUM = '2e77df4dc13ec9c5'
PNG_CHECKSUM = 'b4ed3d8917871960'
PACKAGE = ROOT / 'local' / 'recomp-out' / 'win' / 'rta-windows'
PAD = re.compile(r'holds buttons ([0-9a-f]+), sticks (\d+) (\d+) (\d+) (\d+); keyboard bits ([0-9a-f]+)')


def check_elf_bytes(data):
    actual = hashlib.sha256(data).hexdigest()
    if actual != ELF_SHA256:
        raise ValueError('Unsupported executable SHA-256: ' + actual)
    return actual


def check_disc(path, copy_to=None):
    image = Iso(str(path))
    try:
        entry = image.find('SLUS_209.73')
        if entry is None:
            raise ValueError('The disc has no SLUS_209.73')
        image.f.seek(entry['lba'] * 2048)
        data = image.f.read(entry['size'])
        if len(data) != entry['size']:
            raise ValueError('The disc executable is truncated')
        identity = {'elf_sha256': check_elf_bytes(data), 'elf_bytes': len(data)}
        if copy_to is not None:
            Path(copy_to).write_bytes(data)
        return identity
    finally:
        image.f.close()


def private_output(path):
    path = path.resolve()
    root = ROOT.resolve()
    # Judge the destination after following links. local/ may point outside the
    # checkout, but a link back into a tracked directory must still be rejected.
    if path.is_relative_to(root) and not path.is_relative_to(root / 'local'):
        raise ValueError('Game-derived output must be outside the checkout or under local/')
    return path


def failures(text):
    found = []
    for line in text.splitlines():
        if re.search(r'TIMEOUT|unresolved function|access violation|fatal error', line, re.I):
            found.append(line)
        for label in ('VU1 instructions not implemented', 'GS registers unknown'):
            match = re.search(re.escape(label) + r' (\d+)', line)
            if match and int(match[1]):
                found.append(line)
    return found


def boot_result(text):
    frames = re.search(r'frames=(\d+).*?fields=(\d+) units=(\d+)', text, re.S)
    vu0 = re.search(r'VU0: (\d+) microprogram calls, (\d+) instructions', text)
    values = tuple(map(int, frames.groups())) if frames else None
    vector = tuple(map(int, vu0.groups())) if vu0 else None
    return {'passed': '=hub' in text and values == (2309, 2413, 113069252)
            and vector == (466083, 26111361) and not failures(text),
            'frames_fields_units': values, 'vu0_calls_instructions': vector,
            'reference': 'US v2.00,189-word fix set,documented Windows/Mac boot receipt'}


def input_cases():
    cases = []
    for key, axes in [('w', (128, 0)), ('s', (128, 255)), ('a', (0, 128)), ('d', (255, 128))]:
        cases.append(('key_' + key, ['app key down ' + key], ['app key up ' + key], 0, (*axes, 128, 128)))
    for key, mask in [('up', 0x10), ('right', 0x20), ('down', 0x40), ('left', 0x80),
                      ('i', 0x1000), ('j', 0x8000), ('k', 0x4000), ('l', 0x2000),
                      ('q', 0x400), ('e', 0x800), ('1', 0x100), ('3', 0x200),
                      ('x', 2), ('c', 4), ('return', 8), ('backspace', 1),
                      ('space', 0x8000), ('shift', 0x800), ('tab', 4),
                      ('numpad1', 0x100), ('numpad3', 0x200)]:
        cases.append(('key_' + key, ['app key down ' + key], ['app key up ' + key], mask, (128,) * 4))
    for a, b, mask in [('e', 'shift', 0x800), ('j', 'space', 0x8000), ('c', 'tab', 4),
                       ('1', 'numpad1', 0x100), ('3', 'numpad3', 0x200)]:
        for first, last in [(a, b), (b, a)]:
            cases.append(('overlap_' + first + '_' + last,
                          ['app key down ' + first, 'app key down ' + last,
                           'wait 3', 'app key up ' + first], ['app key up ' + last], mask, (128,) * 4))
    for button, mask in [('up', 0x10), ('right', 0x20), ('down', 0x40), ('left', 0x80),
                         ('triangle', 0x1000), ('square', 0x8000), ('cross', 0x4000),
                         ('circle', 0x2000), ('l1', 0x400), ('r1', 0x800), ('l2', 0x100),
                         ('r2', 0x200), ('l3', 2), ('r3', 4), ('start', 8), ('select', 1)]:
        cases.append(('pad_' + button, ['app gcpad set ' + button + ' 0 0 0 0 0 0'], ['app gcpad none'], mask, (128,) * 4))
    for axis in range(4):
        for sign in (-1, 1):
            values = [0] * 6
            values[axis] = sign
            expected = [128] * 4
            expected[axis] = (255 if sign > 0 else 0) if axis % 2 == 0 else (0 if sign > 0 else 255)
            cases.append(('axis_%d_%d' % (axis, sign),
                          ['app gcpad set none ' + ' '.join(map(str, values))], ['app gcpad none'], 0, tuple(expected)))
    cases += [('deadzone', ['app gcpad set none 0.14 0 0 0 0.29 0.29'], ['app gcpad none'], 0, (128,) * 4),
              ('trigger_76', ['app gcpad set none 0 0 0 0 0.2980392156862745 0.2980392156862745'], ['app gcpad none'], 0, (128,) * 4),
              ('trigger_77', ['app gcpad set none 0 0 0 0 0.3019607843137255 0.3019607843137255'], ['app gcpad none'], 0x300, (128,) * 4)]
    return cases


def input_script(boot):
    lines = [boot, 'app view overhead', 'app gcpad connect', 'wait 3']
    for name, pressed, released, _mask, _axes in input_cases():
        lines += ['echo QA_CASE ' + name] + pressed + ['wait 6', 'app pads'] + released + ['wait 6', 'app pads']
    lines += ['app gcpad disconnect', 'wait 3', 'echo QA_INPUT_COMPLETE', 'quit']
    return '\n'.join(lines) + '\n'


def input_result(text):
    results = []
    for name, _press, _release, mask, axes in input_cases():
        marker = 'QA_CASE ' + name + '\n'
        section = text.split(marker, 1)[1].split('QA_CASE ', 1)[0] if marker in text else ''
        states = PAD.findall(section)
        ok = False
        if len(states) >= 2:
            held, released = states[:2]
            ok = int(held[0], 16) == mask and tuple(map(int, held[1:5])) == axes
            ok = ok and int(released[0], 16) == 0 and tuple(map(int, released[1:5])) == (128,) * 4
        results.append({'case': name, 'passed': ok})
    return {'passed': all(r['passed'] for r in results) and 'QA_INPUT_COMPLETE' in text and not failures(text),
            'cases': results, 'method': 'Compiled Windows message handler and game controller test adapter; physical device actuation untested'}


def run(command, log, timeout=120):
    with log.open('wb') as stream:
        try:
            process = subprocess.run(list(map(str, command)), stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError('Timed out; private log: ' + str(log)) from error
    return process.returncode, log.read_text(encoding='utf-8-sig', errors='replace')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disc', required=True, type=Path)
    parser.add_argument('--package', type=Path, default=PACKAGE)
    parser.add_argument('--out', type=Path, default=ROOT / 'local' / 'pc-qualification')
    parser.add_argument('--skip-inputs', action='store_true', help='Only arithmetic,PNG and boot checks')
    args = parser.parse_args()
    identity = check_disc(args.disc)
    required = ['fpcheck.exe', 'pnghash.exe', 'rta_native.exe', 'rta_app.exe', 'boot-check.rig']
    for name in required:
        if not (args.package / name).is_file():
            parser.error('Missing built package file: ' + name)
    artifacts = {name: hashlib.sha256((args.package / name).read_bytes()).hexdigest() for name in required}
    out = private_output(args.out) / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
    out.mkdir(parents=True)
    private_elf = out / 'SLUS_209.73'
    check_disc(args.disc, private_elf)
    checks = {}
    code, text = run([args.package / 'fpcheck.exe'], out / 'arithmetic.log')
    checks['arithmetic'] = {'passed': code == 0 and re.search(r'must agree everywhere[^\n]*:\s*' + CPU_CHECKSUM, text) is not None
                            and 'rounding mode now toward zero' in text}
    code, text = run([args.package / 'pnghash.exe', args.package / 'pngtest'], out / 'png.log')
    checks['png'] = {'passed': code == 0 and PNG_CHECKSUM in text}
    code, text = run([args.package / 'rta_native.exe', 'boot', '--elf', private_elf, '--disc', args.disc, '--card', out / 'boot-card',
                      '--script', args.package / 'boot-check.rig', '--seconds', '120'], out / 'boot.log')
    checks['boot'] = boot_result(text)
    checks['boot']['passed'] = checks['boot']['passed'] and code == 0
    if not args.skip_inputs:
        script = out / 'inputs.rig'
        script.write_text(input_script((args.package / 'boot-check.rig').read_text()))
        code, text = run([args.package / 'rta_app.exe', '--disc', args.disc, '--data', out / 'input-data', '--script', script,
                          '--offscreen', '--unpaced', '--no-sound', '--no-settings', '--no-log', '--test', 'Input regression',
                          '--stop-after', '8000'], out / 'inputs.log')
        checks['inputs'] = input_result(text)
        checks['inputs']['passed'] = checks['inputs']['passed'] and code == 0
    checks['artifacts_stable'] = {'passed': all(hashlib.sha256((args.package / name).read_bytes()).hexdigest() == value
                                               for name, value in artifacts.items())}
    report = {'scope': 'Software arithmetic,decode,boot and input regression;not complete gameplay qualification',
              'input': identity, 'binary_sha256': artifacts['rta_app.exe'], 'artifact_sha256': artifacts,
              'passed': all(c['passed'] for c in checks.values()), 'checks': checks}
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'private_output': str(out),
                      'checks': {k: v['passed'] for k, v in checks.items()}}, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
