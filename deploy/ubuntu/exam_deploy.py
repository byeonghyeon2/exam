"""Fixed-target deployment controller. Only this installed file runs as root.

Repository code executes as exam-build without production environment variables.
No HTTP interface, arbitrary refs, shell commands, or automatic DB migrations.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass
from typing import Any
import urllib.request
import uuid


@dataclass(frozen=True)
class Config:
    source: Path = Path('/opt/apps/exam')
    releases: Path = Path('/opt/apps/exam-releases')
    current: Path = Path('/opt/apps/exam-current')
    web: Path = Path('/var/www/apps/exam/current')
    state: Path = Path('/var/lib/exam-deploy')
    build_home: Path = Path('/var/lib/exam-build')
    lock: Path = Path('/var/lib/exam-deploy/deploy.lock')
    mysql_config: Path = Path('/etc/exam/mysql-backup.cnf')
    repository: str = 'https://github.com/byeonghyeon2/exam.git'
    build_user: str = 'exam-build'
    operator: str = 'bhadmin'


class DeploymentError(Exception):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def atomic_link(link: Path, target: Path) -> None:
    if link.exists() and not link.is_symlink():
        raise DeploymentError(f'Refusing non-symlink: {link}')
    temporary = link.with_name(link.name + '.deploy-' + uuid.uuid4().hex)
    temporary.symlink_to(target)
    try:
        os.replace(temporary, link)
    finally:
        temporary.unlink(missing_ok=True)


def migration_hashes(root: Path) -> dict[str, str]:
    directory = root / 'backend/alembic/versions'
    if directory.is_symlink() or any(p.is_symlink() for p in directory.glob('*.py')):
        raise DeploymentError('Migration paths must not be symbolic links', 20)
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.glob('*.py') if p.name != '__init__.py'}


def unpack_archive(archive: Path, destination: Path) -> None:
    # Git source must never introduce absolute paths, links, device nodes or secrets.
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            parts = Path(member.name).parts
            if (not parts or member.name.startswith('/') or '..' in parts
                    or any(p == '.git' or p == '.env' or
                           (p.startswith('.env.') and not p.endswith('.example')) for p in parts)
                    or not (member.isfile() or member.isdir())):
                raise DeploymentError('Unsafe or secret-bearing source archive entry')
        source.extractall(destination, filter='data')


class Deployment:
    def __init__(self, config: Config):
        self.c = config
        self.run_id = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
        self.previous: Path | None = None
        self.previous_web: Path | None = None
        self.candidate: Path | None = None
        self.switched = False
        self.target = ''
        self.phase = 'preflight'
        self.started = utcnow()
        self.finished = False

    def emit(self, status: str, phase: str, message: str) -> None:
        self.phase = phase
        record: dict[str, Any] = {
            'schema_version': 1, 'run_id': self.run_id, 'status': status,
            'phase': phase, 'message': message, 'started_at': self.started,
            'updated_at': utcnow(), 'target_commit': self.target,
            'previous_release': str(self.previous or ''),
            'candidate_release': str(self.candidate or ''),
        }
        self.c.state.mkdir(exist_ok=True)
        history = self.c.state / 'history'
        history.mkdir(exist_ok=True)
        for destination in (self.c.state / 'status.json', history / f'{self.run_id}.json'):
            temporary = destination.with_suffix('.tmp')
            temporary.write_text(json.dumps(record, ensure_ascii=False) + '\n', encoding='utf-8')
            temporary.chmod(0o640)
            if hasattr(os, 'geteuid') and os.geteuid() == 0:
                import grp
                os.chown(temporary, 0, grp.getgrnam(self.c.operator).gr_gid)
            os.replace(temporary, destination)
        print(f'[{phase}] {status}: {message}', flush=True)

    def command(self, args: list[str], *, capture: bool = False) -> str:
        try:
            result = subprocess.run(args, check=True, text=True,
                                    stdout=subprocess.PIPE if capture else None,
                                    env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin',
                                         'LANG': 'C.UTF-8', 'HOME': '/root'})
        except subprocess.CalledProcessError as error:
            raise DeploymentError(f'{self.phase}: command failed (exit {error.returncode})') from error
        return result.stdout.strip() if capture else ''

    def as_user(self, user: str, args: list[str]) -> str:
        return self.command(['/usr/sbin/runuser', '-u', user, '--', '/usr/bin/env', '-i',
                             'PATH=/usr/sbin:/usr/bin:/sbin:/bin', 'LANG=C.UTF-8',
                             f'HOME={self.c.build_home}' if user == self.c.build_user else 'HOME=/home/bhadmin',
                             'GIT_TERMINAL_PROMPT=0', *args], capture=True)

    def preflight(self) -> None:
        if (self.c.state / 'pending.json').exists():
            raise DeploymentError('Interrupted activation detected; inspect pending.json before retrying', 22)
        for path in (self.c.current, self.c.web):
            if not path.is_symlink() or not path.resolve().is_dir():
                raise DeploymentError('Install deployment support first; active symlink missing')
        self.previous, self.previous_web = self.c.current.resolve(), self.c.web.resolve()
        if self.previous != self.c.source and self.previous.parent != self.c.releases:
            raise DeploymentError('Unexpected active backend path')
        if self.as_user(self.c.operator, ['git', '-C', str(self.c.source), 'status', '--porcelain']):
            raise DeploymentError('Server source has local changes; refusing to overwrite/deploy', 21)
        if self.as_user(self.c.operator, ['git', '-C', str(self.c.source), 'remote', 'get-url', 'origin']) != self.c.repository:
            raise DeploymentError('Unexpected source repository')
        if shutil.disk_usage(self.c.releases).free < 3 * 1024**3:
            raise DeploymentError('At least 3 GiB free disk space is required')
        self.command(['systemctl', 'is-active', '--quiet', 'exam-backend.service'])

    def fetch(self) -> str:
        mirror = self.c.build_home / 'repository.git'
        if not mirror.exists():
            self.as_user(self.c.build_user, ['git', 'clone', '--bare', self.c.repository, str(mirror)])
        if self.as_user(self.c.build_user, ['git', '--git-dir', str(mirror), 'remote', 'get-url', 'origin']) != self.c.repository:
            raise DeploymentError('Unexpected build repository')
        self.as_user(self.c.build_user, ['git', '--git-dir', str(mirror), 'fetch', '--prune', 'origin',
                                        '+refs/heads/main:refs/heads/main'])
        target = self.as_user(self.c.build_user, ['git', '--git-dir', str(mirror), 'rev-parse', 'refs/heads/main^{commit}'])
        if not re.fullmatch('[0-9a-f]{40}', target):
            raise DeploymentError('Invalid main commit')
        return target

    def active_commit(self) -> str:
        assert self.previous is not None
        marker = self.previous / '.exam-release.json'
        if self.previous == self.c.source:
            return self.as_user(self.c.operator, ['git', '-C', str(self.c.source), 'rev-parse', 'HEAD'])
        return str(json.loads(marker.read_text())['commit'])

    def check_fast_forward(self, current: str) -> None:
        self.as_user(self.c.build_user, ['git', '--git-dir', str(self.c.build_home / 'repository.git'),
                                        'merge-base', '--is-ancestor', current, self.target])

    def build_step(self, cwd: Path, args: list[str], *, capture: bool = False) -> str:
        # Each transient unit kills all descendants when the step finishes.
        unit = f'exam-build-{self.run_id}-{uuid.uuid4().hex[:6]}'
        args = [
            'systemd-run', '--quiet', '--wait', '--pipe', '--collect', f'--unit={unit}',
            f'--property=User={self.c.build_user}', f'--property=Group={self.c.build_user}',
            f'--property=WorkingDirectory={cwd}', '--property=NoNewPrivileges=true',
            '--property=ProtectSystem=strict', '--property=ProtectHome=true',
            '--property=PrivateTmp=true', '--property=PrivateDevices=true',
            '--property=ProtectKernelTunables=true', '--property=ProtectKernelModules=true',
            '--property=ProtectControlGroups=true', '--property=RestrictSUIDSGID=true',
            '--property=CapabilityBoundingSet=', '--property=UMask=0022',
            '--property=RuntimeMaxSec=30min',
            f'--property=ReadWritePaths={self.candidate} {self.c.build_home}',
            '--property=InaccessiblePaths=/etc/exam /var/lib/exam /var/backups/apps/exam',
            '/usr/bin/env', '-i', 'PATH=/usr/sbin:/usr/bin:/sbin:/bin',
            f'HOME={self.c.build_home}', 'LANG=C.UTF-8', 'CI=true',
            'APP_ENV=test', 'DATABASE_URL=sqlite+pysqlite:///:memory:', 'OPENAI_API_KEY=',
            'VITE_API_BASE_URL=/api/v1', 'PYTHONDONTWRITEBYTECODE=1', *args,
        ]
        try:
            return self.command(args, capture=capture)
        finally:
            # Also stop a transient job when its waiting client is interrupted.
            subprocess.run(['systemctl', 'stop', unit], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'})

    def prepare(self) -> None:
        assert self.candidate is not None
        self.candidate.mkdir(mode=0o755)
        self.candidate.chmod(0o755)
        archive = self.c.build_home / f'{self.run_id}.tar'
        try:
            self.as_user(self.c.build_user, ['git', '--git-dir', str(self.c.build_home / 'repository.git'),
                                            'archive', '--format=tar', f'--output={archive}', self.target])
            unpack_archive(archive, self.candidate)
        finally:
            archive.unlink(missing_ok=True)
        import pwd
        account = pwd.getpwnam(self.c.build_user)
        self.change_owner(self.candidate, account.pw_uid, account.pw_gid)
        backend = self.candidate / 'backend'
        python = str(backend / '.venv/bin/python')
        self.build_step(backend, ['/usr/bin/python3', '-m', 'venv', '.venv'])
        self.build_step(backend, [python, '-m', 'pip', 'install', '-e', '.[dev]'])
        for args in ([python, '-m', 'pip', 'check'], [python, '-m', 'ruff', 'check', '.'],
                     [python, '-m', 'mypy', 'app'], [python, '-m', 'pytest']):
            self.build_step(backend, args)
        frontend = self.candidate / 'frontend'
        for args in (['npm', 'ci'], ['npm', 'run', 'lint'], ['npm', 'test'], ['npm', 'run', 'build']):
            self.build_step(frontend, args)
        dist = frontend / 'dist'
        for directory in (backend, frontend, dist, backend / 'alembic', backend / 'alembic/versions'):
            if directory.is_symlink() or not directory.is_dir():
                raise DeploymentError('Unexpected symlink or missing release directory')
        if not (dist / 'index.html').is_file():
            raise DeploymentError('Frontend build did not produce index.html')
        if any(p.is_symlink() or (not p.is_file() and not p.is_dir()) for p in dist.rglob('*')):
            raise DeploymentError('Frontend output must contain regular files only')
        # Obtain Alembic heads WITHOUT running migration env.py or giving code DB secrets.
        heads_code = ('import json; from alembic.config import Config; '
                      'from alembic.script import ScriptDirectory; '
                      'print(json.dumps(ScriptDirectory.from_config(Config("alembic.ini")).get_heads()))')
        heads_file = backend / '.deploy-heads.json'
        # This subprocess runs as the build user; stdout is validated before activation.
        heads = self.build_step(backend, [python, '-c', heads_code], capture=True)
        parsed = json.loads(heads)
        if not isinstance(parsed, list) or len(parsed) != 1 or not re.fullmatch('[A-Za-z0-9_]+', parsed[0]):
            raise DeploymentError('Exactly one valid Alembic head is required', 20)
        if heads_file.is_symlink() or (self.candidate / '.exam-release.json').exists() or (self.candidate / '.exam-release.json').is_symlink():
            raise DeploymentError('Unexpected release metadata path')
        heads_file.write_text(json.dumps(parsed))
        if (frontend / 'node_modules').is_dir():
            shutil.rmtree(frontend / 'node_modules')
        self.freeze_release(self.candidate)
        (self.candidate / '.exam-release.json').write_text(json.dumps({
            'commit': self.target, 'created_at': utcnow(), 'run_id': self.run_id,
        }) + '\n')

    @staticmethod
    def change_owner(root: Path, uid: int, gid: int) -> None:
        for directory, subdirs, files in os.walk(root, followlinks=False):
            os.chown(directory, uid, gid, follow_symlinks=False)
            for name in subdirs + files:
                os.chown(Path(directory) / name, uid, gid, follow_symlinks=False)

    @staticmethod
    def freeze_release(root: Path) -> None:
        for directory, subdirs, files in os.walk(root, followlinks=False):
            for path in [Path(directory), *(Path(directory) / n for n in subdirs + files)]:
                mode = path.lstat().st_mode
                if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode) or stat.S_ISLNK(mode)):
                    raise DeploymentError('Special files are not allowed in a release')
                os.chown(path, 0, 0, follow_symlinks=False)
                if not stat.S_ISLNK(mode):
                    path.chmod(0o755 if stat.S_ISDIR(mode) or mode & 0o111 else 0o644)

    def checkpoint(self) -> None:
        temporary = self.c.state / 'pending.tmp'
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump({'run_id': self.run_id, 'previous_backend': str(self.previous),
                       'previous_frontend': str(self.previous_web),
                       'candidate': str(self.candidate)}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.c.state / 'pending.json')

    def check_schema(self) -> None:
        assert self.candidate is not None and self.previous is not None
        old = migration_hashes(self.previous)
        new = migration_hashes(self.candidate)
        if any(new.get(name) != digest for name, digest in old.items()):
            raise DeploymentError('Existing migration changed; manual review required', 20)
        heads = json.loads((self.candidate / 'backend/.deploy-heads.json').read_text())
        actual = self.command(['mysql', f'--defaults-extra-file={self.c.mysql_config}', '--batch',
                               '--skip-column-names', 'cert_exam', '-e',
                               'SELECT version_num FROM alembic_version ORDER BY version_num'], capture=True)
        if actual.splitlines() != sorted(heads):
            raise DeploymentError('DB migration approval required; no schema or live release changed', 20)

    def backup(self) -> None:
        self.command(['systemctl', 'start', 'exam-db-backup.service'])
        if self.command(['systemctl', 'show', 'exam-db-backup.service', '-p', 'Result', '--value'], capture=True) != 'success':
            raise DeploymentError('Pre-deployment DB backup failed')

    def restart(self) -> None:
        self.command(['systemctl', 'restart', 'exam-backend.service'])

    def healthy(self, release: Path) -> None:
        expected_index = (self.c.web.resolve() / 'index.html').read_bytes()
        for _ in range(30):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3) as response:
                    if json.load(response).get('status') != 'ok':
                        raise ValueError('Unexpected health response')
                with urllib.request.urlopen('http://127.0.0.1:8000/api/v1/system/status', timeout=3) as response:
                    if 'maintenance_active' not in json.load(response):
                        raise ValueError('DB-backed health failed')
                # Verify the actual restarted process uses the candidate, not an old listener.
                pid = self.command(['systemctl', 'show', 'exam-backend.service', '-p', 'MainPID', '--value'], capture=True)
                if Path(f'/proc/{int(pid)}/cwd').resolve() != release / 'backend':
                    raise ValueError('Backend process has an unexpected working directory')
                served = self.command(['curl', '--fail', '--silent', '--show-error', '--max-time', '5',
                    '--resolve', 'certexam.duckdns.org:443:127.0.0.1', 'https://certexam.duckdns.org/'], capture=True)
                if served != expected_index.decode().strip():
                    raise ValueError('Nginx did not serve the selected frontend')
                return
            except (OSError, ValueError, DeploymentError):
                time.sleep(2)
        raise DeploymentError('Post-deployment health check failed')

    def cleanup_candidate(self) -> None:
        if self.candidate is None or not self.candidate.exists():
            return
        if self.candidate.is_symlink() or self.candidate.parent.resolve() != self.c.releases.resolve():
            raise DeploymentError('Unsafe candidate cleanup path')
        if self.c.current.resolve() == self.candidate or self.c.web.resolve().is_relative_to(self.candidate):
            return
        shutil.rmtree(self.candidate)

    def prune(self) -> None:
        keep = {self.c.current.resolve(), self.previous}
        known = sorted((p for p in self.c.releases.iterdir()
                        if p.is_dir() and not p.is_symlink() and (p / '.exam-release.json').is_file()),
                       key=lambda p: p.name, reverse=True)
        keep.update(known[:3])
        for release in known:
            if release not in keep and release.parent.resolve() == self.c.releases.resolve():
                shutil.rmtree(release)

    def execute(self) -> int:
        try:
            self.emit('running', 'preflight', 'Checking fixed deployment target')
            self.preflight()
            self.emit('running', 'fetch', 'Fetching origin/main; live source and .env are untouched')
            self.target = self.fetch()
            current = self.active_commit()
            self.check_fast_forward(current)
            if current == self.target and self.previous != self.c.source:
                self.emit('noop', 'complete', 'Already running the latest main commit')
                return 0
            self.candidate = self.c.releases / f'{self.run_id}-{self.target[:12]}'
            self.emit('running', 'build', 'Building and testing as an isolated unprivileged user')
            self.prepare()
            self.emit('running', 'schema', 'Checking schema compatibility without migrations')
            self.check_schema()
            self.emit('running', 'backup', 'Backing up production DB before activation')
            self.backup()
            self.emit('running', 'activate', 'Switching backend and frontend releases')
            self.checkpoint()
            self.switched = True  # Covers a failure between the two link replacements.
            atomic_link(self.c.current, self.candidate)
            atomic_link(self.c.web, self.candidate / 'frontend/dist')
            self.restart()
            self.emit('running', 'health', 'Checking backend process, DB API and HTTPS frontend')
            self.healthy(self.candidate)
            self.finished = True
            (self.c.state / 'pending.json').unlink()
            self.emit('succeeded', 'complete', 'Deployment healthy; no database schema changes made')
            try:
                self.prune()
            except OSError:
                print('Warning: old release cleanup deferred; active deployment is healthy', flush=True)
            return 0
        except Exception as error:
            code = error.code if isinstance(error, DeploymentError) else 1
            message = str(error) if isinstance(error, DeploymentError) else f'{self.phase}: {type(error).__name__}'
            status = 'blocked' if code in (20, 21, 22) else 'failed'
            if self.switched and not self.finished:
                try:
                    assert self.previous is not None and self.previous_web is not None
                    self.emit('running', 'rollback', 'Restoring previous code/frontend; DB is not restored')
                    atomic_link(self.c.current, self.previous)
                    atomic_link(self.c.web, self.previous_web)
                    self.restart()
                    self.healthy(self.previous)
                    (self.c.state / 'pending.json').unlink(missing_ok=True)
                    status = 'rolled_back'
                except Exception:
                    self.emit('rollback_failed', 'rollback', 'Manual intervention required; releases and DB preserved')
                    return 2
            self.emit(status, self.phase, message)
            self.cleanup_candidate()
            return code


def main() -> int:
    if len(sys.argv) != 1 or not hasattr(os, 'geteuid') or os.geteuid() != 0:
        print('Usage: sudo /usr/local/sbin/exam-deploy (no arguments)', file=sys.stderr)
        return 77
    import fcntl
    config = Config()
    # No environment/CLI path overrides in the privileged entry point.
    os.umask(0o027)
    fd = os.open(config.lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another deployment is already running', file=sys.stderr)
            return 75
        def interrupted(signum: int, frame: Any) -> None:
            raise DeploymentError(f'Deployment interrupted by signal {signum}', 130)
        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGINT, interrupted)
        return Deployment(config).execute()


if __name__ == '__main__':
    raise SystemExit(main())
