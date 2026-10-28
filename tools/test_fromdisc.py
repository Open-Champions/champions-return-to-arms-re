"""Installer completion contracts using authored temporary files; no disc, compiler or application is run."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).parent / 'install' / 'fromdisc.py'
spec = importlib.util.spec_from_file_location('installer_completion_tests', SOURCE)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerCompletionTests(unittest.TestCase):
    def setUp(self):
        self.private = tempfile.TemporaryDirectory(prefix='champions-install-')
        self.addCleanup(self.private.cleanup)
        self.root = Path(self.private.name)
        self.disc = self.put('authored input.iso', b'authored placeholder; never parsed')
        self.native = self.put('local/native/rta_app.exe', b'authored native fixture')
        self.library = self.put('user/godot/librta_game.dll', b'previous authored library')
        self.record = self.put('local/install.txt', b'previous authored install record')
        for item in [patch.object(installer, 'ROOT', str(self.root)),
                     patch.object(installer, 'PROGRESS', {'on': False, 'last': -1}),
                     patch.object(installer, 'extract_elf', return_value=True),
                     patch.object(installer, 'vu1_translation'),
                     patch.object(installer, 'build', return_value=str(self.native))]:
            item.start()
            self.addCleanup(item.stop)

    def put(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def invoke(self, extra, result=None, error=None, platform='windows'):
        output = io.StringIO()
        args = ['fromdisc.py', '--platform', platform, '--disc', str(self.disc), '--progress'] + extra
        with patch.object(installer.sys, 'argv', args), \
                patch.object(installer, 'godot_library', return_value=result, side_effect=error) as godot, \
                patch.object(installer, 'desktop_dir', return_value=str(self.root / 'desktop')) as desktop, \
                patch.object(installer, 'launcher_windows', return_value='authored launcher') as launcher, \
                contextlib.redirect_stdout(output):
            code = installer.main()
        return code, output.getvalue(), godot, desktop, launcher

    def assert_previous_artifacts(self):
        self.assertEqual(self.native.read_bytes(), b'authored native fixture')
        self.assertEqual(self.library.read_bytes(), b'previous authored library')
        self.assertEqual(self.record.read_bytes(), b'previous authored install record')

    def test_requested_godot_failure_is_incomplete_on_every_platform(self):
        for platform in ['mac', 'linux', 'windows']:
            with self.subTest(platform=platform):
                code, output, godot, desktop, launcher = self.invoke(['--godot'], platform=platform)
                self.assertEqual(code, 1)
                self.assertIn('Godot was requested', output)
                self.assertIn(str(self.native), output)
                self.assertNotIn('@progress 100', output)
                self.assertNotIn('[install] done.', output)
                godot.assert_called_once()
                desktop.assert_not_called()
                launcher.assert_not_called()
                self.assert_previous_artifacts()

    def test_requested_godot_exception_preserves_native_library_and_diagnostic(self):
        code, output, _, _, launcher = self.invoke(['--godot'], error=OSError('authored compiler unavailable'))
        self.assertEqual(code, 1)
        self.assertIn('authored compiler unavailable', output)
        launcher.assert_not_called()
        self.assert_previous_artifacts()

    def test_requested_godot_missing_returned_file_is_not_success(self):
        code, output, _, _, launcher = self.invoke(['--godot'], result=str(self.root / 'missing.dll'))
        self.assertEqual(code, 1)
        self.assertIn('installation is incomplete', output)
        launcher.assert_not_called()
        self.assert_previous_artifacts()

    def test_native_only_still_succeeds_and_makes_requested_launcher(self):
        code, output, godot, _, launcher = self.invoke([])
        self.assertEqual(code, 0)
        godot.assert_not_called()
        launcher.assert_called_once()
        self.assertIn('@progress 100 Done', output)
        self.assertIn('program=' + str(self.native), self.record.read_text())
        self.assertNotIn('godot_library=', self.record.read_text())
        self.assertEqual(self.library.read_bytes(), b'previous authored library')

    def test_requested_godot_success_records_library_and_launcher(self):
        code, output, _, _, launcher = self.invoke(['--godot'], result=str(self.library))
        self.assertEqual(code, 0)
        launcher.assert_called_once()
        self.assertIn('@progress 100 Done', output)
        self.assertIn('godot_library=' + str(self.library), self.record.read_text())


class GodotLibraryInstallTests(unittest.TestCase):
    def setUp(self):
        self.private = tempfile.TemporaryDirectory(prefix='champions-library-install-')
        self.addCleanup(self.private.cleanup)
        self.root = Path(self.private.name)
        self.put('tools/godot/build_lib_win.py', b'authored placeholder; never run')
        self.library = self.put('user/godot/librta_game.dll', b'previous authored library')
        for item in [patch.object(installer, 'ROOT', str(self.root)),
                     patch.object(installer, 'godot_folder', return_value=str(self.library.parent)),
                     patch.object(installer, 'Watch', side_effect=lambda *a, **k: contextlib.nullcontext()),
                     patch.dict(os.environ, {'RTA_GODOT_PARTY8': '0'})]:
            item.start()
            self.addCleanup(item.stop)

    def put(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def install(self, returncode=0):
        with patch.object(installer.subprocess, 'run', return_value=types.SimpleNamespace(returncode=returncode)), \
                contextlib.redirect_stdout(io.StringIO()):
            return installer.godot_library('windows', 2)

    def test_failed_build_does_not_install_stale_output_or_replace_library(self):
        self.put('local/godot-install/windows/librta_game.dll', b'stale authored output')
        self.assertIsNone(self.install(returncode=3))
        self.assertEqual(self.library.read_bytes(), b'previous authored library')

    def test_missing_output_preserves_existing_library(self):
        self.assertIsNone(self.install())
        self.assertEqual(self.library.read_bytes(), b'previous authored library')

    def test_success_replaces_only_the_library_with_new_output(self):
        made = self.put('local/godot-install/windows/librta_game.dll', b'new authored output')
        self.assertEqual(self.install(), str(self.library))
        self.assertEqual(self.library.read_bytes(), b'new authored output')
        self.assertEqual(made.read_bytes(), b'new authored output')

    def test_copy_failure_leaves_previous_library_intact(self):
        self.put('local/godot-install/windows/librta_game.dll', b'new authored output')
        with patch.object(installer.shutil, 'copy2', side_effect=OSError('authored copy failure')):
            with self.assertRaisesRegex(OSError, 'authored copy failure'):
                self.install()
        self.assertEqual(self.library.read_bytes(), b'previous authored library')

    def test_explicit_party8_uses_its_own_output_without_ordinary_fallback(self):
        ordinary = self.put('local/godot-install/windows/librta_game.dll', b'ordinary authored output')
        with patch.dict(os.environ, {'RTA_GODOT_PARTY8': '1'}):
            self.assertIsNone(self.install())
            self.assertEqual(self.library.read_bytes(), b'previous authored library')
            self.put('local/godot-install/windows-p8/librta_game.dll', b'party8 authored output')
            self.assertEqual(self.install(), str(self.library))
        self.assertEqual(self.library.read_bytes(), b'party8 authored output')
        self.assertEqual(ordinary.read_bytes(), b'ordinary authored output')


if __name__ == '__main__':
    unittest.main()
