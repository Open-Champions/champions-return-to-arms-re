"""Authored capture-admission controls; no compiler, engine, game or GPU launch."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest


_spec = importlib.util.spec_from_file_location(
    'retained_shadow_runner_under_test', Path(__file__).parent / 'godot/tests/run_retained_base.py')
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)

PHASES = ('seed_far', 'left_shadow', 'left_unshadowed', 'left_shadow_restored',
          'right_shadow', 'right_repeat', 'outside', 'return_left')
ROW_FLAGS = ('passed', 'base_pixels_valid', 'camera_valid', 'retained_path_valid',
             'same_scenario', 'shadow_roi_valid', 'shadow_mask_valid', 'raw_rgba_saved')
REPORT_FLAGS = ('passed', 'stationary_full_rgba_equal', 'return_full_rgba_equal',
                'outside_full_rgba_equal')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def png_header(width=128, height=128):
    # Only the header is authored: this tests the runner's artifact-shape gate,
    # while decoding/rendered pixels are covered by the actual GPU fixture.
    return (b'\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR'
            + width.to_bytes(4, 'big') + height.to_bytes(4, 'big')
            + b'\x08\x06\x00\x00\x00' + b'\x00' * 4)


class RetainedShadowCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='retained-shadow-artifacts-')
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)
        groups = (0, 1, 2, 1, 3, 3, 0, 1)
        self.report = {flag: True for flag in REPORT_FLAGS}
        self.report['cases'] = []
        for index, phase in enumerate(PHASES):
            raw = bytes((groups[index], 20, 40, 255)) * (128 * 128)
            (self.out / (phase + '.rgba')).write_bytes(raw)
            (self.out / (phase + '.png')).write_bytes(png_header())
            self.report['cases'].append({
                'phase': phase, 'size': [128, 128], 'rgba_bytes': len(raw),
                'rgba_sha256': digest(raw), 'capture_exit': 0,
                **{flag: True for flag in ROW_FLAGS},
            })

    def rejected(self, report):
        valid, captures = runner.retained_shadow_captures(self.out, report)
        self.assertIs(valid, False)
        self.assertIsInstance(captures, dict)

    def test_complete_ordered_evidence_returns_all_sixteen_actual_hashes(self):
        self.assertEqual(runner.SHADOW_PHASES, PHASES)
        valid, captures = runner.retained_shadow_captures(self.out, self.report)
        self.assertIs(valid, True)
        expected = {phase + suffix: digest((self.out / (phase + suffix)).read_bytes())
                    for phase in PHASES for suffix in ('.png', '.rgba')}
        self.assertEqual(captures, expected)
        self.assertEqual(len(captures), 16)

    def test_omitted_reordered_duplicate_or_extra_phase_is_rejected(self):
        mutations = (list(PHASES[:-1]), [PHASES[1], PHASES[0], *PHASES[2:]],
                     [*PHASES[:-1], PHASES[-2]], [*PHASES, PHASES[-1]])
        rows = {row['phase']: row for row in self.report['cases']}
        for phases in mutations:
            with self.subTest(phases=phases):
                report = copy.deepcopy(self.report)
                report['cases'] = [copy.deepcopy(rows[phase]) for phase in phases]
                self.rejected(report)

    def test_every_phase_flag_requires_boolean_true_and_capture_exit_integer_zero(self):
        for flag in ROW_FLAGS:
            for value in (False, 1, 'true', None):
                with self.subTest(flag=flag, value=value):
                    report = copy.deepcopy(self.report)
                    report['cases'][3][flag] = value
                    self.rejected(report)
            report = copy.deepcopy(self.report)
            del report['cases'][3][flag]
            self.rejected(report)
        for value in (False, True, 0.0, '0', None, 1):
            with self.subTest(capture_exit=value):
                report = copy.deepcopy(self.report)
                report['cases'][3]['capture_exit'] = value
                self.rejected(report)

    def test_report_pass_and_all_full_image_equalities_require_boolean_true(self):
        for flag in REPORT_FLAGS:
            for value in (False, 1, 'true', None):
                with self.subTest(flag=flag, value=value):
                    report = copy.deepcopy(self.report)
                    report[flag] = value
                    self.rejected(report)
            report = copy.deepcopy(self.report)
            del report[flag]
            self.rejected(report)

    def test_actual_full_image_equality_is_rechecked_despite_matching_row_hashes(self):
        for phase in ('right_repeat', 'return_left', 'outside'):
            with self.subTest(phase=phase):
                path = self.out / (phase + '.rgba')
                original = path.read_bytes()
                changed = bytes((original[0] ^ 1,)) + original[1:]
                path.write_bytes(changed)
                report = copy.deepcopy(self.report)
                row = next(row for row in report['cases'] if row['phase'] == phase)
                row['rgba_sha256'] = digest(changed)
                self.assertTrue(all(report[flag] is True for flag in REPORT_FLAGS))
                self.rejected(report)
                path.write_bytes(original)

    def test_missing_png_or_raw_file_is_rejected(self):
        for suffix in ('.png', '.rgba'):
            path = self.out / (PHASES[2] + suffix)
            original = path.read_bytes()
            with self.subTest(suffix=suffix):
                path.unlink()
                self.rejected(self.report)
            path.write_bytes(original)

    def test_raw_size_is_checked_even_when_the_reported_hash_matches(self):
        path = self.out / (PHASES[2] + '.rgba')
        original = path.read_bytes()
        for size in (0, 1, 128 * 128 * 4 - 1, 128 * 128 * 4 + 1):
            with self.subTest(size=size):
                raw = b'\0' * size
                path.write_bytes(raw)
                report = copy.deepcopy(self.report)
                report['cases'][2].update(rgba_sha256=digest(raw), rgba_bytes=size)
                self.rejected(report)
        path.write_bytes(original)

    def test_png_magic_ihdr_dimensions_and_truncation_are_rejected(self):
        path = self.out / (PHASES[2] + '.png')
        original = path.read_bytes()
        for data in (b'', b'not PNG!' + original[8:], original[:12] + b'NOPE' + original[16:],
                     png_header(127, 128), png_header(128, 129), original[:23]):
            with self.subTest(header=data):
                path.write_bytes(data)
                self.rejected(self.report)
        path.write_bytes(original)

    def test_changed_raw_or_malformed_report_cannot_pass(self):
        path = self.out / (PHASES[2] + '.rgba')
        original = path.read_bytes()
        path.write_bytes(bytes((original[0] ^ 1,)) + original[1:])
        self.rejected(self.report)
        path.write_bytes(original)
        report = copy.deepcopy(self.report)
        report['cases'][2]['rgba_sha256'] = '0' * 64
        self.rejected(report)
        malformed = (None, [], 'report', {}, {'cases': None}, {'cases': {}},
                     {**self.report, 'cases': [None] * 8},
                     {**self.report, 'cases': [1] * 8})
        for report in malformed:
            with self.subTest(report=report):
                self.rejected(report)


if __name__ == '__main__':
    unittest.main()
