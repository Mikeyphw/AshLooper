#!/usr/bin/env python3
"""Deterministic standalone module candidate, never bundles AshLooper core."""
from pathlib import Path
import argparse
import hashlib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    'module.prop',
    'service.sh',
    'action.sh',
    'customize.sh',
    'uninstall.sh',
    'bin/companion.sh',
    'bin/parse-recovery.awk',
    'bin/synthetic-test.sh',
)
BLOCKED = {'utils.sh', 'post-fs-data.sh', 'recovery-notify.sh', 'settings.prop'}


def build(target: Path):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as zf:
        for file in FILES:
            if file in BLOCKED:
                raise ValueError('Core file included in standalone companion')
            source = ROOT / file
            if not source.is_file():
                raise FileNotFoundError(source)
            info = zipfile.ZipInfo(file, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = ((0o100755 if file.endswith('.sh') else 0o100644) << 16)
            zf.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED,
                        compresslevel=9)
    with zipfile.ZipFile(target) as check:
        if set(check.namelist()) != set(FILES) or check.testzip() is not None:
            raise ValueError('Build inventory/corruption mismatch')
    print(f'RF04_CANDIDATE_SHA256 {hashlib.sha256(target.read_bytes()).hexdigest()}')
    print(f'RF04_CANDIDATE_PATH {target}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    build(parser.parse_args().out)
