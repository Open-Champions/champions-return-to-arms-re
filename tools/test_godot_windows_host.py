"""Windows Godot launch/staging contracts; authored temporary files, no game or engine launch."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
import zipfile
from unittest.mock import patch


HERE = Path(__file__).parent / 'godot'


def load(name, source):
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    previous = sys.path[:]
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = previous
    return module


runner = load('godot_windows_runner', HERE / 'run.py')
builder = load('godot_windows_builder', HERE / 'build.py')


class GodotRunnerTests(unittest.TestCase):
    def test_windows_default_editor_uses_pinned_portable_binary(self):
        with patch.object(runner.sys, 'platform', 'win32'):
            expected = os.path.join(runner.ROOT, 'local', 'godot-spike', 'deps',
                                    'godot-editor', 'Godot_v4.5.2-stable_win64.exe')
            self.assertEqual(runner.default_godot(), expected)

    def test_macos_default_editor_is_preserved(self):
        with patch.object(runner.sys, 'platform', 'darwin'):
            self.assertTrue(runner.default_godot().endswith(
                os.path.join('Godot.app', 'Contents', 'MacOS', 'Godot')))

    def test_explicit_editor_override_is_preserved(self):
        with patch.dict(os.environ, {'RTA_GODOT': 'portable editor/another Godot.exe'}):
            selected = load('godot_explicit_editor', HERE / 'run.py')
            self.assertEqual(selected.GODOT, 'portable editor/another Godot.exe')

    def test_windows_private_environment_does_not_mutate_parent(self):
        with tempfile.TemporaryDirectory(prefix='godot-host-') as folder:
            inherited = {'APPDATA': 'original roaming', 'LOCALAPPDATA': 'original local'}
            with patch.object(runner, 'OUT', folder), patch.object(runner.sys, 'platform', 'win32'), \
                    patch.dict(os.environ, inherited):
                env = runner.environment()
                for key, name in [('APPDATA', 'appdata'), ('LOCALAPPDATA', 'localappdata'),
                                  ('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                                  ('XDG_CACHE_HOME', 'cache')]:
                    expected = Path(folder) / 'godot-home' / name
                    self.assertEqual(Path(env[key]), expected)
                    self.assertTrue(expected.is_dir())
                self.assertEqual(env['RTA_CWD'], os.getcwd())
                self.assertEqual(os.environ['APPDATA'], inherited['APPDATA'])
                self.assertEqual(os.environ['LOCALAPPDATA'], inherited['LOCALAPPDATA'])

    def test_posix_keeps_existing_windows_variables(self):
        with tempfile.TemporaryDirectory(prefix='godot-host-') as folder:
            with patch.object(runner, 'OUT', folder), patch.object(runner.sys, 'platform', 'linux'), \
                    patch.dict(os.environ, {'APPDATA': 'keep roaming', 'LOCALAPPDATA': 'keep local'}):
                env = runner.environment()
                self.assertEqual(env['APPDATA'], 'keep roaming')
                self.assertEqual(env['LOCALAPPDATA'], 'keep local')

    def launch(self, platform, args, nice=None):
        with tempfile.TemporaryDirectory(prefix='godot-host-') as folder:
            root = Path(folder)
            editor = root / 'editor with spaces.exe'
            editor.write_bytes(b'authored placeholder; never executed')
            project = root / 'project'
            project.mkdir()
            (project / 'project.godot').write_text('authored placeholder')
            env = dict(os.environ)
            if nice is None:
                env.pop('RTA_NICE', None)
            else:
                env['RTA_NICE'] = nice
            with patch.object(runner, 'GODOT', str(editor)), patch.object(runner, 'PROJECT', str(project)), \
                    patch.object(runner, 'OUT', folder), patch.object(runner.sys, 'platform', platform), \
                    patch.object(runner.sys, 'argv', ['run.py'] + args), \
                    patch.dict(os.environ, env, clear=True), \
                    patch.object(runner.subprocess, 'call', return_value=0) as child:
                self.assertEqual(runner.main(), 0)
                command = child.call_args.args[0]
                return command, str(editor), str(project)

    def test_windows_launch_never_uses_nice_and_preserves_arguments(self):
        args = ['--headless', '--', '--script', 'private file.rig']
        for nice in (None, '10', '0'):
            with self.subTest(nice=nice):
                command, editor, project = self.launch('win32', args, nice)
                self.assertEqual(command, [editor, '--path', project] + args)

    def test_windows_import_keeps_bounded_headless_command(self):
        command, editor, project = self.launch('win32', ['import'])
        self.assertEqual(command, [editor, '--headless', '--path', project,
                                   '--editor', '--quit-after', '120', '--frame-delay', '50'])

    def test_posix_priority_options_are_preserved(self):
        for nice, expected in [(None, ['nice', '-n', '10']), ('7', ['nice', '-n', '7']), ('0', [])]:
            with self.subTest(nice=nice):
                command, editor, project = self.launch('darwin', ['--editor'], nice)
                self.assertEqual(command, expected + [editor, '--path', project, '--editor'])

    def test_missing_editor_does_not_start_a_child(self):
        with tempfile.TemporaryDirectory(prefix='godot-host-') as folder:
            with patch.object(runner, 'GODOT', os.path.join(folder, 'missing.exe')), \
                    patch.object(runner.sys, 'argv', ['run.py']), \
                    patch.object(runner.subprocess, 'call') as child, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.main(), 1)
                child.assert_not_called()


class GodotWindowsStagingTests(unittest.TestCase):
    def setUp(self):
        self.private = tempfile.TemporaryDirectory(prefix='godot-stage-')
        self.addCleanup(self.private.cleanup)
        variant = patch.dict(os.environ, {'RTA_GODOT_PARTY8': '0'})
        variant.start()
        self.addCleanup(variant.stop)
        self.base = Path(self.private.name)
        self.source = self.base / 'authored-source'
        self.out = self.base / 'private-output'
        (self.source / 'project').mkdir(parents=True)
        (self.source / 'project/project.godot').write_text('authored test project')
        self.patches = [patch.object(builder, 'HERE', str(self.source)),
                        patch.object(builder, 'OUT', str(self.out))]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def put(self, relative, data=b'authored fixture'):
        target = self.out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def stage(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(builder.stage_project(types.SimpleNamespace()), 0)
        return self.out / 'project/bin'

    def test_windows_game_and_both_extension_targets_are_staged(self):
        expected = {'librta_game.dll': b'game interface fixture'}
        self.put('windows/librta_game.dll', expected['librta_game.dll'])
        for target in ('template_debug', 'template_release'):
            name = 'rta_godot.windows.%s.x86_64.dll' % target
            expected[name] = target.encode()
            self.put('xbin/windows/' + name, expected[name])
        self.put('windows/unrelated.bin', b'must not be staged')
        destination = self.stage()
        self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, expected)

    def test_requested_windows_party8_library_is_staged_instead_of_ordinary_library(self):
        self.put('windows/librta_game.dll', b'ordinary authored fixture')
        self.put('windows-p8/librta_game.dll', b'party8 authored fixture')
        with patch.dict(os.environ, {'RTA_GODOT_PARTY8': '1'}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(builder.stage_project(types.SimpleNamespace(platform='windows')), 0)
        self.assertEqual((self.out / 'project/bin/librta_game.dll').read_bytes(), b'party8 authored fixture')
        self.assertEqual((self.out / 'windows/librta_game.dll').read_bytes(), b'ordinary authored fixture')

    def test_missing_requested_party8_library_does_not_fall_back_or_overwrite_stage(self):
        self.put('windows/librta_game.dll', b'ordinary authored fixture')
        old = self.put('project/bin/librta_game.dll', b'old authored stage')
        with patch.dict(os.environ, {'RTA_GODOT_PARTY8': '1'}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(builder.stage_project(types.SimpleNamespace(platform='windows')), 1)
        self.assertEqual(old.read_bytes(), b'old authored stage')

    def test_mac_libraries_are_still_staged_and_missing_windows_files_are_optional(self):
        names = ('librta_game.dylib', 'librta_game_orig.dylib')
        for name in names:
            self.put('lib/' + name, name.encode())
        destination = self.stage()
        self.assertEqual(sorted(p.name for p in destination.iterdir()), sorted(names))

    def test_changed_content_with_same_size_and_timestamp_is_updated(self):
        source = self.put('windows/librta_game.dll', b'old-content')
        stamp = 1000000000
        os.utime(source, (stamp, stamp))
        destination = self.stage() / source.name
        self.assertEqual(destination.read_bytes(), b'old-content')
        # Populate filecmp's cache, then retain both size and mtime while changing bytes.
        self.stage()
        source.write_bytes(b'new-content')
        os.utime(source, (stamp, stamp))
        self.stage()
        self.assertEqual(destination.read_bytes(), b'new-content')
        self.assertEqual(source.stat().st_mtime_ns, destination.stat().st_mtime_ns)

    def test_identical_libraries_are_not_replaced(self):
        self.put('windows/librta_game.dll')
        self.put('xbin/windows/rta_godot.windows.template_debug.x86_64.dll')
        self.stage()
        with patch.object(builder.os, 'replace', side_effect=AssertionError('identical library replaced')):
            self.stage()


class GodotWindowsBuildTests(unittest.TestCase):
    def args(self, **changes):
        values = dict(platform='windows', arch='x86_64', release=True, jobs=2, opt='-O2', original=False, with_game=False)
        values.update(changes)
        return types.SimpleNamespace(**values)

    def test_windows_defaults_match_the_portable_runner(self):
        with patch.object(builder.sys, 'platform', 'win32'):
            self.assertEqual(builder.default_platform(), 'windows')
            self.assertEqual(builder.default_godot(), runner.default_godot())
            self.assertEqual(builder.build_priority(), [])
        with patch.object(builder.sys, 'platform', 'darwin'):
            self.assertEqual(builder.default_platform(), 'macos')
            self.assertEqual(builder.build_priority(), ['nice', '-n', '10'])

    def test_windows_lib_dispatch_preserves_output_and_failure(self):
        with patch.object(builder.subprocess, 'run', return_value=types.SimpleNamespace(returncode=7)) as child:
            self.assertEqual(builder.build_lib(self.args()), 7)
        command = child.call_args.args[0]
        self.assertEqual(command, [sys.executable, '-B', str(HERE / 'build_lib_win.py'), '--jobs', '2', '--opt=-O2'])
        self.assertEqual(child.call_args.kwargs['env']['RTA_GODOT_OUT'], builder.OUT)
        self.assertEqual(child.call_args.kwargs['cwd'], builder.ROOT)

    def test_windows_all_does_not_take_mac_snapshot(self):
        calls = []
        with patch.object(builder.sys, 'platform', 'win32'), patch.object(builder.sys, 'argv', ['build.py', 'all']), \
                patch.object(builder, 'snapshot', side_effect=AssertionError('Mac snapshot selected')), \
                patch.object(builder, 'build_lib', side_effect=lambda a: calls.append(('lib', a.platform)) or 0), \
                patch.object(builder, 'build_extension', side_effect=lambda a: calls.append(('extension', a.platform)) or 0), \
                patch.object(builder, 'stage_project', side_effect=lambda a: calls.append(('project', a.platform)) or 0):
            self.assertEqual(builder.main(), 0)
        self.assertEqual(calls, [('lib', 'windows'), ('extension', 'windows'), ('project', 'windows')])

    def test_windows_extension_uses_bundled_make_and_x86_64(self):
        with tempfile.TemporaryDirectory(prefix='godot-build-') as folder:
            deps = Path(folder) / 'deps'
            (deps / 'godot-cpp/src').mkdir(parents=True)
            (deps / 'godot-cpp/src/CMakeLists.txt').write_text('authored placeholder')
            make = str(Path(folder) / 'compiler with spaces/mingw32-make.exe')
            with patch.object(builder, 'DEPS', str(deps)), patch.object(builder, 'OUT', str(Path(folder) / 'out')), \
                    patch.object(builder.sys, 'platform', 'win32'), \
                    patch.object(builder.shutil, 'which', side_effect=lambda x: make if x == 'mingw32-make' else None), \
                    patch.object(builder.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0)) as child, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(builder.build_extension(self.args()), 0)
            commands = [c.args[0] for c in child.call_args_list]
            self.assertEqual(len(commands), 2)
            self.assertEqual(commands[0][0], 'cmake')
            self.assertIn('MinGW Makefiles', commands[0])
            self.assertIn('-DCMAKE_MAKE_PROGRAM=' + make, commands[0])
            self.assertIn('-DGODOTCPP_ARCH=x86_64', commands[0])
            self.assertIn('-DCMAKE_CXX_FLAGS=-include cstdlib', commands[0])
            self.assertIn('-DGODOTCPP_TARGET=template_release', commands[0])
            self.assertNotIn('nice', commands[1])

    def test_existing_cmake_generator_is_preserved(self):
        with tempfile.TemporaryDirectory(prefix='godot-build-') as folder:
            Path(folder, 'CMakeCache.txt').write_text('CMAKE_GENERATOR:INTERNAL=MinGW Makefiles')
            with patch.object(builder.shutil, 'which', side_effect=AssertionError('cached build needs no generator selection')):
                self.assertEqual(builder.extension_generator(folder), [])

    def test_windows_extension_can_select_ninja_or_fail_clearly(self):
        with patch.object(builder.sys, 'platform', 'win32'), patch.object(builder.os.path, 'isfile', return_value=False):
            with patch.object(builder.shutil, 'which', return_value='ninja.exe'):
                self.assertEqual(builder.extension_generator('new-build'), ['-G', 'Ninja'])
            with patch.object(builder.shutil, 'which', return_value=None):
                with self.assertRaisesRegex(ValueError, 'Ninja or llvm-mingw'):
                    builder.extension_generator('new-build')


class GodotExportTests(unittest.TestCase):
    def setUp(self):
        self.private = tempfile.TemporaryDirectory(prefix='godot-export-')
        self.addCleanup(self.private.cleanup)
        self.root = Path(self.private.name)
        self.source = self.root / 'source'
        self.out = self.root / 'private output'
        self.deps = self.root / 'deps'
        project = self.source / 'project'
        project.mkdir(parents=True)
        (project / 'project.godot').write_text('authored project')
        (project / 'export_presets.cfg').write_text('custom_template/release=""')
        (project / 'override.cfg').write_text('private test settings must be absent')
        (project / 'bin').mkdir()
        (project / 'bin/librta_game.dll').write_bytes(b'authored forbidden-name fixture')
        for target in ['debug', 'release']:
            self.put('xbin/windows/rta_godot.windows.template_%s.x86_64.dll' % target)
        self.editor = self.deps / 'godot-editor/Godot_v4.5.2-stable_win64.exe'
        self.editor.parent.mkdir(parents=True)
        self.editor.write_bytes(b'authored editor placeholder; never executed')
        self.archive = self.deps / 'godot-templates/Godot_v4.5.2-stable_export_templates.tpz'
        self.archive.parent.mkdir(parents=True)
        with zipfile.ZipFile(self.archive, 'w') as package:
            package.writestr('templates/windows_release_x86_64.exe', b'authored template')
            package.writestr('templates/version.txt', '4.5.2.stable')
            package.writestr('../outside.txt', 'must not be extracted')
            package.writestr('templates/librta_game.dll', 'must not be extracted')
        for item in [patch.object(builder, 'HERE', str(self.source)), patch.object(builder, 'OUT', str(self.out)),
                     patch.object(builder, 'DEPS', str(self.deps)), patch.object(builder.sys, 'platform', 'win32')]:
            item.start()
            self.addCleanup(item.stop)
        self.args = types.SimpleNamespace(platform='windows', arch='x86_64', with_game=False)

    def put(self, relative):
        p = self.out / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'authored extension fixture')
        return p

    def fake_editor(self, command, **kwargs):
        if '--export-release' in command:
            Path(command[-1]).write_bytes(b'authored exported application')
        return types.SimpleNamespace(returncode=0)

    def export(self, editor=None):
        with patch.dict(os.environ, {'RTA_GODOT': str(editor or self.editor)}), \
                patch.object(builder.subprocess, 'run', side_effect=self.fake_editor) as child, \
                contextlib.redirect_stdout(io.StringIO()):
            code = builder.export_app(self.args)
        return code, child

    def test_windows_export_is_private_and_contains_no_game_library(self):
        with patch.dict(os.environ, {'APPDATA': 'player roaming', 'LOCALAPPDATA': 'player local'}):
            code, child = self.export()
            self.assertEqual(os.environ['APPDATA'], 'player roaming')
            self.assertEqual(os.environ['LOCALAPPDATA'], 'player local')
        self.assertEqual(code, 0)
        self.assertEqual(len(child.call_args_list), 2)
        for call in child.call_args_list:
            self.assertEqual(call.args[0][0], str(self.editor))
            self.assertNotIn('nice', call.args[0])
            self.assertNotIn('unzip', call.args[0])
            self.assertEqual(Path(call.kwargs['env']['APPDATA']), self.out / 'godot-home/appdata')
            self.assertEqual(Path(call.kwargs['env']['LOCALAPPDATA']), self.out / 'godot-home/localappdata')
        staged = self.out / 'export/project'
        self.assertEqual(sorted(p.name for p in (staged / 'bin').iterdir()),
                         ['rta_godot.windows.template_debug.x86_64.dll', 'rta_godot.windows.template_release.x86_64.dll'])
        self.assertFalse((staged / 'override.cfg').exists())
        self.assertFalse((self.deps / 'outside.txt').exists())
        self.assertFalse((self.archive.parent / 'templates/librta_game.dll').exists())
        self.assertTrue((self.archive.parent / 'templates/windows_release_x86_64.exe').is_file())
        self.assertNotIn('\\', (staged / 'export_presets.cfg').read_text())

    def test_explicit_editor_path_is_used(self):
        other = self.root / 'different editor.exe'
        other.write_bytes(b'authored editor placeholder')
        code, child = self.export(other)
        self.assertEqual(code, 0)
        self.assertEqual(child.call_args_list[0].args[0][0], str(other))

    def test_existing_export_and_player_files_are_preserved(self):
        existing = self.put('export/windows/player-data/card/keep.dat')
        code, child = self.export()
        self.assertEqual(code, 1)
        child.assert_not_called()
        self.assertEqual(existing.read_bytes(), b'authored extension fixture')

    def test_explicit_destination_reuses_cache_and_preserves_previous_export(self):
        previous = self.put('export/windows/previous-client.dat')
        destination = self.root / 'versions/client 02'
        self.args.export_dir = str(destination)
        code, child = self.export()
        self.assertEqual(code, 0)
        self.assertTrue((destination / 'RtaGodot.exe').is_file())
        self.assertTrue(Path(str(destination) + '.export.log').is_file())
        self.assertEqual(previous.read_bytes(), b'authored extension fixture')
        self.assertEqual(child.call_args_list[1].args[0][-1], str(destination / 'RtaGodot.exe'))
        self.assertFalse(any(p.name.startswith('librta_game') for p in destination.rglob('*')))

    def test_existing_explicit_destination_is_preserved(self):
        previous = self.root / 'immutable-client'
        previous.mkdir()
        marker = previous / 'keep.dat'
        marker.write_bytes(b'previous immutable authored client')
        self.args.export_dir = str(previous)
        code, child = self.export()
        self.assertEqual(code, 1)
        child.assert_not_called()
        self.assertEqual(marker.read_bytes(), b'previous immutable authored client')

    def test_missing_editor_or_debug_extension_never_runs_export(self):
        code, child = self.export(self.root / 'missing editor.exe')
        self.assertEqual(code, 1)
        child.assert_not_called()
        (self.out / 'xbin/windows/rta_godot.windows.template_debug.x86_64.dll').unlink()
        code, child = self.export()
        self.assertEqual(code, 1)
        child.assert_not_called()

    def test_missing_template_member_is_reported_without_running_editor(self):
        with zipfile.ZipFile(self.archive, 'w') as package:
            package.writestr('templates/version.txt', '4.5.2.stable')
        code, child = self.export()
        self.assertEqual(code, 1)
        child.assert_not_called()
        self.assertFalse((self.out / 'export/windows').exists())

    def test_symlink_template_member_is_rejected(self):
        with zipfile.ZipFile(self.archive, 'w') as package:
            item = zipfile.ZipInfo('templates/windows_release_x86_64.exe')
            item.create_system = 3
            item.external_attr = 0o120777 << 16
            package.writestr(item, '../outside.exe')
            package.writestr('templates/version.txt', '4.5.2.stable')
        code, child = self.export()
        self.assertEqual(code, 1)
        child.assert_not_called()

    def test_failed_export_remains_a_failure(self):
        with patch.dict(os.environ, {'RTA_GODOT': str(self.editor)}), \
                patch.object(builder.subprocess, 'run', return_value=types.SimpleNamespace(returncode=3)), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(builder.export_app(self.args), 1)

    def test_failed_import_does_not_attempt_export(self):
        with patch.dict(os.environ, {'RTA_GODOT': str(self.editor)}), \
                patch.object(builder.subprocess, 'run', return_value=types.SimpleNamespace(returncode=3)) as child, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(builder.export_app(self.args), 1)
        self.assertEqual(child.call_count, 1)
        self.assertIn('--editor', child.call_args.args[0])

    def test_macos_export_keeps_posix_priority_and_platform_libraries(self):
        for target in ['release', 'debug']:
            self.put('project/bin/rta_godot.macos.template_%s.dylib' % target)
        with zipfile.ZipFile(self.archive, 'a') as package:
            package.writestr('templates/macos.zip', b'authored macOS template')
        self.args.platform = 'macos'
        with patch.object(builder.sys, 'platform', 'darwin'):
            code, child = self.export()
        self.assertEqual(code, 0)
        for call in child.call_args_list[:2]:
            self.assertEqual(call.args[0][:3], ['nice', '-n', '10'])
        self.assertTrue((self.out / 'export/macos/RtaGodot.app').is_file())
        self.assertEqual(sorted(p.name for p in (self.out / 'export/project/bin').iterdir()),
                         ['rta_godot.macos.template_debug.dylib', 'rta_godot.macos.template_release.dylib'])

    def test_zero_exit_import_script_error_prevents_export(self):
        def editor(command, **kwargs):
            kwargs['stdout'].write('\x1b[31mSCRIPT ERROR: authored parse failure\x1b[0m\n')
            return types.SimpleNamespace(returncode=0)
        with patch.dict(os.environ, {'RTA_GODOT': str(self.editor)}), \
                patch.object(builder.subprocess, 'run', side_effect=editor) as child, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(builder.export_app(self.args), 1)
        self.assertEqual(child.call_count, 1)

    def test_zero_exit_export_error_does_not_qualify_written_executable(self):
        def editor(command, **kwargs):
            result = self.fake_editor(command, **kwargs)
            if '--export-release' in command:
                kwargs['stdout'].write('ERROR: authored export dependency failure\n')
            return result
        with patch.dict(os.environ, {'RTA_GODOT': str(self.editor)}), \
                patch.object(builder.subprocess, 'run', side_effect=editor), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(builder.export_app(self.args), 1)
        self.assertTrue((self.out / 'export/windows/RtaGodot.exe').exists())

    def test_non_mac_with_game_is_refused(self):
        self.args.with_game = True
        code, child = self.export()
        self.assertEqual(code, 1)
        child.assert_not_called()


if __name__ == '__main__':
    unittest.main()
