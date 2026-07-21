'''Run the reproducible D2 release checks without silently accepting missing tools.'''

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime' / 'evidence' / 'release-verification'
SANDBOX_IMAGE = 'xa-guard/sandbox:latest'


class ReleaseVerificationError(RuntimeError):
    pass


def run(command: Sequence[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> str:
    print('+ ' + subprocess.list2cmdline(list(command)), flush=True)
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(completed.stdout, end='')
    if completed.returncode != 0:
        raise ReleaseVerificationError(
            f'command failed with exit code {completed.returncode}: {command[0]}'
        )
    return completed.stdout


def executable(name: str) -> str:
    value = shutil.which(name)
    if not value:
        raise ReleaseVerificationError(f'required executable is unavailable: {name}')
    return value


def resolve_helm(env: dict[str, str]) -> str:
    configured = env.get('HELM_BIN', '')
    if configured and Path(configured).is_file():
        return configured
    discovered = shutil.which('helm')
    if discovered:
        return discovered
    suffix = '.exe' if os.name == 'nt' else ''
    locked = ROOT / 'deploy' / 'kind' / '.tools' / 'bin' / f'helm{suffix}'
    if not locked.is_file():
        run([sys.executable, 'deploy/kind/bootstrap_tools.py'])
    if not locked.is_file():
        raise ReleaseVerificationError('locked Helm bootstrap did not create HELM_BIN')
    return str(locked)


def ensure_sandbox_image(env: dict[str, str]) -> None:
    docker = executable('docker')
    run([docker, 'info'], env=env)
    inspected = subprocess.run(
        [docker, 'image', 'inspect', SANDBOX_IMAGE],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if inspected.returncode != 0:
        run(
            [docker, 'build', '-f', 'docker/sandbox.Dockerfile', '-t', SANDBOX_IMAGE, '.'],
            env=env,
        )


def verify_pytest(env: dict[str, str]) -> dict[str, object]:
    junit = RUNTIME / 'pytest-junit.xml'
    run(
        [
            sys.executable,
            '-m',
            'pytest',
            '-q',
            '-p',
            'no:cacheprovider',
            '--junitxml',
            str(junit),
        ],
        env=env,
    )
    root = ET.parse(junit).getroot()
    suite = root if root.tag == 'testsuite' else root.find('testsuite')
    if suite is None:
        raise ReleaseVerificationError('pytest JUnit output contains no testsuite')
    skipped = []
    for case in suite.iter('testcase'):
        marker = case.find('skipped')
        if marker is not None:
            skipped.append(
                {
                    'class': case.attrib.get('classname', ''),
                    'name': case.attrib.get('name', ''),
                    'message': marker.attrib.get('message', '') or marker.text or '',
                }
            )
    unexpected = skipped
    if platform.system() == 'Windows':
        unexpected = [
            item for item in skipped if 'directory symlinks are unavailable' not in item['message']
        ]
    if unexpected:
        raise ReleaseVerificationError(
            'pytest skipped checks other than the documented Windows symlink capability: '
            + json.dumps(unexpected, ensure_ascii=False)
        )
    return {
        'tests': int(suite.attrib.get('tests', '0')),
        'failures': int(suite.attrib.get('failures', '0')),
        'errors': int(suite.attrib.get('errors', '0')),
        'skipped': len(skipped),
        'allowed_skips': skipped,
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument(
        '--evidence-bundle',
        type=Path,
        default=ROOT / 'docs' / 'evidence' / 'agent-identity-undo-acceptance-2026-07-16',
    )
    return value


def main() -> None:
    args = parser().parse_args()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env['TEMP'] = str(RUNTIME)
    env['TMP'] = str(RUNTIME)
    env['PYTHONUTF8'] = '1'
    env['HELM_BIN'] = resolve_helm(env)
    ensure_sandbox_image(env)

    run([sys.executable, '-m', 'pip', 'check'], env=env)
    run(
        [
            sys.executable,
            '-m',
            'ruff',
            'check',
            'src',
            'bench',
            'demo',
            'scripts',
            'tools',
            'enterprise-agent-range/range_src',
            'open-agent-range/kernel',
            '--exclude',
            'tests',
        ],
        env=env,
    )
    pytest_result = verify_pytest(env)
    run([sys.executable, 'scripts/verify_l3_static.py', '--section', 'all'], env=env)
    run([executable('docker'), 'compose', 'config', '--quiet'], env=env)
    npm = executable('npm.cmd' if os.name == 'nt' else 'npm')
    run([npm, 'test'], cwd=ROOT / 'console', env=env)
    run([npm, 'run', 'build'], cwd=ROOT / 'console', env=env)

    if not args.evidence_bundle.is_dir():
        raise ReleaseVerificationError(f'evidence bundle is absent: {args.evidence_bundle}')
    run(
        [
            sys.executable,
            'scripts/verify_identity_undo_evidence.py',
            '--bundle',
            str(args.evidence_bundle),
            '--expected-key-id',
            '87ca0b5c56dc9313',
        ],
        env=env,
    )
    summary = {
        'schema': 'xa-guard-release-verification/v1',
        'status': 'passed',
        'helm_bin': env['HELM_BIN'],
        'sandbox_image': SANDBOX_IMAGE,
        'pytest': pytest_result,
        'evidence_bundle': str(args.evidence_bundle.resolve()),
    }
    output = RUNTIME / 'summary.json'
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, ReleaseVerificationError) as exc:
        raise SystemExit(f'RELEASE VERIFICATION FAILED: {exc}') from None
