"""Build an authored scene ABI library and exercise production retained placement on a real GPU."""
import argparse,hashlib,json,os,re,shutil,signal,subprocess,sys,time
from pathlib import Path

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,value): p.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

FIXTURES = {
    'retained': ('retained_base_frame_library.cpp', 'retained_base_test.gd', 'retained-base-result.json', 'authored_retained_base'),
    'big_raw': ('big_raw_frame_library.cpp', 'big_raw_test.gd', 'big-raw-result.json', 'authored_big_raw'),
    'retained_shadow': ('shadow_receiver_frame_library.cpp', 'shadow_receiver_test.gd', 'shadow-receiver-result.json', 'authored_retained_shadow'),
}
BIG_RAW_PHASES = ('seed', 'same_count_move_recolour', 'grow', 'shrink_reuse', 'zero', 'flat', 'raw_threshold_return', 'raw_stress')
SHADOW_PHASES = ('seed_far', 'left_shadow', 'left_unshadowed', 'left_shadow_restored', 'right_shadow', 'right_repeat', 'outside', 'return_left')
OWNED_FIXTURES = ('big_raw', 'retained_shadow')
ERROR_PATTERN = r'ERROR:|SCRIPT ERROR|Parse Error|SHADER ERROR|leaked at exit|still in use at exit'

def run_big_owned(command, env, deadline, log):
    """Own only this authored fixture/import process and stop its tree on failure."""
    receipt = {'exit': None, 'timeout': False, 'pid': None, 'cleanup': None, 'error': None, 'log': str(log)}
    process = None
    def stop_owned():
        cleanup = {'pid': process.pid, 'error': None}
        receipt['cleanup'] = cleanup
        try:
            if sys.platform == 'win32':
                command = ['taskkill', '/PID', str(process.pid), '/T', '/F']
                killed = subprocess.run(command, capture_output=True, text=True, timeout=15)
                cleanup.update(command=command, exit=killed.returncode, stdout=killed.stdout, stderr=killed.stderr)
            else:
                os.killpg(process.pid, signal.SIGKILL)
                cleanup['signal'] = 'SIGKILL'
        except Exception as error:
            cleanup['error'] = type(error).__name__ + ': ' + str(error)
        try:
            receipt['exit'] = process.wait(timeout=15)
        except Exception as error:
            cleanup['wait_error'] = type(error).__name__ + ': ' + str(error)
            cleanup['wait_timeout'] = isinstance(error, subprocess.TimeoutExpired)
            try:
                process.kill()
                receipt['exit'] = process.wait(timeout=15)
            except Exception as error:
                cleanup['final_wait_error'] = type(error).__name__ + ': ' + str(error)
        try:
            cleanup['reaped'] = process.poll() is not None
        except Exception as error:
            cleanup['reaped'] = False
            cleanup['poll_error'] = type(error).__name__ + ': ' + str(error)
    try:
        options = {'creationflags': subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == 'win32' else {'start_new_session': True}
        with log.open('xb') as stream:
            process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT, env=env, **options)
            receipt['pid'] = process.pid
            try:
                receipt['exit'] = process.wait(timeout=deadline)
            except subprocess.TimeoutExpired:
                receipt['timeout'] = True
                stop_owned()
            except Exception as error:
                receipt['error'] = type(error).__name__ + ': ' + str(error)
                stop_owned()
    except Exception as error:
        receipt['error'] = type(error).__name__ + ': ' + str(error)
        if process is not None:
            try:
                running = process.poll() is None
            except Exception as poll_error:
                receipt['poll_error'] = type(poll_error).__name__ + ': ' + str(poll_error)
                running = True
            if running:
                stop_owned()
    return receipt

def big_execution_ok(receipt):
    return type(receipt.get('exit')) is int and receipt['exit'] == 0 and not receipt['timeout'] and receipt['error'] is None and receipt['cleanup'] is None

def big_raw_captures(out, report):
    """Require all eight admitted GPU phases and pin their full PNG/RGBA outputs."""
    rows = report.get('cases', []) if isinstance(report, dict) else []
    valid = tuple(row.get('phase') for row in rows) == BIG_RAW_PHASES and all(row.get('passed') is True and row.get('big_path_delta_matches') is True for row in rows)
    captures = {}
    for phase in BIG_RAW_PHASES:
        for suffix in ('.png', '.rgba'):
            path = out / (phase + suffix)
            if not path.is_file():
                valid = False
                continue
            data = path.read_bytes()
            captures[path.name] = sha(path)
            if suffix == '.rgba':
                valid = valid and len(data) == 128 * 128 * 4
            else:
                valid = valid and data[:8] == b'\x89PNG\r\n\x1a\n' and data[12:16] == b'IHDR' and data[16:24] == (128).to_bytes(4, 'big') * 2
    return valid and len(captures) == 16, captures


def retained_shadow_captures(out, report):
    """Require the complete shadow oracle and pin all eight saved image pairs."""
    captures = {}
    if not isinstance(report, dict) or report.get('passed') is not True:
        return False, captures
    rows = report.get('cases')
    if not isinstance(rows, list) or len(rows) != len(SHADOW_PHASES) or not all(isinstance(row, dict) for row in rows):
        return False, captures
    valid = tuple(row.get('phase') for row in rows) == SHADOW_PHASES
    valid = valid and all(report.get(key) is True for key in ('stationary_full_rgba_equal', 'return_full_rgba_equal', 'outside_full_rgba_equal'))
    flags = ('passed', 'base_pixels_valid', 'camera_valid', 'retained_path_valid', 'same_scenario', 'shadow_roi_valid', 'shadow_mask_valid')
    for phase, row in zip(SHADOW_PHASES, rows):
        valid = valid and all(row.get(key) is True for key in flags)
        valid = valid and type(row.get('capture_exit')) is int and row['capture_exit'] == 0 and row.get('raw_rgba_saved') is True
        for suffix in ('.png', '.rgba'):
            path = out / (phase + suffix)
            if not path.is_file():
                valid = False
                continue
            data = path.read_bytes()
            captures[path.name] = sha(path)
            if suffix == '.rgba':
                valid = valid and len(data) == 128 * 128 * 4 and captures[path.name] == row.get('rgba_sha256')
            else:
                valid = valid and data[:8] == b'\x89PNG\r\n\x1a\n' and data[12:16] == b'IHDR' and data[16:24] == (128).to_bytes(4, 'big') * 2
    for group in (('right_shadow', 'right_repeat'), ('left_shadow', 'left_shadow_restored', 'return_left'), ('seed_far', 'outside')):
        valid = valid and len({captures.get(phase + '.rgba') for phase in group}) == 1
    return valid and len(captures) == 16, captures


def execute(out):
    spec=json.loads((out/'run-result.json').read_text(encoding='utf-8-sig'))
    if (out/'runtime.log').exists(): raise ValueError('This case already ran; preserve it and prepare a fresh output.')
    fixture = spec.get('fixture', 'retained')
    if fixture not in FIXTURES: raise ValueError('Unknown prepared fixture')
    if fixture in OWNED_FIXTURES and (out/'import.log').exists(): raise ValueError('This authored case already started; preserve it and prepare a fresh output.')
    for name,value in spec['pinned_sha256'].items():
        if sha(Path(name))!=value: raise ValueError('Prepared input changed: '+name)
    env=dict(os.environ)
    for key,name in [('TEMP','temp'),('TMP','temp'),('APPDATA','appdata'),('LOCALAPPDATA','localappdata'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache')]:
        path=out/name;path.mkdir(exist_ok=True);env[key]=str(path)
    began=time.monotonic()
    if fixture in OWNED_FIXTURES:
        spec['import_execution'] = run_big_owned(spec['import_command'], env, 60, out/'import.log')
        import_text = (out/'import.log').read_text(encoding='utf-8-sig', errors='replace') if (out/'import.log').exists() else ''
        spec['import_errors'] = [line for line in import_text.splitlines() if re.search(ERROR_PATTERN, line, re.I)]
        if not big_execution_ok(spec['import_execution']) or spec['import_errors']:
            spec['passed'] = False
            save(out/'run-result.json', spec)
            return 1
        spec['gpu_execution'] = run_big_owned(spec['command'], env, 75, out/'runtime.log')
        spec.update(exit=spec['gpu_execution']['exit'], timeout=spec['gpu_execution']['timeout'])
    else:
        with (out/'runtime.log').open('wb') as log:
            try:
                result=subprocess.run(spec['command'],stdout=log,stderr=subprocess.STDOUT,env=env,timeout=60,
                    **({'creationflags':subprocess.CREATE_NO_WINDOW}if sys.platform=='win32'else{}))
                spec.update(exit=result.returncode,timeout=False)
            except subprocess.TimeoutExpired:
                spec.update(exit=None,timeout=True)
    spec['elapsed_seconds']=time.monotonic()-began
    capture_out = out/'captures' if fixture == 'retained_shadow' else out
    report=capture_out/FIXTURES[fixture][2]
    spec['gpu_report']=json.loads(report.read_text())if report.exists()else None
    text=(out/'runtime.log').read_text(encoding='utf-8-sig',errors='replace')
    spec['runtime_errors']=[line for line in text.splitlines()if re.search(r'ERROR:|SCRIPT ERROR|Parse Error|SHADER ERROR|leaked at exit|still in use at exit',line,re.I)]
    spec['inputs_stable']=all(sha(Path(name))==value for name,value in spec['pinned_sha256'].items())
    spec['passed']=spec.get('exit')==0 and not spec['timeout'] and bool(spec['gpu_report'])and spec['gpu_report']['passed']and not spec['runtime_errors']and spec['inputs_stable']
    if fixture == 'big_raw':
        spec['captures_valid'], spec['capture_sha256'] = big_raw_captures(out, spec['gpu_report'])
        spec['passed'] = spec['passed'] and big_execution_ok(spec['gpu_execution']) and spec['captures_valid']
    if fixture == 'retained_shadow':
        spec['captures_valid'], spec['capture_sha256'] = retained_shadow_captures(capture_out, spec['gpu_report'])
        spec['passed'] = spec['passed'] and big_execution_ok(spec['gpu_execution']) and spec['captures_valid'] and spec['gpu_report'].get('driver') == spec['driver']
    save(out/'run-result.json',spec)
    print(json.dumps({'passed':spec['passed'],'exit':spec.get('exit'),'timeout':spec['timeout'],'runtime_errors':spec['runtime_errors'],'inputs_stable':spec['inputs_stable'],'result':str(out/'run-result.json')},indent=2))
    return 0 if spec['passed']else 1

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot',type=Path);parser.add_argument('--project',type=Path);parser.add_argument('--cxx')
    parser.add_argument('--out',type=Path);parser.add_argument('--driver',choices=['vulkan','opengl3','d3d12'],default='vulkan')
    parser.add_argument('--prepare-only',action='store_true');parser.add_argument('--run-prepared',type=Path)
    parser.add_argument('--fixture', choices=tuple(FIXTURES), default='retained')
    args=parser.parse_args()
    if args.run_prepared:
        try:return execute(args.run_prepared.resolve())
        except (ValueError,OSError)as error:parser.error(str(error))
    if not all([args.godot,args.project,args.cxx,args.out]):parser.error('--godot,--project,--cxx and--out are required to prepare.')
    here=Path(__file__).resolve().parent;repo=here.parents[2];out=args.out.resolve();project=args.project.resolve()
    if out.is_relative_to(repo)and not out.is_relative_to(repo/'local'):parser.error('Generated files must stay outside tracked repository paths.')
    if any(project.glob('librta_game*'))or any((project/'bin').glob('librta_game*')):parser.error('Use a fresh authored project stage without a game library.')
    out.mkdir(parents=True,exist_ok=False)
    cpp, gd, report, library_name = FIXTURES[args.fixture]
    library=out/(library_name+('.dll'if sys.platform=='win32'else'.so'))
    compile_command=[args.cxx,'-std=c++17','-O2','-shared','-I',str(here.parent/'lib'),str(here/cpp),'-o',str(library)]
    compile_command+=['-static','-Wl,--export-all-symbols']if sys.platform=='win32'else['-fPIC']
    build=subprocess.run(compile_command,capture_output=True,text=True,timeout=60)
    (out/'compile.log').write_text(build.stdout+build.stderr,encoding='utf-8')
    if build.returncode:
        save(out/'run-result.json',{'passed':False,'compile_exit':build.returncode,'compile_command':compile_command});print(build.stderr);return build.returncode
    source=here/gd if args.fixture == 'retained_shadow' else here.parent/'project/dev'/gd
    staged=project/'dev'/gd;staged.parent.mkdir(exist_ok=True)
    if not staged.exists()or staged.read_bytes()!=source.read_bytes():shutil.copyfile(source,staged)
    capture_out = out/'captures' if args.fixture == 'retained_shadow' else out
    if args.fixture == 'retained_shadow': capture_out.mkdir()
    command=[str(args.godot.resolve()),'--path',str(project),'--rendering-method','gl_compatibility'if args.driver=='opengl3'else'forward_plus','--rendering-driver',args.driver,'--script','res://dev/'+gd,'--','--lib',str(library),'--out',str(capture_out)]
    if sys.platform=='win32':command[1:1]=['--display-driver','windows','--position','40,60','--resolution','160x160']
    pins=[args.godot.resolve(),library,staged,Path(__file__).resolve(),here/cpp,here.parent/'lib/rtag.h',project/'project.godot',project/'rta_godot.gdextension',project/'shaders/gs_draw.gdshaderinc']
    if args.fixture == 'retained_shadow': pins.append(source)
    engine=args.godot.with_name(args.godot.name.replace('_console',''))
    if engine.is_file() and engine.resolve()!=args.godot.resolve():pins.append(engine.resolve())
    if args.fixture in OWNED_FIXTURES:
        for name in ('gs_draw.gdshaderinc', 'atmosphere.gdshaderinc', 'er_world.gdshaderinc'):
            original = here.parent/'project/shaders'/name
            target = project/'shaders'/name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.read_bytes() != original.read_bytes(): shutil.copyfile(original, target)
            pins.extend((original, target))
    pins+=sorted((project/'bin').glob('rta_godot.*'))
    save(out/'run-result.json',{'prepared':True,'compile_exit':0,'compile_command':compile_command,'command':command,'driver':args.driver,
        'scope':'Authored ABI frames through production scene/kept/flat pools; no game library,disc,assets or translation.','pinned_sha256':{str(p):sha(p)for p in pins}})
    if args.fixture in OWNED_FIXTURES:
        spec=json.loads((out/'run-result.json').read_text())
        scope = 'Authored eight-phase production BIG raw GPU regression; no game data or performance claim.' if args.fixture == 'big_raw' else 'Authored eight-phase production retained shadow-caster/receiver regression; no game data or performance claim.'
        spec.update(fixture=args.fixture, scope=scope, readback_limit='Production readback is RGB8 converted to stored RGBA8; alpha is synthesized opaque255, not original scene alpha.', import_command=[str(args.godot.resolve()), '--headless', '--path', str(project), '--editor', '--quit-after', '120', '--frame-delay', '50'])
        save(out/'run-result.json', spec)
    if args.prepare_only:
        print(json.dumps({'prepared':str(out),'launched':False,'command':command},indent=2));return 0
    return execute(out)

if __name__=='__main__':raise SystemExit(main())
