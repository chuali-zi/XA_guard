'''Create a secret-free manifest for every file tracked by a clean release commit.'''

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / '.runtime' / 'evidence' / 'release-manifest.json'


def git(*args: str) -> str:
    completed = subprocess.run(
        ['git', *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return completed.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    dirty = git('status', '--porcelain=v1', '--untracked-files=all')
    if dirty:
        raise SystemExit('release manifest requires a clean worktree')
    names = [name for name in git('ls-files').splitlines() if name]
    files = []
    for name in names:
        path = ROOT / name
        if not path.is_file():
            raise SystemExit(f'tracked release file is absent: {name}')
        files.append({'path': name.replace('\\', '/'), 'size': path.stat().st_size, 'sha256': sha256(path)})
    manifest = {
        'schema': 'xa-guard-release-manifest/v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'git_commit': git('rev-parse', 'HEAD'),
        'git_branch': git('branch', '--show-current'),
        'tracked_file_count': len(files),
        'files': files,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'passed', 'output': str(args.output.resolve()), 'tracked_file_count': len(files)}, sort_keys=True))


if __name__ == '__main__':
    main()
