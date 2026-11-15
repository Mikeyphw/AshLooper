#!/usr/bin/env python3
"""RF02 offline acceptance: no root commands, no module changes, no reboot."""
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ENTRY = ROOT / 'companion/bin/companion.sh'


class CompanionRF02Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)
        self.source = self.d / 'ashlooper'
        self.mods = self.d / 'modules'
        self.state = self.d / 'state'
        for path in (self.source, self.mods, self.state):
            path.mkdir()
        self.pending = self.source / 'disabled-report.pending'
        self.calls = self.d / 'notifications.txt'
        self.notifier = self.d / 'fake-notify.sh'
        self.notifier.write_text('#!/bin/sh\nprintf "%s\\n----\\n%s\\n" "$1" "$2" >> "$ARC_NOTIFY_OUTPUT"\n')
        self.notifier.chmod(0o755)
        self.env = dict(os.environ, ARC_SOURCE=str(self.source), ARC_MODULES=str(self.mods),
                        ARC_STATE=str(self.state), ARC_TEST_BOOT_ID='boot-acceptance-001',
                        ARC_TEST_STABLE='yes', ARC_TEST_NOTIFY=str(self.notifier),
                        ARC_NOTIFY_OUTPUT=str(self.calls), ARC_RETRY_SECONDS='0')

    def module(self, identifier, name, disabled=True, folder=None):
        folder = folder or identifier
        path = self.mods / folder
        path.mkdir()
        (path / 'module.prop').write_text(f'id={identifier}\nname={name}\n')
        if disabled:
            (path / 'disable').touch()
        return path

    def run_command(self, command='notify-pending', env=None, ok=True):
        proc = subprocess.run(['sh', str(ENTRY), command], env=env or self.env,
                              cwd=self.d, capture_output=True, text=True, timeout=15)
        if ok:
            self.assertEqual(proc.returncode, 0, proc.stdout + '\n' + proc.stderr)
        return proc

    def pending_rows(self, *rows):
        self.pending.write_text(''.join('\t'.join(item) + '\n' for item in rows))

    def test_module_notification_history_and_archive(self):
        self.module('lsposed', 'LSPosed')
        self.module('pif', 'Play Integrity Fix')
        self.pending_rows(('module','lsposed','LSPosed'),('module','pif','Play Integrity Fix'))
        self.run_command()
        body = self.calls.read_text()
        self.assertIn('2 item(s) disabled', body)
        self.assertIn('LSPosed (lsposed)', body)
        self.assertIn('Play Integrity Fix (pif)', body)
        self.assertFalse(self.pending.exists())
        self.assertEqual(1, len(list((self.state / 'history').glob('*.tsv'))))
        self.assertTrue((self.source / 'disabled-report.last').exists())

    def test_enabled_or_unrelated_module_not_claimed(self):
        self.module('manual', 'Manually disabled', True)
        self.module('restored', 'Was restored', False)
        self.pending_rows(('module','restored','Was restored'))
        self.run_command()
        self.assertFalse(self.calls.exists())
        self.assertIn('unverified-or-restored', next((self.state / 'history').glob('*.tsv')).read_text())
        self.assertTrue((self.source / 'disabled-report.last').exists())
        self.assertNotIn('manual', next((self.state / 'history').glob('*.tsv')).read_text())

    def test_failed_post_preserves_source_report_for_retry(self):
        self.module('good', 'Good Module')
        self.pending_rows(('module','good','Good Module'))
        failure = self.d / 'fail.sh'
        failure.write_text('#!/bin/sh\nexit 7\n')
        failure.chmod(0o755)
        env = dict(self.env, ARC_TEST_NOTIFY=str(failure))
        p = self.run_command(env=env, ok=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertTrue(self.pending.exists())
        self.run_command()
        self.assertFalse(self.pending.exists())
        self.assertTrue(self.calls.exists())

    def test_acknowledged_delivery_skips_repost_after_archive_interruption(self):
        self.module('safe', 'Safe')
        self.pending_rows(('module', 'safe', 'Safe'))
        self.run_command()
        self.assertEqual(1, self.calls.read_text().count('Safe (safe)'))
        source_copy = (self.source / 'disabled-report.last').read_bytes()
        self.pending.write_bytes(source_copy)
        self.run_command()
        self.assertEqual(1, self.calls.read_text().count('Safe (safe)'))
        self.assertFalse(self.pending.exists())

    def test_script_vault_verified(self):
        (self.source / 'fixup.sh.svc.755').write_text('#!/bin/sh\nexit 0\n')
        self.pending_rows(('script','svc:fixup.sh','fixup.sh'))
        self.run_command()
        self.assertIn('Script: fixup.sh', self.calls.read_text())

    def test_stable_boot_is_required(self):
        self.module('safe', 'Safe')
        self.pending_rows(('module', 'safe', 'Safe'))
        env = dict(self.env, ARC_TEST_STABLE='no')
        p = self.run_command(env=env, ok=False)
        self.assertEqual(2, p.returncode)
        self.assertTrue(self.pending.exists())
        self.assertFalse(self.calls.exists())

    def test_module_name_is_data_not_a_command(self):
        # Use a short relative path so both shell-like payloads fit within
        # the companion's intentional 90-character notification-name limit.
        # run_command executes with cwd=self.d; a vulnerable shell would write
        # INJECTED in that directory regardless of the system's TMPDIR length.
        marker = self.d / 'INJECTED'
        suspicious = "O'Hare $(touch INJECTED) `touch INJECTED`"
        self.module('danger', suspicious)
        self.pending_rows(('module', 'danger', suspicious))
        self.run_command()
        self.assertIn(suspicious, self.calls.read_text())
        self.assertFalse(marker.exists())

    def test_long_malicious_module_name_is_safely_truncated(self):
        marker = self.d / 'LONG_INJECTED'
        # The trailing padding guarantees this remains over 90 characters
        # even on a host with short temporary paths.
        suspicious = f"O'Hare $(touch {marker}) `touch {marker}` " + ('X' * 100)
        self.assertGreater(len(suspicious), 90)
        self.module('danger', suspicious)
        self.pending_rows(('module', 'danger', suspicious))
        self.run_command()
        notification = self.calls.read_text()
        self.assertIn(suspicious[:90], notification)
        self.assertNotIn(suspicious, notification)
        self.assertFalse(marker.exists())
        # The original source journal is not modified while formatting.
        self.assertIn(suspicious, (self.source / 'disabled-report.last').read_text())

    def test_rejects_pathlike_module_identifier(self):
        self.module('valid', 'Valid')
        self.pending_rows(('module', '../valid', 'Traversal'))
        self.run_command()
        self.assertFalse(self.calls.exists())

    def test_duplicate_items_show_once(self):
        self.module('same', 'Same')
        self.pending_rows(('module', 'same', 'Same'), ('module', 'same', 'Same'))
        self.run_command()
        self.assertEqual(1, self.calls.read_text().count('Same (same)'))

    def test_alternate_directory_id_resolved_by_prop(self):
        self.module('actual.id', 'Friendly', folder='different.folder')
        self.pending_rows(('module', 'actual.id', 'Friendly'))
        self.run_command()
        self.assertIn('Friendly (actual.id)', self.calls.read_text())

    def test_duplicate_claimed_module_id_is_not_attributed(self):
        self.module('same.id', 'First', folder='first.folder')
        self.module('same.id', 'Second', folder='second.folder')
        self.pending_rows(('module', 'same.id', 'Ambiguous'))
        self.run_command()
        self.assertFalse(self.calls.exists())
        self.assertIn('unverified-or-restored', next((self.state / 'history').glob('*.tsv')).read_text())

    def test_shell_quote_roundtrip_blocks_nested_shell_injection(self):
        # Exercise the exact quote helper in a real shell.
        source = ENTRY.read_text()
        func = source[source.index('shell_quote() {'):source.index('\npost_notification() {')]
        driver = self.d / 'quote-test.sh'
        driver.write_text('#!/bin/sh\n' + func + '\nencoded=$(shell_quote "$MALICIOUS")\neval "roundtrip=$encoded"\ntest "$roundtrip" = "$MALICIOUS"\n')
        marker = self.d / 'MUST_NOT_EXECUTE'
        malicious = f"O'Hare $(touch {marker}) `touch {marker}`"
        proc = subprocess.run(['sh', str(driver)], env=dict(self.env, MALICIOUS=malicious),
                              capture_output=True, text=True)
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertFalse(marker.exists())

    def test_fork_workflow_cannot_force_push_upstream(self):
        workflow = (ROOT / '.github/workflows/sync.yml').read_text()
        self.assertNotIn('git push', workflow)
        self.assertNotIn('RipperHybrid/AshLooper.git', workflow)
        self.assertNotIn('secrets.', workflow)
        self.assertIn('recovery-notify.sh', workflow)
        self.assertIn('actions/upload-artifact', workflow)

    def test_package_reproducible_and_runtime_only(self):
        from companion.tools.build_zip import build
        a, b = self.d / 'a.zip', self.d / 'b.zip'
        build(a); build(b)
        self.assertEqual(a.read_bytes(), b.read_bytes())
        with zipfile.ZipFile(a) as z:
            self.assertIn('bin/companion.sh', z.namelist())
            self.assertIn('service.sh', z.namelist())
            self.assertNotIn('tests/test_companion_rf02.py', z.namelist())

    def test_handoff_replacement_has_guardrails(self):
        from scripts.apply_refurbish import BEFORE, AFTER, MARKER, SERVICE_BLOB, PIN
        self.assertIn('recovery-notify.sh', BEFORE)
        self.assertIn(MARKER, AFTER)
        self.assertIn('ashrexcue_companion', AFTER)
        self.assertIn('recovery-notify.sh', AFTER)
        self.assertEqual(len(PIN), 40)
        self.assertEqual(len(SERVICE_BLOB), 40)


if __name__ == '__main__':
    unittest.main(verbosity=2)

class OverlayRF02Tests(unittest.TestCase):
    """Apply overlay to a temporary Git repo using exact synthetic source pins."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / 'repo'
        self.repo.mkdir()
        (self.repo / '.github/workflows').mkdir(parents=True)
        from scripts import apply_refurbish as patcher
        self.patcher = patcher
        (self.repo / 'service.sh').write_text('#!/system/bin/sh\n' + patcher.BEFORE)
        (self.repo / 'module.prop').write_text('id=AshLooper\nupdateJson=https://old.example/test.json\n')
        (self.repo / 'README.md').write_text('# AshReXcue - Bootloop Protector\n\nProject.\n')
        (self.repo / '.github/workflows/sync.yml').write_text('name: unsafe-old-upstream-sync\n')
        subprocess.run(['git', 'init', '-q', '-b', 'Master', str(self.repo)], check=True)
        subprocess.run(['git', '-C', str(self.repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=test', '-c',
                        'user.email=test@example.invalid', 'commit', '-qm', 'baseline'], check=True)
        self.original_pins = (patcher.PIN, patcher.SERVICE_BLOB, patcher.WORKFLOW_BLOB,
                              patcher.MODULE_BLOB, patcher.README_BLOB)
        patcher.PIN = patcher.git(self.repo, 'rev-parse', 'HEAD')
        patcher.SERVICE_BLOB = patcher.git(self.repo, 'hash-object', 'service.sh')
        patcher.WORKFLOW_BLOB = patcher.git(self.repo, 'hash-object', '.github/workflows/sync.yml')
        patcher.MODULE_BLOB = patcher.git(self.repo, 'hash-object', 'module.prop')
        patcher.README_BLOB = patcher.git(self.repo, 'hash-object', 'README.md')
        self.addCleanup(self.restore_pins)

    def restore_pins(self):
        p = self.patcher
        p.PIN, p.SERVICE_BLOB, p.WORKFLOW_BLOB, p.MODULE_BLOB, p.README_BLOB = self.original_pins

    def test_dry_run_apply_and_idempotent_reapply(self):
        before = (self.repo / 'service.sh').read_bytes()
        self.patcher.overlay(ROOT, self.repo, apply=False)
        self.assertEqual(before, (self.repo / 'service.sh').read_bytes())
        self.patcher.overlay(ROOT, self.repo, apply=True)
        self.assertIn(self.patcher.MARKER, (self.repo / 'service.sh').read_text())
        self.assertIn('recovery-notify.sh', (self.repo / 'service.sh').read_text())
        self.assertFalse('updateJson' in (self.repo / 'module.prop').read_text())
        self.assertFalse('git push' in (self.repo / '.github/workflows/sync.yml').read_text())
        self.assertTrue((self.repo / 'companion/tools/build_zip.py').is_file())
        self.patcher.overlay(ROOT, self.repo, apply=True)
        self.assertEqual(1, (self.repo / 'service.sh').read_text().count(self.patcher.MARKER))
        self.assertEqual(1, (self.repo / 'README.md').read_text().count('**Independent fork:**'))

    def test_mutated_protected_source_refused_without_writes(self):
        (self.repo / 'service.sh').write_text('modified protected source')
        with self.assertRaisesRegex(ValueError, 'Source changed'):
            self.patcher.overlay(ROOT, self.repo, apply=True)
        self.assertFalse((self.repo / 'companion').exists())

    def test_mismatched_repo_head_refused(self):
        self.patcher.PIN = '0' * 40
        with self.assertRaisesRegex(ValueError, 'Unexpected HEAD'):
            self.patcher.overlay(ROOT, self.repo, apply=False)
