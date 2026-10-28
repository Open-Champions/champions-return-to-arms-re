"""Windows game-library module selection; authored headers/files, no game or compiler."""
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


HERE = Path(__file__).parent / 'godot'


def load_builder():
    spec = importlib.util.spec_from_file_location('godot_windows_feature_builder', HERE / 'build_lib_win.py')
    module = importlib.util.module_from_spec(spec)
    previous = sys.path[:]
    try:
        with patch.dict(os.environ):
            spec.loader.exec_module(module)
    finally:
        sys.path[:] = previous
    return module


builder = load_builder()


class GodotFeatureModuleTests(unittest.TestCase):
    def select(self, originals=('orig_00199944', 'orig_0010a620'), missing=(), party8=False, slots=True):
        with tempfile.TemporaryDirectory(prefix='godot-modules-') as folder:
            root = Path(folder)
            snap, gen = root / 'src' / 'recomp', root / 'gen'
            app = snap / 'app'
            app.mkdir(parents=True)
            render = snap / 'render'
            render.mkdir()
            for name in builder.gb.RENDER_CORE:
                (render / name).touch()
            selected = Path(str(gen) + '-p8') if party8 else gen
            selected.mkdir()
            (selected / 'funcs.h').write_text('\n'.join(originals) + ('\ng_party8_slots' if slots and party8 else ''))
            modules = ('fpcontrols.cpp', 'soulscombat.cpp', 'cinematic.cpp', 'cinematic_hle.cpp',
                       'partyscale.cpp', 'partyscale_hle.cpp', 'party8.cpp')
            for name in modules:
                if name not in missing:
                    (app / name).touch()
            captured = []

            def capture(sources, objdir, *_):
                self.object_directory = objdir
                captured.extend(sources)
                return []

            args = types.SimpleNamespace(compiler='clang', opt='-O2', jobs=1)
            with patch.dict(os.environ, {'RTA_GODOT_PARTY8': '1' if party8 else '0'}), \
                    patch.object(builder.gb, 'SNAP', str(snap)), patch.object(builder.gb, 'SRC', str(root / 'src')), \
                    patch.object(builder, 'GEN', str(gen)), patch.object(builder, 'WINDOWS', str(root / 'windows')), \
                    patch.object(builder.bw, 'find_toolchain', return_value=(['clang++'], ['clang++'], None, 'authored test')), \
                    patch.object(builder.bw, 'source_jobs', side_effect=capture), \
                    patch.object(builder.bw, 'translate', return_value=True) as translation, \
                    patch.object(builder.bw, 'compile_all', return_value=True), \
                    patch.object(builder, 'game_objects', return_value=None) as game, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(builder.build(args), 1)  # intercepted before any compilation or link
                self.translation = translation.call_args
                self.game_flags = game.call_args.args[2] if game.called else []
            return {Path(source).name: flags for source, flags, _ in captured}

    def test_eight_player_variant_uses_64mb_everywhere_and_separate_output(self):
        sources = self.select(party8=True)
        self.assertIn('party8.cpp', sources)
        self.assertIn('-DRTAG_HAVE_PARTY8', sources['rtag.cpp'])
        self.assertIn('-DRECOMP_RELOC_DYN', self.game_flags)
        self.assertIn('-DRAM_SIZE=0x04000000u', self.game_flags)
        for name in ('runtime.cpp', 'host_godot.cpp', 'gs.cpp', 'renderer.cpp', 'fpcontrols.cpp',
                     'rtag.cpp', 'scene_export.cpp', 'skeleton_export.cpp', 'party8.cpp', 'soulscombat.cpp'):
            self.assertIn('-DRAM_SIZE=0x04000000u', sources[name], name)
        self.assertTrue(self.object_directory.endswith(os.path.join('windows-p8', 'obj-clang')))
        translated = self.translation.args[0]
        self.assertTrue(translated.party8)
        self.assertFalse(translated.original)
        self.assertTrue(translated.gen.endswith('gen-p8'))

    def test_eight_player_translation_without_slot_definitions_is_rejected(self):
        self.assertEqual(self.select(party8=True, slots=False), {})

    def test_eight_player_missing_module_is_rejected(self):
        self.assertEqual(self.select(party8=True, missing=('party8.cpp',)), {})

    def test_complete_pairs_and_cinematic_capability(self):
        sources = self.select()
        for name in ('cinematic.cpp', 'cinematic_hle.cpp', 'partyscale.cpp', 'partyscale_hle.cpp'):
            self.assertIn(name, sources)
            self.assertEqual(sources[name], sources['app_rt.cpp'])
        self.assertIn('-DRTAG_HAVE_CINE', sources['rtag.cpp'])
        self.assertNotIn('-DRTAG_HAVE_PARTY8', sources['rtag.cpp'])
        self.assertFalse(any(flag.startswith('-DRAM_SIZE=') for flags in sources.values() for flag in flags))

    def test_missing_cinematic_original_keeps_original_fallback(self):
        sources = self.select(originals=('orig_0010a620',))
        self.assertNotIn('cinematic.cpp', sources)
        self.assertNotIn('cinematic_hle.cpp', sources)
        self.assertNotIn('-DRTAG_HAVE_CINE', sources['rtag.cpp'])

    def test_cinematic_implementation_and_wrapper_are_atomic(self):
        for missing in ('cinematic.cpp', 'cinematic_hle.cpp'):
            with self.subTest(missing=missing):
                sources = self.select(missing=(missing,))
                self.assertNotIn('cinematic.cpp', sources)
                self.assertNotIn('cinematic_hle.cpp', sources)
                self.assertNotIn('-DRTAG_HAVE_CINE', sources['rtag.cpp'])

    def test_missing_scaling_original_keeps_original_fallback(self):
        sources = self.select(originals=('orig_00199944',))
        self.assertNotIn('partyscale.cpp', sources)
        self.assertNotIn('partyscale_hle.cpp', sources)
        self.assertIn('-DRTAG_HAVE_SOULS', sources['rtag.cpp'])

    def test_scaling_requires_complete_pair_and_combat_controls(self):
        for missing in ('partyscale.cpp', 'partyscale_hle.cpp', 'soulscombat.cpp', 'fpcontrols.cpp'):
            with self.subTest(missing=missing):
                sources = self.select(missing=(missing,))
                self.assertNotIn('partyscale.cpp', sources)
                self.assertNotIn('partyscale_hle.cpp', sources)


class WindowsPartyTranslationTests(unittest.TestCase):
    def test_party_translation_uses_both_inputs_and_separate_directory(self):
        with tempfile.TemporaryDirectory(prefix='party8-translation-') as folder:
            root = Path(folder)
            regular = root / 'gen-app'
            regular.mkdir()
            (regular / 'keep.txt').write_text('ordinary translation remains intact')
            selected = root / 'gen-app-p8'
            args = types.SimpleNamespace(gen=str(selected), original=False, no_game=False, no_net=True, party8=True)
            commands = []

            def translated(command, **_):
                commands.append(command)
                scratch = Path(command[command.index('--out') + 1])
                scratch.mkdir()
                (scratch / 'funcs.h').write_text('authored g_party8_slots declaration')
                return types.SimpleNamespace(returncode=0, stdout='', stderr='')

            with patch.object(builder.bw.subprocess, 'run', side_effect=translated), contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(builder.bw.translate(args))
            command = commands[0]
            self.assertTrue(command[command.index('--reloc') + 1].endswith('party8-ranges.txt'))
            self.assertTrue(command[command.index('--reloc-sites') + 1].endswith('party8-sites.txt'))
            self.assertTrue((selected / 'funcs.h').exists())
            self.assertEqual((regular / 'keep.txt').read_text(), 'ordinary translation remains intact')

    def test_cli_party_translation_returns_before_compiling(self):
        with patch.object(builder.bw.sys, 'argv', ['build_win.py', '--party8', '--translate-only']), \
                patch.object(builder.bw, 'translate', return_value=True) as translate, \
                patch.object(builder.bw, 'find_toolchain') as compiler:
            self.assertEqual(builder.bw.main(), 0)
        self.assertTrue(translate.call_args.args[0].gen.endswith('gen-app-p8'))
        compiler.assert_not_called()

    def test_cli_refuses_partial_native_party_build(self):
        with patch.object(builder.bw.sys, 'argv', ['build_win.py', '--party8']), \
                patch.object(builder.bw, 'translate') as translate, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                builder.bw.main()
        self.assertEqual(error.exception.code, 2)
        translate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
