#!/usr/bin/env python3
"""Outbound-only CD for one public repository. No credentials or PR jobs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = 'Infibiss/b2b-debitorka'
API = 'https://api.github.com/repos/' + REPOSITORY
WORKFLOW = '.github/workflows/ci.yml'


def validate_sha(value):
    if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{40}', value):
        raise ValueError('Invalid immutable revision')
    return value


def approved(run, sha, workflow_id):
    return isinstance(run, dict) and all((
        run.get('head_sha') == sha, run.get('head_branch') == 'main',
        run.get('event') == 'push', run.get('status') == 'completed',
        run.get('conclusion') == 'success', run.get('workflow_id') == workflow_id,
        run.get('path') == WORKFLOW,
        isinstance(run.get('head_repository'), dict) and
        run['head_repository'].get('full_name') == REPOSITORY,
    ))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Repository redirect refused')


def request(path):
    req = urllib.request.Request(API + path, headers={
        'Accept': 'application/vnd.github+json', 'User-Agent': 'Mandato-Pull-CD',
        'X-GitHub-Api-Version': '2022-11-28'})
    with urllib.request.build_opener(NoRedirect).open(req, timeout=25) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError('Oversized API response')
    return json.loads(raw)


class Controller:
    def __init__(self, directory, origin, public_ip, release_script):
        self.directory = Path(directory)
        self.state = self.directory / 'state.json'
        self.origin, self.public_ip = origin, public_ip
        self.release_script = Path(release_script)
        self.dry_run = False

    def load(self):
        return json.loads(self.state.read_text()) if self.state.exists() else {}

    def save(self, data):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self.state.with_suffix('.tmp')
        fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as handle:
            json.dump(data, handle)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(self.state)

    def head(self):
        return validate_sha(request('/git/ref/heads/main')['object']['sha'])

    def current(self):
        path = Path('/opt/agentpay/current')
        return path.resolve().name if path.is_symlink() else None

    def eligible(self, sha):
        validate_sha(sha)
        workflow = request('/actions/workflows/ci.yml')
        if (workflow.get('path') != WORKFLOW or workflow.get('state') != 'active'
                or type(workflow.get('id')) is not int):
            return False
        query = urllib.parse.urlencode(dict(head_sha=sha, branch='main', event='push', status='success', per_page=10))
        runs = request('/actions/workflows/ci.yml/runs?' + query)
        return any(approved(run, sha, workflow['id']) for run in runs.get('workflow_runs', []))

    def guard(self, sha):
        return self.head() == validate_sha(sha) and self.eligible(sha)

    def tick(self):
        if Path('/opt/agentpay/deploy-needs-operator').exists():
            return 'operator_required'
        state = self.load()
        if state.get('next_check', 0) > time.time():
            return 'backoff'
        sha = self.head()
        if sha == self.current():
            return 'current'
        if sha == state.get('failed_sha'):
            return 'failed_revision'
        if not self.eligible(sha):
            return 'awaiting_ci'
        if self.head() != sha:
            return 'superseded'
        if self.dry_run:
            return 'eligible_dry_run'
        # Latch before any build: crash/timeout cannot create an infinite retry loop.
        self.save({'failed_sha': sha, 'status': 'deploying', 'at': time.time()})
        self.deploy(sha)
        self.save({'last_success': sha, 'status': 'healthy', 'at': time.time()})
        return 'deployed'

    def deploy(self, sha):
        validate_sha(sha)
        if shutil.disk_usage(self.directory).free < 3 * 1024**3:
            raise RuntimeError('Insufficient disk space for safe build and backup')
        cache = self.directory / 'repository.git'
        env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GIT_CONFIG_NOSYSTEM': '1',
               'GIT_CONFIG_GLOBAL': os.devnull}
        def git(*args):
            return subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', *map(str, args)],
                                  check=True, timeout=180, env=env)
        if not cache.exists():
            git('init', '--bare', cache)
        git('--git-dir', cache, 'fetch', '--no-tags', '--depth=1',
            'https://github.com/' + REPOSITORY + '.git', sha)
        archive = Path('/opt/agentpay/incoming') / (sha + '.tar')
        partial = archive.with_suffix('.partial')
        with partial.open('wb') as handle:
            subprocess.run(['git', '--git-dir', str(cache), 'archive', '--format=tar', sha],
                           stdout=handle, check=True, timeout=120, env=env)
        partial.replace(archive)
        with archive.open('rb') as handle:
            checksum = hashlib.file_digest(handle, 'sha256').hexdigest()
        subprocess.run(['bash', str(self.release_script), sha, checksum, self.public_ip, self.origin],
                       check=True, timeout=2100,
                       env={**env, 'AGENTPAY_CD_GUARD': str(Path(__file__).resolve())}, stdin=subprocess.DEVNULL)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=Path('/var/lib/agentpay-cd'))
    parser.add_argument('--release-script', type=Path, default=Path('/usr/local/lib/agentpay-cd/deploy_release.sh'))
    parser.add_argument('--public-ip', default='158.160.164.25')
    parser.add_argument('--public-url', default='https://mandato.ru')
    parser.add_argument('--guard')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--retry-failed', action='store_true')
    args = parser.parse_args()
    ctl = Controller(args.state_dir, args.public_url, args.public_ip, args.release_script)
    if args.guard:
        # A separate process is invoked by the locked release script before stopping the old app.
        return 0 if ctl.guard(args.guard) else 1
    import fcntl  # Linux service only; pure policy is testable on other platforms.
    ctl.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (ctl.directory / 'poll.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another CD check is running')
            return 0
        if args.retry_failed:
            state = ctl.load()
            state.pop('failed_sha', None)
            state.pop('next_check', None)
            ctl.save(state)
        ctl.dry_run = args.dry_run
        try:
            print('Mandato CD:', ctl.tick(), flush=True)
            return 0
        except Exception as error:
            state = ctl.load()
            # Also backs off on GitHub rate limits and transient API/transport errors.
            state['next_check'] = time.time() + 900
            ctl.save(state)
            print('Mandato CD stopped safely:', type(error).__name__, file=sys.stderr, flush=True)
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
