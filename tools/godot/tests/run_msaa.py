"""Run production Godot target reuse against authored ABI frames, without game inputs.

python tools/godot/tests/run_msaa.py --cxx COMPILER --godot GODOT --project STAGED_PROJECT --out PRIVATE_NEW_DIRECTORY
Repeat with --samples 0 for the non-MSAA control, or --driver opengl3 for Compatibility.
An existing built production extension must be present in STAGED_PROJECT/bin.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx',required=True)
    parser.add_argument('--godot',required=True,type=Path)
    parser.add_argument('--project',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--driver',choices=['vulkan','opengl3','d3d12'],default='vulkan')
    parser.add_argument('--samples',type=int,choices=[0,4],default=4)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    repo = here.parents[2]
    out = args.out.resolve()
    if out.is_relative_to(repo) and not out.is_relative_to(repo/'local'):
        parser.error('Keep generated libraries/captures under ignored local/ or outside the repository.')
    out.mkdir(parents=True,exist_ok=False)
    env = dict(os.environ)
    for key,child in [('TEMP','temp'),('TMP','temp'),('APPDATA','appdata'),('LOCALAPPDATA','localappdata'),
                      ('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache')]:
        directory = out/child
        directory.mkdir(exist_ok=True)
        env[key] = str(directory)
    library = out/('authored_msaa.dll' if sys.platform=='win32' else 'authored_msaa.so')
    command = [args.cxx,'-std=c++17','-O2','-shared','-I',str(here.parent/'lib'),
               str(here/'msaa_frame_library.cpp'),'-o',str(library)]
    if sys.platform=='win32':
        command += ['-static','-Wl,--export-all-symbols']
    else:
        command += ['-fPIC']
    build = subprocess.run(command,capture_output=True,text=True,env=env,timeout=60)
    (out/'compile.log').write_text(build.stdout+build.stderr)
    report = {'compile_exit':build.returncode,'compile_command':command,
              'scope':'authored frame library only; no game library, disc or generated translation'}
    if build.returncode:
        (out/'run-result.json').write_text(json.dumps(report,indent=2)+'\n')
        print(build.stderr)
        return build.returncode
    project = args.project.resolve()
    fixture = here.parent/'project/dev/msaa_transition_test.gd'
    staged = project/'dev/msaa_transition_test.gd'
    staged.parent.mkdir(exist_ok=True)
    if not staged.exists() or staged.read_bytes()!=fixture.read_bytes():
        shutil.copyfile(fixture,staged)
    command = [str(args.godot.resolve()),'--path',str(project),'--rendering-method',
               'gl_compatibility' if args.driver=='opengl3' else 'forward_plus',
               '--rendering-driver',args.driver,'--script','res://dev/msaa_transition_test.gd',
               '--','--lib',str(library),'--out',str(out),'--samples',str(args.samples)]
    if sys.platform=='win32':
        command[1:1] = ['--display-driver','windows','--position','40,60']
    report['command'] = command
    report['library_sha256'] = hashlib.sha256(library.read_bytes()).hexdigest()
    report['fixture_sha256'] = hashlib.sha256(fixture.read_bytes()).hexdigest()
    report['extension_sha256'] = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (project/'bin').glob('rta_godot.*')}
    started = time.monotonic()
    with (out/'runtime.log').open('wb') as log:
        try:
            result = subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,env=env,timeout=60,
                                    **({'creationflags':subprocess.CREATE_NO_WINDOW} if sys.platform=='win32' else {}))
            report['exit'] = result.returncode
            report['timeout'] = False
        except subprocess.TimeoutExpired:
            report['exit'] = None
            report['timeout'] = True
    report['elapsed_seconds'] = time.monotonic()-started
    result_path = out/'msaa-transition-result.json'
    report['gpu_report'] = json.loads(result_path.read_text()) if result_path.exists() else None
    runtime = (out/'runtime.log').read_text(encoding='utf-8-sig',errors='replace')
    report['runtime_errors'] = [line for line in runtime.splitlines()
                                if re.search(r'SCRIPT ERROR|Parse Error|ERROR:|fatal error|access violation',line,re.I)]
    after = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (project/'bin').glob('rta_godot.*')}
    report['extension_stable'] = after == report['extension_sha256']
    report['passed'] = (report['exit']==0 and report['gpu_report'] is not None and report['gpu_report']['passed']
                        and not report['runtime_errors'] and report['extension_stable'])
    (out/'run-result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
