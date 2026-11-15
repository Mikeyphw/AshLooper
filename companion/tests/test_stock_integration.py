"""RF03: real shell execution against a fake stock-AshReXcue filesystem.
Never accesses live /data/adb, Android's notification service, or a device.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile
import sys
import runpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MAIN = ROOT / 'bin' / 'companion.sh'
HEADER = '[08:11:00] >[{}]<\n'


class StockAshLooperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mods = self.root / 'modules'
        self.logs = self.root / 'looper'
        self.vault = self.root / 'vault'
        self.scripts = self.root / 'service.d'
        self.state = self.root / 'companion-state'
        self.calls = self.root / 'notification-requests'
        for folder in (self.mods, self.logs, self.vault, self.scripts):
            folder.mkdir()
        self.ashdir = self.mods / 'AshLooper'
        self.ashdir.mkdir()
        (self.ashdir / 'module.prop').write_text('id=AshLooper\nname=Original AshReXcue\n')
        self.settings = self.ashdir / 'settings.prop'
        self.settings.write_text('boot=booted\nboot_id=fake-boot-id\n')
        self.log = self.logs / 'AshReXcueSession-1.log'
        self.log.write_text(HEADER.format('◆◆◆ NEW BOOT 1 ◆◆◆'))
        self.notifier = self.root / 'fake-notify.sh'
        self.notifier.write_text('#!/bin/sh\nprintf "%s\n----\n%s\n" "$1" "$2" >> "$ARC_NOTIFY_OUTPUT"\n')
        self.notifier.chmod(0o755)
        # Make boot completion deterministic on Linux and Android/Termux alike.
        # The real stable_boot() check still validates the stock module markers.
        mock_getprop = self.root / 'getprop'
        mock_getprop.write_text(
            '#!/bin/sh\n'
            'if [ "$1" = "sys.boot_completed" ]; then printf "1\\n"; fi\n'
        )
        mock_getprop.chmod(0o755)
        self.env = dict(os.environ, PATH=f'{self.root}{os.pathsep}{os.environ.get("PATH", "")}',
                        ARC_STATE=str(self.state), ARC_LOGS=str(self.logs),
                        ARC_MODULES=str(self.mods), ARC_VAULT=str(self.vault),
                        ARC_SETTINGS=str(self.settings), ARC_SCRIPTS=str(self.scripts),
                        ARC_TEST_BOOT_ID='fake-boot-id', ARC_TEST_STABLE='yes',
                        ARC_TEST_NOTIFY=str(self.notifier), ARC_NOTIFY_OUTPUT=str(self.calls),
                        ARC_RETRY_SECONDS='0')

    def run_cmd(self, name='notify-pending', success=True, env=None):
        p = subprocess.run(['sh', str(MAIN), name], env=env or self.env,
                           cwd=self.root, capture_output=True, text=True, timeout=15)
        if success:
            self.assertEqual(0, p.returncode, p.stdout + p.stderr)
        return p

    def add_log(self, *messages):
        with self.log.open('a') as f:
            for m in messages:
                f.write(HEADER.format(m))

    def module(self, id, name=None, enabled=False, folder=None):
        path = self.mods / (folder or id)
        path.mkdir()
        (path / 'module.prop').write_text(f'id={id}\nname={name or id}\n')
        if not enabled:
            (path / 'disable').touch()
        return path

    def seed(self):
        self.run_cmd('seed')

    def test_existing_unchanged_core_and_no_old_notifications(self):
        self.module('old', 'Old module')
        self.add_log('Threshold reached - disabling new modules',
                     'Module disabled: /data/adb/modules/old')
        original_logs = self.log.read_bytes()
        original_settings = self.settings.read_bytes()
        self.seed()
        self.run_cmd()
        self.assertFalse(self.calls.exists())
        self.assertEqual(original_logs, self.log.read_bytes())
        self.assertEqual(original_settings, self.settings.read_bytes())
        self.assertTrue((self.mods / 'old' / 'disable').exists())

    def test_stock_targeted_recovery_attribution(self):
        self.seed()
        self.module('pif', 'Play Integrity Fix')
        self.add_log('◆◆◆ NEW BOOT 2 ◆◆◆', 'Threshold reached - disabling new modules',
                     'Targeting non-whitelisted modules: pif',
                     'Module disabled: /data/adb/modules/pif')
        self.run_cmd()
        body = self.calls.read_text()
        self.assertIn('Play Integrity Fix (pif)', body)
        self.assertEqual(1, body.count('Play Integrity Fix'))
        self.assertEqual(1, len(list((self.state / 'history').glob('*.tsv'))))
        self.assertIn('targeted', next((self.state / 'history').glob('*.tsv')).read_text())

    def test_stock_lockdown_names_and_service_script_vault(self):
        self.seed()
        self.module('lsp', 'LSPosed')
        (self.scripts / 'fix.sh').touch(mode=0o000)
        (self.vault / 'fix.sh.svc.755').write_text('#!/bin/sh\necho test\n')
        self.add_log('◆◆◆ NEW BOOT 3 ◆◆◆', 'Lockdown Mode Activated',
                     'Disabled module: lsp',
                     'Disabled script: /data/adb/service.d/fix.sh -> /data/adb/ashlooper/fix.sh.svc.755 (Dummy created)')
        self.run_cmd()
        body = self.calls.read_text()
        self.assertIn('LSPosed (lsp)', body)
        self.assertIn('Script: fix.sh (svc:fix.sh)', body)
        self.assertIn('lockdown', next((self.state / 'history').glob('*.tsv')).read_text())

    def test_nuclear_phase_recorded(self):
        self.seed()
        self.module('breaks', 'Module Broken')
        self.add_log('◆◆◆ NEW BOOT 4 ◆◆◆',
                     'NUKING all scripts and disabling all modules including AshLooper.',
                     'Lockdown Mode Activated', 'Disabled module: breaks')
        self.run_cmd()
        self.assertIn('nuclear', next((self.state / 'history').glob('*.tsv')).read_text())

    def test_unrelated_manual_disable_not_attributed(self):
        self.seed()
        self.module('manual', 'Manually disabled')
        self.add_log('Module disabled: /data/adb/modules/manual')
        self.run_cmd()
        self.assertFalse(self.calls.exists())

    def test_unverified_restored_event_not_notified(self):
        self.seed()
        self.module('restored', 'Restored', enabled=True)
        self.add_log('Threshold reached - disabling new modules',
                     'Module disabled: /data/adb/modules/restored')
        self.run_cmd()
        self.assertFalse(self.calls.exists())
        self.assertIn('unverified-or-restored', next((self.state / 'history').glob('*.tsv')).read_text())

    def test_old_event_does_not_repeat_after_subsequent_boot(self):
        self.seed()
        self.module('one')
        self.add_log('Threshold reached - disabling new modules',
                     'Module disabled: /data/adb/modules/one')
        self.run_cmd()
        first = self.calls.read_text()
        self.add_log('◆◆◆ NEW BOOT 3 ◆◆◆', 'Boot successful')
        self.run_cmd()
        self.assertEqual(first, self.calls.read_text())

    def test_failed_notification_leaves_queue_for_retry(self):
        self.seed()
        self.module('retry')
        self.add_log('Threshold reached - disabling new modules',
                     'Module disabled: /data/adb/modules/retry')
        fail = self.root / 'fail.sh'
        fail.write_text('#!/bin/sh\nexit 9\n')
        fail.chmod(0o755)
        e = dict(self.env, ARC_TEST_NOTIFY=str(fail))
        p = self.run_cmd(success=False, env=e)
        self.assertNotEqual(0, p.returncode)
        self.assertTrue((self.state / 'pending.tsv').exists())
        self.run_cmd()
        self.assertFalse((self.state / 'pending.tsv').exists())
        self.assertIn('retry', self.calls.read_text())

    def test_ack_after_archive_interruption_does_not_duplicate(self):
        self.seed()
        self.module('once')
        self.add_log('Threshold reached - disabling new modules',
                     'Module disabled: /data/adb/modules/once')
        self.run_cmd()
        original = self.calls.read_text()
        row = 'module\tonce\ttargeted\n'
        (self.state / 'pending.tsv').write_text(row)
        self.run_cmd()
        self.assertEqual(original, self.calls.read_text())

    def test_ambiguous_duplicate_ids_not_notified(self):
        self.seed()
        self.module('dup', 'A', folder='A')
        self.module('dup', 'B', folder='B')
        self.add_log('Threshold reached - disabling new modules',
                     'Disabled module: dup')
        self.run_cmd()
        self.assertFalse(self.calls.exists())

    def test_invalid_module_identifier_rejected(self):
        self.seed()
        self.module('safe')
        self.add_log('Threshold reached - disabling new modules',
                     'Disabled module: ../safe')
        self.run_cmd()
        self.assertFalse(self.calls.exists())

    def test_stable_boot_required(self):
        self.seed()
        self.module('stable')
        self.add_log('Threshold reached - disabling new modules',
                     'Disabled module: stable')
        # ARC_TEST_STABLE=no disables the test bypass; it does not force failure.
        # Actually simulate a boot that stock AshReXcue hasn't marked as stable.
        self.settings.write_text('boot=booting\nboot_id=fake-boot-id\n')
        e = dict(self.env, ARC_TEST_STABLE='no')
        p = self.run_cmd(success=False, env=e)
        self.assertEqual(2, p.returncode, p.stdout + p.stderr)
        self.assertFalse(self.calls.exists())
        self.assertFalse((self.state / 'pending.tsv').exists())
        self.settings.write_text('boot=booted\nboot_id=fake-boot-id\n')
        self.run_cmd(env=e)
        self.assertTrue(self.calls.exists())

    def test_stale_boot_id_blocks_notification(self):
        self.seed()
        self.module('stale')
        self.add_log('Threshold reached - disabling new modules',
                     'Disabled module: stale')
        self.settings.write_text('boot=booted\nboot_id=previous-boot-id\n')
        e = dict(self.env, ARC_TEST_STABLE='no')
        p = self.run_cmd(success=False, env=e)
        self.assertEqual(2, p.returncode, p.stdout + p.stderr)
        self.assertFalse(self.calls.exists())
        self.settings.write_text('boot=booted\nboot_id=fake-boot-id\n')
        self.run_cmd(env=e)
        self.assertIn('stale', self.calls.read_text())

    def test_disabled_original_module_blocks_notification(self):
        self.seed()
        self.module('disabled-original')
        self.add_log('Threshold reached - disabling new modules',
                     'Disabled module: disabled-original')
        marker = self.ashdir / 'disable'
        marker.touch()
        e = dict(self.env, ARC_TEST_STABLE='no')
        p = self.run_cmd(success=False, env=e)
        self.assertEqual(2, p.returncode, p.stdout + p.stderr)
        self.assertFalse(self.calls.exists())
        marker.unlink()
        self.run_cmd(env=e)
        self.assertIn('disabled-original', self.calls.read_text())

    def test_shell_injection_stays_in_data(self):
        self.seed()
        marker = self.root / 'INJECTED'
        suspect = "O'Hare $(touch INJECTED) `touch INJECTED`"
        self.module('inject', suspect)
        self.add_log('Threshold reached - disabling new modules',
                     'Disabled module: inject')
        self.run_cmd()
        self.assertIn(suspect, self.calls.read_text())
        self.assertFalse(marker.exists())
        s = MAIN.read_text()
        quote_helper = s[s.index('shell_quote() {'):s.index('\npost_notification() {')]
        script = self.root / 'quote-test.sh'
        script.write_text('#!/bin/sh\n' + quote_helper +
                          '\nencoded=$(shell_quote "$MALICIOUS")\neval "roundtrip=$encoded"\ntest "$roundtrip" = "$MALICIOUS"\n')
        hostile = f"O'Hare $(touch {marker}) `touch {marker}`"
        p = subprocess.run(['sh', str(script)], env=dict(self.env, MALICIOUS=hostile),
                           capture_output=True, text=True)
        self.assertEqual(0, p.returncode, p.stderr)
        self.assertFalse(marker.exists())

    def test_file_rotation_with_reused_filename(self):
        self.seed()
        self.module('new')
        self.log.write_text(HEADER.format('◆◆◆ NEW BOOT 11 ◆◆◆') +
                            HEADER.format('Threshold reached - disabling new modules') +
                            HEADER.format('Disabled module: new'))
        self.run_cmd()
        self.assertIn('new', self.calls.read_text())

    def test_no_writes_to_original_module_or_log_on_failure(self):
        self.seed()
        self.module('abc')
        self.add_log('Threshold reached - disabling new modules',
                     'Disabled module: abc')
        original = {str(p): p.read_bytes() for p in self.mods.rglob('*') if p.is_file()}
        original[str(self.log)] = self.log.read_bytes()
        self.run_cmd()
        self.assertTrue(all(Path(p).read_bytes() == before for p, before in original.items()))


class PackagingTests(unittest.TestCase):
    def test_companion_is_not_original_module(self):
        prop = (ROOT / 'module.prop').read_text()
        self.assertIn('id=ashrexcue_companion', prop)
        self.assertNotIn('id=AshLooper\n', prop)
        data = (ROOT / 'bin/companion.sh').read_text()
        self.assertNotIn('touch "$MODULES/', data)
        self.assertNotIn('reboot recovery', data)
        self.assertNotIn('disabled-report.pending', data)

    def test_zip_contains_no_original_core_files(self):
        # Avoid a top-level "tools" import: Termux and other environments may
        # provide an unrelated package with that name. Load our exact file.
        builder = runpy.run_path(str(ROOT / 'tools' / 'build_zip.py'),
                                 run_name='ashrexcue_companion_build_zip_test')
        build, FILES = builder['build'], builder['FILES']
        with tempfile.TemporaryDirectory() as p:
            a = Path(p) / 'a.zip'
            b = Path(p) / 'b.zip'
            build(a)
            build(b)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            with zipfile.ZipFile(a) as z:
                self.assertEqual(set(FILES), set(z.namelist()))
                self.assertNotIn('utils.sh', z.namelist())
                self.assertNotIn('post-fs-data.sh', z.namelist())
                self.assertNotIn('settings.prop', z.namelist())
                self.assertIn('bin/parse-recovery.awk', z.namelist())

    def test_installer_seeds_log_baseline_without_core_mutations(self):
        installer = (ROOT / 'customize.sh').read_text()
        self.assertIn('seed', installer)
        self.assertNotIn('rm -rf /data/adb/ashlooper', installer)
        self.assertNotIn('git push', installer)
        self.assertNotIn('reboot recovery', installer)
        self.assertNotIn('reboot -', installer)


if __name__ == '__main__':
    unittest.main(verbosity=2)
