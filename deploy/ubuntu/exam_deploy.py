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
import platform
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import time
import tomllib
from dataclasses import dataclass
from typing import Any
import urllib.request
import uuid


@dataclass(frozen=True)
class Config:
    source: Path = Path('/opt/apps/exam')
    releases: Path = Path('/opt/apps/exam-releases')
    environments: Path = Path('/opt/apps/exam-python-envs')
    node_environments: Path = Path('/opt/apps/exam-node-envs')
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
        self.started_clock = time.monotonic()
        self.finished = False
        self.environment: Path | None = None
        self.new_environment: Path | None = None
        self.writable_environment: Path | None = None
        self.node_environment: Path | None = None
        self.new_node_environment: Path | None = None

    def emit(self, status: str, phase: str, message: str) -> None:
        self.phase = phase
        record: dict[str, Any] = {
            'schema_version': 1, 'run_id': self.run_id, 'status': status,
            'phase': phase, 'message': message, 'started_at': self.started,
            'updated_at': utcnow(), 'target_commit': self.target,
            'previous_release': str(self.previous or ''),
            'candidate_release': str(self.candidate or ''),
            'elapsed_seconds': round(time.monotonic() - self.started_clock, 2),
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
        # UI가 읽는 phase/status는 유지하고, 터미널에는 사람이 읽을 단계 번호를 붙인다.
        steps = {'preflight': '1/7', 'fetch': '2/7', 'build': '3/7',
                 'schema': '4/7', 'activate': '5/7',
                 'health': '6/7', 'complete': '7/7', 'rollback': '복구'}
        print(f'[{steps.get(phase, phase)}][{phase}][{status}] {message}', flush=True)

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
        if not self.c.environments.is_dir() or self.c.environments.is_symlink():
            raise DeploymentError('Install updated deployment support first; Python environment store missing')
        if not self.c.node_environments.is_dir() or self.c.node_environments.is_symlink():
            raise DeploymentError('Install updated deployment support first; Node environment store missing')
        if (self.c.node_environments.stat().st_uid != 0
                or self.c.node_environments.stat().st_mode & 0o022):
            raise DeploymentError('Unsafe Node environment store permissions')
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
            f'--property=ReadWritePaths={self.candidate}'
            + (f' {self.writable_environment}' if self.writable_environment else ''),
            '--property=InaccessiblePaths=/etc/exam /var/lib/exam /var/backups/apps/exam',
            '/usr/bin/env', '-i', 'PATH=/usr/sbin:/usr/bin:/sbin:/bin',
            f'HOME={self.candidate}/.build-home', 'LANG=C.UTF-8', 'CI=true',
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

    def logged_build_step(self, label: str, cwd: Path, args: list[str], *, capture: bool = False) -> str:
        # 명령 인자/환경값을 재출력하지 않는다. 고정 설명만 남겨 비밀값 노출을 피한다.
        self.emit('running', 'build', label + ' — 시작 (운영 서비스는 계속 실행 중)')
        started = time.monotonic()
        try:
            result = self.build_step(cwd, args, capture=capture)
        except DeploymentError as error:
            # 최종 status.json에서도 어느 하위 검사가 실패했는지 알 수 있게 한다.
            raise DeploymentError(f'{label}: {error}', error.code) from error
        print(f'[3/7][완료] {label} ({time.monotonic() - started:.1f}초)', flush=True)
        return result

    @staticmethod
    def dependency_key(paths: list[Path], runtime: str) -> str:
        digest = hashlib.sha256(('exam-dependencies-v1\0' + runtime).encode())
        for path in paths:
            data = path.read_bytes() if path.is_file() else b''
            digest.update(len(data).to_bytes(8, 'big'))
            digest.update(data)
        return digest.hexdigest()

    @staticmethod
    def environment_ready(path: Path, key: str) -> bool:
        marker = path / '.exam-env.json'
        try:
            return (not path.is_symlink() and path.is_dir()
                    and path.stat().st_uid == 0 and not path.stat().st_mode & 0o022
                    and not marker.is_symlink() and marker.stat().st_uid == 0
                    and not marker.stat().st_mode & 0o022
                    and json.loads(marker.read_text()).get('key') == key
                    and (path / 'bin/python').is_file())
        except (OSError, ValueError, AttributeError):
            return False

    def prepare_python(self, backend: Path, uid: int, gid: int) -> str:
        manifest = backend / 'pyproject.toml'
        project = tomllib.loads(manifest.read_text(encoding='utf-8'))['project']
        requires = re.fullmatch(r'>=\s*(\d+)\.(\d+)(?:\.(\d+))?', project.get('requires-python', ''))
        dependencies = project.get('dependencies')
        # 현재 프로젝트로 검증된 정적 의존성 계약만 허용한다. 새 패키징 방식은 검토가 필요하다.
        if (not requires or tuple(map(int, requires.groups(default='0'))) > sys.version_info[:3]
                or project.get('dynamic') or project.get('scripts') or project.get('gui-scripts')
                or project.get('entry-points') or not isinstance(dependencies, list)
                or not all(isinstance(d, str) and re.match(r'^[A-Za-z0-9]', d)
                           and not any(c in d for c in ('@', '/', '\\')) for d in dependencies)):
            raise DeploymentError('Unsupported Python dependency contract; manual review required')
        identity = f'{sys.version}|{sys.implementation.cache_tag}|{platform.machine()}|{sys.platform}'
        key = self.dependency_key([manifest], identity)
        for path in sorted(self.c.environments.glob(f'{key}-*')):
            if self.environment_ready(path, key):
                self.environment = path
                self.emit('running', 'build', '3-1 Python 의존성 변경 없음 — 기존 환경 재사용 (설치 생략)')
                break
        if self.environment is None:
            # venv에는 절대 경로가 들어간다. 완성 후에도 이동/이름 변경하지 않는다.
            self.environment = self.new_environment = self.c.environments / f'{key}-{self.run_id}'
            self.environment.mkdir(mode=0o755)
            os.chown(self.environment, uid, gid)
            self.writable_environment = self.environment
            try:
                self.logged_build_step('3-1 새 Python 의존성 환경 생성', backend,
                                       ['/usr/bin/python3', '-I', '-m', 'venv', str(self.environment)])
                python = str(self.environment / 'bin/python')
                self.logged_build_step('3-2 변경된 Python 운영 의존성 설치', backend,
                                       [python, '-I', '-m', 'pip', 'install', '--disable-pip-version-check',
                                        '--no-input', '--', *dependencies])
                self.logged_build_step('3-3 Python 의존성 호환성 검사', backend,
                                       [python, '-I', '-m', 'pip', 'check'])
                # 빌드 계정이 나중에 바꿀 수 있는 외부 파일을 캐시 환경이 참조하지 못하게 한다.
                for path in self.environment.rglob('*'):
                    if path.is_symlink() and not path.resolve().is_relative_to(self.environment):
                        if not (path.parent == self.environment / 'bin'
                                and path.resolve() == Path(sys.executable).resolve()):
                            raise DeploymentError('Unsafe Python environment link')
                marker = self.environment / '.exam-env.json'
                if marker.exists() or marker.is_symlink():
                    raise DeploymentError('Unexpected Python environment metadata')
                self.freeze_release(self.environment)
                marker.write_text(json.dumps({'key': key}) + '\n')
                marker.chmod(0o644)
            finally:
                self.writable_environment = None
        link = backend / '.venv'
        if link.exists() or link.is_symlink():
            raise DeploymentError('Source must not supply a Python environment')
        link.symlink_to(self.environment, target_is_directory=True)
        return str(link / 'bin/python')

    def frontend_dependency_key(self, frontend: Path) -> str:
        package = json.loads((frontend / 'package.json').read_text())
        scripts = package.get('scripts', {})
        dependency_values = [value for section in ('dependencies', 'devDependencies', 'optionalDependencies')
                             for value in package.get(section, {}).values()]
        # 설치 훅/workspace/로컬 의존성이 있으면 소스 변경이 설치 결과에도 영향을 줄 수 있다.
        if ((frontend / 'npm-shrinkwrap.json').exists() or package.get('overrides')
                or package.get('workspaces') or any(name in scripts for name in (
                'preinstall', 'install', 'postinstall', 'prepublish', 'preprepare', 'prepare', 'postprepare'))
                or any(not isinstance(value, str) or value.startswith(('file:', 'link:', 'workspace:', '.', '/'))
                       for value in dependency_values)):
            return ''
        lock = json.loads((frontend / 'package-lock.json').read_text())
        if lock.get('lockfileVersion') != 3 or any(
                value.get('link') or str(value.get('resolved', '')).startswith(('file:', 'link:', '.', '/'))
                for value in lock.get('packages', {}).values()):
            return ''
        runtime = self.build_step(frontend, ['node', '--version'], capture=True)
        runtime += '|' + self.build_step(frontend, ['npm', '--version'], capture=True)
        runtime += f'|{sys.platform}|{platform.machine()}'
        return self.dependency_key([frontend / 'package.json', frontend / 'package-lock.json',
                                    frontend / '.npmrc', frontend.parent / '.npmrc'], runtime)

    @staticmethod
    def reusable_node_modules(root: Path) -> bool:
        if root.is_symlink() or not root.is_dir() or not (root / '.package-lock.json').is_file():
            return False
        for path in root.rglob('*'):
            if path.is_symlink():
                if os.path.isabs(os.readlink(path)) or not path.resolve().is_relative_to(root):
                    return False
            elif not path.is_file() and not path.is_dir():
                return False
        return True

    @classmethod
    def immutable_node_modules(cls, root: Path) -> bool:
        if not cls.reusable_node_modules(root):
            return False
        return all(path.is_symlink() or (path.stat().st_uid == 0 and not path.stat().st_mode & 0o022)
                   for path in [root, *root.rglob('*')])

    def prepare_frontend(self, frontend: Path) -> str:
        if (frontend / 'node_modules').exists() or (frontend / 'node_modules').is_symlink():
            raise DeploymentError('Source must not supply node_modules')
        key = self.frontend_dependency_key(frontend)
        if key:
            for environment in sorted(self.c.node_environments.glob(f'{key}-*')):
                if self.node_environment_ready(environment, key):
                    self.node_environment = environment
                    break
        previous_key = ''
        if self.previous is not None and self.previous != self.c.source:
            try:
                previous_key = json.loads((self.previous / '.exam-release.json').read_text()).get('frontend_dependencies_key', '')
            except (OSError, ValueError, AttributeError):
                pass
        previous_modules = self.previous / '.node-dependencies' if self.previous else Path('/nonexistent')
        snapshot = frontend.parent / '.node-dependencies'
        if snapshot.exists() or snapshot.is_symlink():
            raise DeploymentError('Source must not supply dependency snapshots')
        modules = frontend / 'node_modules'
        if self.node_environment is None:
            # 구 버전의 검증된 원본은 첫 전환에만 복사한다. 기존 릴리스는 수정하지 않는다.
            if (key and key == previous_key and self.immutable_node_modules(previous_modules)):
                self.logged_build_step('3-4 기존 Node 원본을 새 캐시로 1회 이전 (설치 생략)', frontend,
                                       ['cp', '-R', '--preserve=mode,timestamps', '--reflink=auto',
                                        str(previous_modules), str(modules)])
            else:
                self.logged_build_step('3-4 변경된 프론트엔드 의존성 설치', frontend,
                                       ['npm', 'ci', '--prefer-offline', '--no-audit', '--no-fund'])
            if not self.reusable_node_modules(modules):
                raise DeploymentError('Unsafe Node dependency tree')
            self.node_environment = self.new_node_environment = (
                self.c.node_environments / f'{key or "uncached"}-{self.run_id}')
            self.node_environment.mkdir(mode=0o755)
            # 같은 /opt 파일시스템에서 이동: 설치 직후 원본을 복제하지 않는다.
            modules.rename(self.node_environment / 'node_modules')
            self.freeze_release(self.node_environment)
            marker = self.node_environment / '.exam-node-env.json'
            marker.write_text(json.dumps({'key': key}) + '\n')
            marker.chmod(0o644)
        else:
            self.emit('running', 'build', '3-4 Node 의존성 변경 없음 — 읽기 전용 연결 (설치·복사 생략)')
        os.chown(frontend.parent, 0, 0)
        frontend.parent.chmod(0o755)
        snapshot.symlink_to(self.node_environment / 'node_modules', target_is_directory=True)
        modules.symlink_to(self.node_environment / 'node_modules', target_is_directory=True)
        # Vite 기본 config bundler의 node_modules/.vite-temp 쓰기를 피한다.
        self.logged_build_step('3-5 프론트엔드 운영 빌드', frontend,
                               ['npm', 'run', 'build', '--', '--configLoader', 'runner'])
        if modules.resolve() != self.node_environment / 'node_modules':
            raise DeploymentError('Node environment link changed during build')
        return key

    @staticmethod
    def node_environment_ready(path: Path, key: str) -> bool:
        marker = path / '.exam-node-env.json'
        try:
            return (not path.is_symlink() and path.is_dir()
                    and path.stat().st_uid == 0 and not path.stat().st_mode & 0o022
                    and not marker.is_symlink() and marker.stat().st_uid == 0
                    and not marker.stat().st_mode & 0o022
                    and json.loads(marker.read_text()).get('key') == key
                    and not (path / 'node_modules').is_symlink()
                    and (path / 'node_modules/.package-lock.json').is_file())
        except (OSError, ValueError, AttributeError):
            return False

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
        temporary_home = self.candidate / '.build-home'
        if temporary_home.exists() or temporary_home.is_symlink():
            raise DeploymentError('Source must not supply build home')
        temporary_home.mkdir(mode=0o700)
        os.chown(temporary_home, account.pw_uid, account.pw_gid)
        backend = self.candidate / 'backend'
        python = self.prepare_python(backend, account.pw_uid, account.pw_gid)
        frontend = self.candidate / 'frontend'
        frontend_key = self.prepare_frontend(frontend)
        # 앱 소스는 재사용할 의존성이 모두 고정된 뒤에만 실행한다.
        # import만 확인하며 서버 시작/lifespan/운영 DB 접속은 하지 않는다.
        self.logged_build_step('3-6 백엔드 모듈 로딩 확인 (DB 접속 없음)', backend,
                               [python, '-c', 'from app.main import app; assert app.routes'])
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
        heads = self.logged_build_step('3-7 Alembic 목표 버전 확인 (DB 접속 없음)',
                                       backend, [python, '-c', heads_code], capture=True)
        parsed = json.loads(heads)
        if not isinstance(parsed, list) or len(parsed) != 1 or not re.fullmatch('[A-Za-z0-9_]+', parsed[0]):
            raise DeploymentError('Exactly one valid Alembic head is required', 20)
        if heads_file.is_symlink() or (self.candidate / '.exam-release.json').exists() or (self.candidate / '.exam-release.json').is_symlink():
            raise DeploymentError('Unexpected release metadata path')
        heads_file.write_text(json.dumps(parsed))
        self.emit('running', 'build', '3-8 재사용 의존성 보존 및 릴리스 권한 고정')
        if (backend / '.venv').resolve() != self.environment:
            raise DeploymentError('Python environment link changed during build')
        shutil.rmtree(temporary_home)
        modules = frontend / 'node_modules'
        if (not modules.is_symlink()
                or modules.resolve() != self.node_environment / 'node_modules'):
            raise DeploymentError('Refusing unexpected Node environment cleanup')
        modules.unlink()
        self.freeze_release(self.candidate)
        (self.candidate / '.exam-release.json').write_text(json.dumps({
            'commit': self.target, 'created_at': utcnow(), 'run_id': self.run_id,
            'frontend_dependencies_key': frontend_key,
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

    def restart(self) -> None:
        self.command(['systemctl', 'restart', 'exam-backend.service'])

    def healthy(self, release: Path) -> None:
        expected_index = (self.c.web.resolve() / 'index.html').read_bytes()
        for attempt in range(30):
            if attempt % 5 == 0:
                print(f'[{self.phase}] 상태 확인 {attempt + 1}/30: 백엔드 · DB API · HTTPS', flush=True)
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
        self.prune_environments()
        self.prune_node_environments()

    def prune_environments(self) -> None:
        # 보관 중인 어떤 릴리스라도 참조하는 환경은 삭제하지 않는다. 정체불명 경로도 보존한다.
        referenced = {(release / 'backend/.venv').resolve() for release in self.c.releases.iterdir()
                      if release.is_dir() and not release.is_symlink()}
        referenced.add((self.c.current.resolve() / 'backend/.venv').resolve())
        if not self.c.environments.is_dir():
            return
        for path in self.c.environments.iterdir():
            if (path.is_symlink() or path in referenced
                    or path.parent.resolve() != self.c.environments.resolve()):
                continue
            key = path.name.split('-', 1)[0]
            if ((re.fullmatch('[0-9a-f]{64}', key) and self.environment_ready(path, key))
                    or path == self.new_environment):
                shutil.rmtree(path)

    def prune(self) -> None:
        keep = {self.c.current.resolve(), self.previous}
        known = sorted((p for p in self.c.releases.iterdir()
                        if p.is_dir() and not p.is_symlink() and (p / '.exam-release.json').is_file()),
                       key=lambda p: p.name, reverse=True)
        keep.update(known[:3])
        for release in known:
            if release not in keep and release.parent.resolve() == self.c.releases.resolve():
                shutil.rmtree(release)
        self.prune_environments()
        self.prune_node_environments()

    def prune_node_environments(self) -> None:
        referenced = {(release / '.node-dependencies').resolve().parent
                      for release in self.c.releases.iterdir()
                      if release.is_dir() and not release.is_symlink()}
        if not self.c.node_environments.is_dir():
            return
        for path in self.c.node_environments.iterdir():
            if (path.is_symlink() or path in referenced
                    or path.parent.resolve() != self.c.node_environments.resolve()):
                continue
            key = path.name.split('-', 1)[0]
            if ((re.fullmatch('[0-9a-f]{64}|uncached', key)
                 and self.node_environment_ready(path, '' if key == 'uncached' else key))
                    or path == self.new_node_environment):
                shutil.rmtree(path)

    def execute(self) -> int:
        try:
            # 1~4: 운영 코드/DB 스키마를 변경하지 않는 준비 구간이다.
            self.emit('running', 'preflight', '사전 점검: 중단된 배포, 운영 경로, 서버 소스 변경, 디스크, 서비스 확인')
            self.preflight()
            self.emit('running', 'fetch', 'Git main 최신 소스 가져오기 — 원본 작업 폴더와 .env는 그대로 유지')
            self.target = self.fetch()
            current = self.active_commit()
            self.emit('running', 'fetch', f'현재 {current[:12]} → 대상 {self.target[:12]} / 커밋 이력 확인')
            self.check_fast_forward(current)
            if current == self.target and self.previous != self.c.source:
                self.emit('noop', 'complete', '이미 최신 커밋 실행 중 — 빌드·백업·재시작 없이 종료')
                return 0
            self.candidate = self.c.releases / f'{self.run_id}-{self.target[:12]}'
            self.emit('running', 'build', '경량 배포 준비 — 운영 의존성·빌드만 수행, 전체 테스트는 CI에서 실행')
            self.prepare()
            self.emit('running', 'schema', 'DB 버전과 기존 마이그레이션 비교 — 스키마 변경이 필요하면 중단')
            self.check_schema()
            # 백업은 사용자 지정 월간 타이머만 담당한다. 배포에서는 호출하지 않는다.
            # 5: 여기부터 운영에 반영된다. 복구 정보 기록 후 두 링크를 전환한다.
            self.emit('running', 'activate', '운영 반영 시작: 복구 정보 기록 → 백엔드/프론트엔드 링크 전환')
            self.checkpoint()
            self.switched = True  # Covers a failure between the two link replacements.
            atomic_link(self.c.current, self.candidate)
            atomic_link(self.c.web, self.candidate / 'frontend/dist')
            self.emit('running', 'activate', '백엔드 재시작 — 짧은 접속 중단 및 재로그인이 발생할 수 있음')
            self.restart()
            # 6: 프로세스가 새 코드를 실행하고 HTTPS가 새 화면을 반환하는지 확인한다.
            self.emit('running', 'health', '운영 검증: 백엔드 실행 경로 · health API · DB API · HTTPS 화면')
            self.healthy(self.candidate)
            self.finished = True
            (self.c.state / 'pending.json').unlink()
            # 7: 검증된 배포만 완료 처리. 정리는 알려진 오래된 릴리스에 한정한다.
            print('[7/7][정리] 오래된 릴리스 정리 — 최근 3개와 직전 운영 릴리스 보존', flush=True)
            try:
                self.prune()
            except OSError:
                print('[7/7][경고] 오래된 릴리스 정리 보류 — 운영 서비스 상태는 정상', flush=True)
            self.emit('succeeded', 'complete', '배포 완료 — 운영 검증 통과, DB 스키마 변경 없음')
            return 0
        except Exception as error:
            code = error.code if isinstance(error, DeploymentError) else 1
            message = str(error) if isinstance(error, DeploymentError) else f'{self.phase}: {type(error).__name__}'
            status = 'blocked' if code in (20, 21, 22) else 'failed'
            if self.switched and not self.finished:
                try:
                    assert self.previous is not None and self.previous_web is not None
                    # 전환 후 실패만 이전 코드로 복구한다. DB 복원/downgrade는 하지 않는다.
                    self.emit('running', 'rollback', f'배포 실패 ({message}) — 이전 코드/화면 복구 및 재검증, DB 복원 없음')
                    atomic_link(self.c.current, self.previous)
                    atomic_link(self.c.web, self.previous_web)
                    self.restart()
                    self.healthy(self.previous)
                    (self.c.state / 'pending.json').unlink(missing_ok=True)
                    status = 'rolled_back'
                except Exception:
                    self.emit('rollback_failed', 'rollback', '자동 복구 검증 실패 — 수동 확인 필요, 릴리스와 DB 보존')
                    return 2
            self.emit(status, self.phase, message)
            self.cleanup_candidate()
            return code
        finally:
            elapsed = time.monotonic() - self.started_clock
            minutes, seconds = divmod(elapsed, 60)
            print(f'[배포 종료] 총 배포 소요 시간: {int(minutes)}분 {seconds:.1f}초 ({elapsed:.1f}초)',
                  flush=True)


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
