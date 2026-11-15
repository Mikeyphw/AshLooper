#!/usr/bin/env python3
"""Source-pinned RF02 overlay. No Git writes, module installs, or reboots."""
from argparse import ArgumentParser
from pathlib import Path
import os
import subprocess
import sys

PIN = '276c071181711ba4f7a6f35fef4ea66eb4481cee'
SERVICE_BLOB = '042c9684496be931d5ebc561c82bcc02685c67ad'
WORKFLOW_BLOB = 'b25a0d5c04bd3fab86be1c60afc8a85ba302375a'
MODULE_BLOB = '9c3b3f2a2dc7663b4dceda4f4e8f57ffd161b0ff'
README_BLOB = '5bda3059a5f4b9ba74353094767d1d5d17f84d7b'
MARKER = '# ARC_COMPANION_RF02_HANDOFF'
BEFORE = '''# Deliver only after a stable Android boot. Pending data survives reboot and
# failed notification attempts, and is not affected by the settings reset.
if [ -s "$ASHLOOPER_DIR/disabled-report.pending" ]; then
    if /system/bin/sh "$MODPATH/recovery-notify.sh" send; then
        log "Android recovery notification delivered; report archived."
    else
        log "Android recovery notification failed; report retained for next boot."
    fi
fi
'''
AFTER = '''# Deliver only after stable boot. If the independent companion is enabled,
# hand over notification ownership without changing boot recovery behavior.
''' + MARKER + '''
if [ -s "$ASHLOOPER_DIR/disabled-report.pending" ]; then
    arc_companion="/data/adb/modules/ashrexcue_companion"
    if [ -d "$arc_companion" ] && [ ! -f "$arc_companion/disable" ] && [ -f "$arc_companion/service.sh" ]; then
        log "AshReXcue Companion enabled; retaining pending report for companion delivery."
    elif /system/bin/sh "$MODPATH/recovery-notify.sh" send; then
        log "Android recovery notification delivered; report archived."
    else
        log "Android recovery notification failed; report retained for next boot."
    fi
fi
'''
ADDITIONS = [
    'companion/module.prop',
    'companion/service.sh',
    'companion/action.sh',
    'companion/customize.sh',
    'companion/uninstall.sh',
    'companion/bin/companion.sh',
    'companion/tools/build_zip.py',
    'docs/COMPANION.md',
    'tests/test_companion_rf02.py',
    '.github/workflows/companion-ci.yml',
    'docs/FORK_MAINTENANCE.md',
    '.gitignore',
    'scripts/apply_refurbish.py',
]


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def overlay(root, repo, apply=False):
    repo = repo.resolve()
    if not (repo / '.git').exists():
        raise ValueError('Not a Git working tree')
    head = git(repo, 'rev-parse', 'HEAD')
    if head != PIN:
        raise ValueError(f'Unexpected HEAD {head}. Expected exact {PIN}; regenerate overlay for changed source.')
    service = repo / 'service.sh'
    source = service.read_text(encoding='utf-8')
    if MARKER in source:
        patched = source
    else:
        blob = git(repo, 'hash-object', 'service.sh')
        if blob != SERVICE_BLOB or source.count(BEFORE) != 1:
            raise ValueError(f'Source changed: service.sh blob {blob} (wanted {SERVICE_BLOB})')
        patched = source.replace(BEFORE, AFTER)
    replacements = {
        '.github/workflows/sync.yml': (WORKFLOW_BLOB, (root / '.github/workflows/sync.yml').read_text()),
    }
    # Prevent root-manager updates from silently swapping fork builds for upstream.
    module = (repo / 'module.prop').read_text()
    module_new = '\n'.join(line for line in module.splitlines() if not line.startswith('updateJson=')) + '\n'
    replacements['module.prop'] = (MODULE_BLOB, module_new)
    readme = (repo / 'README.md').read_text()
    fork_notice = (
        '> **Independent fork:** maintained at [Mikeyphw/AshLooper](https://github.com/Mikeyphw/AshLooper). '
        'Original project by [AshBorn / RipperHybrid](https://github.com/RipperHybrid/AshLooper). '
        'See [companion module](docs/COMPANION.md) and '
        '[fork maintenance notes](docs/FORK_MAINTENANCE.md).\n\n'
    )
    if fork_notice in readme:
        readme_new = readme
    else:
        readme_new = readme.replace('# AshReXcue - Bootloop Protector\n\n',
                                    '# AshReXcue - Bootloop Protector\n\n' + fork_notice, 1)
        if readme_new == readme:
            raise ValueError('README header not found; refusing to change unknown source')
    replacements['README.md'] = (README_BLOB, readme_new)
    for rel, (expected_blob, target_text) in replacements.items():
        actual_blob = git(repo, 'hash-object', rel)
        current_text = (repo / rel).read_text()
        if current_text != target_text and actual_blob != expected_blob:
            raise ValueError(f'{rel} changed (blob {actual_blob}); expected {expected_blob}')
    for rel in ADDITIONS:
        src = root / rel
        dst = repo / rel
        if not src.is_file() or src.is_symlink():
            raise ValueError(f'Missing overlay source: {rel}')
        if dst.exists() and dst.read_bytes() != src.read_bytes():
            raise ValueError(f'Conflicting destination file: {rel}')
    if apply:
        # Stage all writes before replacing paths. Roll back any partial mutation
        # when an I/O failure interrupts the transaction.
        changes = [('service.sh', patched.encode('utf-8'), None)]
        changes.extend((rel, value.encode('utf-8'), None) for rel, (_, value) in replacements.items())
        changes.extend((rel, (root / rel).read_bytes(), (root / rel).stat().st_mode & 0o777)
                       for rel in ADDITIONS)
        originals = {}
        written = []
        for rel, contents, mode in changes:
            dest = repo / rel
            if dest.is_symlink() or (dest.exists() and not dest.is_file()):
                raise ValueError(f'Refusing nonregular target: {rel}')
            originals[rel] = (dest.read_bytes(), dest.stat().st_mode & 0o777) if dest.exists() else None
        try:
            for rel, contents, mode in changes:
                dest = repo / rel
                if originals[rel] is not None and originals[rel][0] == contents:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                temporary = dest.with_name(dest.name + f'.rf02.tmp.{os.getpid()}')
                try:
                    with temporary.open('wb') as fp:
                        fp.write(contents)
                        fp.flush()
                        os.fsync(fp.fileno())
                    os.chmod(temporary, mode if mode is not None else
                             (originals[rel][1] if originals[rel] is not None else 0o644))
                    os.replace(temporary, dest)
                    written.append(rel)
                finally:
                    temporary.unlink(missing_ok=True)
        except OSError:
            for rel in reversed(written):
                dest = repo / rel
                saved = originals[rel]
                if saved is None:
                    dest.unlink(missing_ok=True)
                else:
                    dest.write_bytes(saved[0])
                    os.chmod(dest, saved[1])
            raise
        print('RF02_OVERLAY_APPLIED: 13 additions, 3 guarded replacements and source-pinned handoff')
    else:
        print('RF02_OVERLAY_VALIDATED_NO_WRITES')


def main():
    parser = ArgumentParser()
    parser.add_argument('repo', type=Path)
    parser.add_argument('--apply', action='store_true', help='Write changes (default: check only)')
    args = parser.parse_args()
    try:
        overlay(Path(__file__).resolve().parents[1], args.repo, args.apply)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f'RF02_REFUSED: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
