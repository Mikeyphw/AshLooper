#!/usr/bin/env python3
"""Reproducible root-module ZIP. Explicit allowlist excludes tests and repository files."""
from argparse import ArgumentParser
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (
    'module.prop', 'service.sh', 'action.sh', 'customize.sh',
    'uninstall.sh', 'bin/companion.sh',
)


def build(destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, 'w') as archive:
        for rel in RUNTIME:
            source = ROOT / rel
            if not source.is_file() or source.is_symlink():
                raise SystemExit(f'Missing or symlink module file: {rel}')
            info = ZipInfo(rel, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = ((0o100755 if rel.endswith('.sh') else 0o100644) << 16)
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, source.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    build(args.out)
    print(f'Built {args.out} ({args.out.stat().st_size} bytes)')
