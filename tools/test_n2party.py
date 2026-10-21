"""Portable native-rendezvous driver contracts; no game files, services or processes."""
import argparse
import importlib.util
import io
from contextlib import redirect_stderr
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).parent
SOURCE = HERE / 'recomp' / 'net2' / 'n2party.py'
SPEC = importlib.util.spec_from_file_location('n2party_portable', SOURCE)
qa = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qa)


def arguments(**overrides):
    values = dict(kind='native', offscreen=False, program='test-game', relay='', external=False,
                  pace=59.94, tls=False, port=41977, service_address='127.0.0.1', scenario='plain',
                  level_option=None, opt=[], tick_watch=[], idle=False, seed=1, play=120, level=None,
                  play2=120, rounds=2, limit=120)
    values.update(overrides)
    return argparse.Namespace(**values)


class N2PartyTests(unittest.TestCase):
    def capture_copy(self, args):
        captured = {}
        def capture(command, **kwargs):
            captured.update(command=command, kwargs=kwargs)
            kwargs['stdout'].close()
            return Mock()
        with tempfile.TemporaryDirectory(prefix='n2party-') as directory:
            run = os.path.join(directory, 'run1')
            os.mkdir(run)
            with patch.dict(os.environ, {'RTA_DISC': 'test-disc.iso'}), patch.object(qa.subprocess, 'Popen', side_effect=capture):
                qa.start_copy('host', 0, directory, run, '', 2, args)
            captured['script'] = Path(run, 'host.rig').read_text()
        return captured

    def test_native_default_keeps_headless_argument_order(self):
        got = self.capture_copy(arguments())
        command = got['command']
        self.assertEqual(command[:3], ['test-game', 'boot', '--elf'])
        self.assertIn('--card', command)
        self.assertNotIn('--offscreen', command)
        self.assertNotIn('--', command)

    def test_window_app_receives_script_before_runtime_separator(self):
        got = self.capture_copy(arguments(kind='window', offscreen=True))
        command = got['command']
        split = command.index('--')
        for key in ('--script', '--data', '--offscreen', '--no-settings', '--no-sound', '--elf'):
            self.assertIn(key, command[:split])
        self.assertIn('--sym', command[split + 1:])
        self.assertIn('net-local-only=1', command[split + 1:])
        self.assertIn('net2-bind=127.0.0.1:0', command[split + 1:])
        self.assertNotIn('--card', command)
        self.assertFalse(any(v.startswith('net2-level=') for v in command))
        self.assertFalse(any(line.split()[:1] in (['poke'], ['call']) for line in got['script'].splitlines()))

    def test_local_forced_relay_is_explicit(self):
        command = self.capture_copy(arguments(kind='window', offscreen=True, relay='force'))['command']
        self.assertIn('net2-relay=force', command)
        self.assertIn('net2-service=127.0.0.1:41977', command)

    def test_windows_child_does_not_use_posix_preexec(self):
        with patch.object(qa.os, 'name', 'nt'), patch.object(qa.subprocess, 'CREATE_NO_WINDOW', 0x08000000, create=True):
            self.assertEqual(qa.child_options(), {'creationflags': 0x08000000})
        with patch.object(qa.os, 'name', 'posix'):
            self.assertIn('preexec_fn', qa.child_options())

    def test_windows_cleanup_terminates_only_owned_service(self):
        process = Mock()
        process.poll.return_value = None
        with patch.object(qa.os, 'name', 'nt'):
            qa.stop_service(process)
        process.terminate.assert_called_once_with()
        process.send_signal.assert_not_called()
        process.wait.assert_called_once_with(5)

    def test_posix_cleanup_keeps_sigint_and_bounded_kill(self):
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired('test', 5), 0]
        with patch.object(qa.os, 'name', 'posix'):
            qa.stop_service(process)
        process.send_signal.assert_called_once_with(2)
        process.kill.assert_called_once_with()

    def test_no_getloadavg_is_supported(self):
        with patch.object(qa.os, 'getloadavg', side_effect=AttributeError, create=True):
            self.assertEqual(qa.load_average(), 'unavailable')

    def test_comparison_requires_success_and_positive_confirmed_frames(self):
        good = 'ticks: A has 20, B has 20, compared 20\nRESULT: no shared column differs on any tick\n'
        self.assertEqual(qa.comparison_result(good, 0), (20, True))
        self.assertFalse(qa.comparison_result(good, 1)[1])
        self.assertFalse(qa.comparison_result(good.replace('compared 20', 'compared 0'), 0)[1])
        self.assertFalse(qa.comparison_result('no shared column differs', 0)[1])
        self.assertFalse(qa.comparison_result('compared 20\nRESULT: DIFFER', 0)[1])

    def test_launched_but_premature_exit_does_not_pass(self):
        roles = ['host', 'j1']
        self.assertTrue(qa.copies_finished(roles, dict(host=True, j1=True), dict(host=0, j1=0)))
        self.assertFalse(qa.copies_finished(roles, dict(host=True, j1=False), dict(host=0, j1=0)))
        self.assertFalse(qa.copies_finished(roles, dict(host=True, j1=True), dict(host=0, j1=1)))
        self.assertFalse(qa.copies_finished(roles, dict(host=True, j1=True), dict(host=0, j1=None)))

    def test_deliberate_drop_requires_ready_and_driver_kill(self):
        args = (['host', 'j1'], dict(host=True, j1=False), dict(host=0, j1=-9))
        self.assertTrue(qa.copies_finished(*args, victim='j1', killed=True, ready=True))
        self.assertFalse(qa.copies_finished(*args, victim='j1', killed=False, ready=True))
        self.assertFalse(qa.copies_finished(*args, victim='j1', killed=True, ready=False))

    def test_localhost_main_does_not_need_platform_address_lookup(self):
        with tempfile.TemporaryDirectory(prefix='n2party-main-') as directory:
            Path(directory, 'service.log').write_text('test service stopped\n')
            service = Mock(pid=42)
            argv = ['n2party.py', directory, '--kind', 'window', '--offscreen']
            with patch.object(sys, 'argv', argv), patch.dict(os.environ, {'RTA_DISC': 'test.iso'}), \
                    patch.object(qa, 'own_addresses', side_effect=AssertionError('must not resolve localhost')), \
                    patch.object(qa, 'start_service', return_value=service), \
                    patch.object(qa, 'one_launch', return_value=True), patch.object(qa, 'stop_service') as stop:
                self.assertEqual(qa.main(), 0)
            stop.assert_called_once_with(service)


    def test_external_driver_failure_is_not_suppressed_by_cleanup(self):
        with tempfile.TemporaryDirectory(prefix='n2party-external-') as directory:
            argv = ['n2party.py', directory, '--external']
            with patch.object(sys, 'argv', argv), patch.dict(os.environ, {'RTA_DISC': 'test.iso'}), \
                    patch.object(qa, 'one_launch', side_effect=RuntimeError('trial failed')):
                with self.assertRaisesRegex(RuntimeError, 'trial failed'):
                    qa.main()

    def test_again_requires_expected_game_logs_from_both_peers(self):
        self.assertFalse(qa.have_expected_games({'host': ['first'], 'j1': ['first']}, 2))
        self.assertFalse(qa.have_expected_games({'host': ['first', 'second'], 'j1': ['first']}, 2))
        self.assertTrue(qa.have_expected_games({'host': ['first', 'second'], 'j1': ['first', 'second']}, 2))
        self.assertFalse(qa.have_expected_games({}, 1))

    def test_zero_or_negative_trial_counts_are_rejected_before_launch(self):
        for option in ('--launches', '--rounds'):
            for value in ('0', '-1'):
                with self.subTest(option=option, value=value), \
                        patch.object(sys, 'argv', ['n2party.py', 'unused', option, value]), \
                        patch.dict(os.environ, {'RTA_DISC': 'test.iso'}), \
                        patch.object(qa, 'start_service') as start, redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as stopped:
                        qa.main()
                    self.assertEqual(stopped.exception.code, 2)
                    start.assert_not_called()

if __name__ == '__main__':
    unittest.main()
