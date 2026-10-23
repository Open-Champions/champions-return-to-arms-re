"""Guards against false-positive Windows qualification receipts; no game data."""
import hashlib
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).parent / 'recomp' / 'app' / 'win' / 'qualify.py'
SPEC = importlib.util.spec_from_file_location('windows_qualification', SOURCE)
qa = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qa)


class QualificationTests(unittest.TestCase):
    def test_unsupported_elf_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported executable SHA-256'):
            qa.check_elf_bytes(b'not the supported executable')

    def test_hash_covers_bytes_not_only_ps2_xor(self):
        a = bytes.fromhex('0100000002000000')
        b = bytes.fromhex('0000000003000000')
        self.assertEqual(1 ^ 2, 0 ^ 3)
        with patch.object(qa, 'ELF_SHA256', hashlib.sha256(a).hexdigest()):
            self.assertEqual(qa.check_elf_bytes(a), hashlib.sha256(a).hexdigest())
            with self.assertRaises(ValueError):
                qa.check_elf_bytes(b)

    def test_missing_disc_executable_rejected(self):
        class Missing:
            def __init__(self, _path): self.f = io.BytesIO()
            def find(self, _name): return None
        with patch.object(qa, 'Iso', Missing):
            with self.assertRaisesRegex(ValueError, 'no SLUS_209.73'):
                qa.check_disc('synthetic.iso')

    def test_truncated_disc_executable_rejected(self):
        class Truncated:
            def __init__(self, _path): self.f = io.BytesIO(b'abc')
            def find(self, _name): return {'lba': 0, 'size': 100}
        with patch.object(qa, 'Iso', Truncated):
            with self.assertRaisesRegex(ValueError, 'truncated'):
                qa.check_disc('synthetic.iso')

    def test_tracked_output_directory_rejected(self):
        with self.assertRaisesRegex(ValueError, 'outside the checkout or under local'):
            qa.private_output(qa.ROOT / 'docs' / 'unsafe-output')
        self.assertEqual(qa.private_output(qa.ROOT / 'local' / 'checks'), qa.ROOT / 'local' / 'checks')

    def test_zero_unknown_metrics_are_success_not_error(self):
        self.assertEqual(qa.failures('VU1 instructions not implemented 0; GS registers unknown 0'), [])
        self.assertTrue(qa.failures('VU1 instructions not implemented 1; GS registers unknown 0'))
        self.assertTrue(qa.failures('VU1 instructions not implemented 0; GS registers unknown 2'))
        self.assertTrue(qa.failures('TIMEOUT waiting for a mission'))

    def test_boot_exit_zero_is_not_enough(self):
        self.assertFalse(qa.boot_result('exited successfully')['passed'])
        good = '=hub\nframes=2309 wall=1.2s\nfields=2413 units=113069252\nVU0: 466083 microprogram calls, 26111361 instructions'
        self.assertTrue(qa.boot_result(good)['passed'])
        self.assertFalse(qa.boot_result(good.replace('113069252', '113069251'))['passed'])
        self.assertFalse(qa.boot_result(good + '\nTIMEOUT')['passed'])

    @staticmethod
    def alias_trace(held, released):
        return ('QA_CASE overlap_e_shift\n'
                'holds buttons %s, sticks 128 128 128 128; keyboard bits %s\n'
                'holds buttons %s, sticks 128 128 128 128; keyboard bits %s\n'
                'QA_INPUT_COMPLETE\n') % (held, held, released, released)

    def test_alias_release_regression_and_stuck_key_fail(self):
        def alias(text):
            return next(c for c in qa.input_result(text)['cases'] if c['case'] == 'overlap_e_shift')['passed']
        self.assertTrue(alias(self.alias_trace('0800', '0000')))
        self.assertFalse(alias(self.alias_trace('0000', '0000')))
        self.assertFalse(alias(self.alias_trace('0800', '0800')))

    def test_completion_marker_cannot_replace_input_evidence(self):
        self.assertFalse(qa.input_result('QA_INPUT_COMPLETE')['passed'])


if __name__ == '__main__':
    unittest.main()
