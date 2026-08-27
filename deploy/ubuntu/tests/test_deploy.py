"""No production services, secrets, network, or third-party packages are used."""
import importlib.util
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import subprocess
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'exam_deploy.py'
spec = importlib.util.spec_from_file_location('exam_deploy', MODULE)
deploy = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = deploy
spec.loader.exec_module(deploy)


class FakeDeployment(deploy.Deployment):
    def __init__(self, config, fail=''):
        super().__init__(config)
        self.fail = fail
        self.calls = []
        self.new_commit = 'a' * 40

    def preflight(self):
        self.previous = self.c.current.resolve()
        self.previous_web = self.c.web.resolve()
        if self.fail == 'dirty':
            raise deploy.DeploymentError('dirty worktree', 21)

    def fetch(self):
        return self.new_commit

    def active_commit(self):
        return 'b' * 40

    def check_fast_forward(self, current):
        if self.fail == 'nonfastforward':
            raise deploy.DeploymentError('not fast forward')

    def prepare(self):
        self.calls.append('build')
        self.candidate.mkdir()
        (self.candidate / 'backend/alembic/versions').mkdir(parents=True)
        (self.candidate / 'frontend/dist').mkdir(parents=True)
        (self.candidate / 'frontend/dist/index.html').write_text('candidate')
        (self.candidate / '.exam-release.json').write_text('{}')
        if self.fail == 'build':
            raise deploy.DeploymentError('build failed')

    def check_schema(self):
        self.calls.append('schema')
        if self.fail == 'schema':
            raise deploy.DeploymentError('migration required', 20)

    def backup(self):
        self.calls.append('backup')
        if self.fail == 'backup':
            raise deploy.DeploymentError('backup failed')

    def restart(self):
        self.calls.append('restart')
        if self.fail == 'restart' and self.c.current.resolve() == self.candidate:
            raise deploy.DeploymentError('restart failed')

    def healthy(self, release):
        self.calls.append('health')
        if self.fail == 'rollback' or (self.fail == 'health' and release == self.candidate):
            raise deploy.DeploymentError('unhealthy')


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.c = deploy.Config(source=root / 'source', releases=root / 'releases',
                               current=root / 'current', web=root / 'web', state=root / 'state',
                               environments=root / 'environments', build_home=root / 'build-home')
        self.c.source.mkdir()
        (self.c.source / '.env').write_text('DO_NOT_DELETE')
        old_web = root / 'old-web'
        old_web.mkdir()
        (old_web / 'index.html').write_text('old')
        self.c.releases.mkdir()
        self.c.environments.mkdir()
        self.c.current.symlink_to(self.c.source, target_is_directory=True)
        self.c.web.symlink_to(old_web, target_is_directory=True)
        self.old_web = old_web
        # Tests may run under root in CI; avoid looking up a host-specific account.
        self.uid = patch.object(deploy.os, 'geteuid', return_value=1000, create=True)
        self.uid.start()

    def tearDown(self):
        self.uid.stop()
        self.temp.cleanup()

    def state(self):
        return json.loads((self.c.state / 'status.json').read_text())

    def assert_unchanged(self):
        self.assertEqual(self.c.current.resolve(), self.c.source)
        self.assertEqual(self.c.web.resolve(), self.old_web)
        self.assertEqual((self.c.source / '.env').read_text(), 'DO_NOT_DELETE')

    def test_success_and_order(self):
        job = FakeDeployment(self.c)
        self.assertEqual(job.execute(), 0)
        self.assertEqual(job.calls, ['build', 'schema', 'restart', 'health'])
        self.assertEqual(self.state()['status'], 'succeeded')
        self.assertEqual(self.c.current.resolve(), job.candidate)
        self.assertTrue((self.c.source / '.env').exists())

    def test_pre_activation_failures_preserve_service_and_env(self):
        for failure in ('dirty', 'nonfastforward', 'build', 'schema'):
            with self.subTest(failure=failure):
                job = FakeDeployment(self.c, failure)
                self.assertNotEqual(job.execute(), 0)
                self.assertNotIn('restart', job.calls)
                self.assert_unchanged()
                if job.candidate:
                    self.assertFalse(job.candidate.exists())

    def test_health_and_restart_failure_roll_back_both_links(self):
        for failure in ('health', 'restart'):
            with self.subTest(failure=failure):
                job = FakeDeployment(self.c, failure)
                self.assertNotEqual(job.execute(), 0)
                self.assertEqual(self.state()['status'], 'rolled_back')
                self.assert_unchanged()
                self.assertFalse(job.candidate.exists())

    def test_rollback_failure_preserves_artifacts(self):
        job = FakeDeployment(self.c, 'rollback')
        self.assertEqual(job.execute(), 2)
        self.assertEqual(self.state()['status'], 'rollback_failed')
        self.assertTrue(job.candidate.exists())

    def test_failure_between_link_switches_rolls_back(self):
        original = deploy.atomic_link
        count = 0
        def failing_link(link, target):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('simulated frontend link error')
            original(link, target)
        with patch.object(deploy, 'atomic_link', side_effect=failing_link):
            job = FakeDeployment(self.c)
            self.assertNotEqual(job.execute(), 0)
        self.assert_unchanged()
        self.assertEqual(self.state()['status'], 'rolled_back')

    def test_noop_does_not_build_backup_or_restart(self):
        release = self.c.releases / 'existing'
        release.mkdir()
        deploy.atomic_link(self.c.current, release)
        job = FakeDeployment(self.c)
        job.new_commit = 'b' * 40
        self.assertEqual(job.execute(), 0)
        self.assertEqual(self.state()['status'], 'noop')
        self.assertEqual(job.calls, [])

    def test_deployment_never_starts_a_backup(self):
        job = FakeDeployment(self.c, 'backup')
        self.assertEqual(job.execute(), 0)
        self.assertNotIn('backup', job.calls)

    def test_cleanup_rejects_outside_release_root(self):
        job = FakeDeployment(self.c)
        job.candidate = self.c.source
        with self.assertRaises(deploy.DeploymentError):
            job.cleanup_candidate()
        self.assertTrue((self.c.source / '.env').exists())

    def test_real_directory_is_not_replaced_by_link(self):
        with self.assertRaises(deploy.DeploymentError):
            deploy.atomic_link(self.c.source, self.old_web)

    def test_schema_mismatch_and_changed_historical_migration(self):
        job = FakeDeployment(self.c)
        job.preflight()
        job.candidate = self.c.releases / 'schema-test'
        job.prepare()
        (job.candidate / 'backend/.deploy-heads.json').write_text('["0011_new"]')
        job.command = lambda *a, **kw: '0010_old'
        with self.assertRaises(deploy.DeploymentError) as error:
            deploy.Deployment.check_schema(job)
        self.assertEqual(error.exception.code, 20)
        old = self.c.source / 'backend/alembic/versions'
        old.mkdir(parents=True)
        (old / '0010.py').write_text('original')
        (job.candidate / 'backend/alembic/versions/0010.py').write_text('changed')
        with self.assertRaises(deploy.DeploymentError):
            deploy.Deployment.check_schema(job)

    def test_pending_activation_blocks_new_deployment(self):
        self.c.state.mkdir()
        (self.c.state / 'pending.json').write_text('{}')
        with self.assertRaises(deploy.DeploymentError) as error:
            deploy.Deployment.preflight(FakeDeployment(self.c))
        self.assertEqual(error.exception.code, 22)

    def test_interrupted_build_stops_transient_job(self):
        job = FakeDeployment(self.c)
        job.candidate = self.c.releases / 'candidate'
        with patch.object(job, 'command', side_effect=deploy.DeploymentError('interrupted', 130)), \
                patch.object(deploy.subprocess, 'run') as stop:
            with self.assertRaises(deploy.DeploymentError):
                job.build_step(self.c.source, ['false'])
            self.assertEqual(stop.call_args.args[0][:2], ['systemctl', 'stop'])

    def test_retention_preserves_current_previous_and_unknown_directories(self):
        job = FakeDeployment(self.c)
        job.preflight()
        for n in range(6):
            release = self.c.releases / f'2026010{n}'
            release.mkdir()
            (release / '.exam-release.json').write_text('{}')
        unknown = self.c.releases / 'operator-files'
        unknown.mkdir()
        (unknown / 'keep.txt').write_text('keep')
        job.previous = self.c.releases / '20260100'
        deploy.atomic_link(self.c.current, self.c.releases / '20260105')
        job.prune()
        self.assertTrue(job.previous.exists())
        self.assertTrue((unknown / 'keep.txt').exists())
        self.assertFalse((self.c.releases / '20260101').exists())
        self.assertEqual(len(list(self.c.releases.iterdir())), 5)

    @unittest.skipUnless(sys.platform == 'linux', 'Linux flock contract')
    def test_concurrent_entry_rejected(self):
        import fcntl
        self.c.state.mkdir()
        config = deploy.Config(lock=self.c.state / 'deploy.lock')
        with config.lock.open('w') as locked:
            fcntl.flock(locked, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(deploy, 'Config', return_value=config), \
                    patch.object(deploy.os, 'geteuid', return_value=0), \
                    patch.object(deploy.sys, 'argv', ['exam-deploy']):
                self.assertEqual(deploy.main(), 75)

    def python_backend(self, name):
        backend = self.c.source / name / 'backend'
        backend.mkdir(parents=True)
        (backend / 'pyproject.toml').write_text(
            '[project]\nname="exam"\nrequires-python=">=3.12"\ndependencies=["fastapi>=0.115"]\n')
        return backend

    def test_python_environment_cold_warm_and_changed_manifest(self):
        first = FakeDeployment(self.c)
        commands = []
        def install(label, cwd, args, **kwargs):
            commands.append(args)
            if 'venv' in args:
                (first.environment / 'bin').mkdir()
                (first.environment / 'bin/python').write_text('test interpreter')
            return ''
        with patch.object(deploy.os, 'chown'), patch.object(first, 'freeze_release'), \
                patch.object(first, 'logged_build_step', side_effect=install):
            first.prepare_python(self.python_backend('first'), 1000, 1000)
        self.assertEqual(len(commands), 3)
        self.assertNotIn('.[dev]', str(commands))
        self.assertEqual(commands[1][-1], 'fastapi>=0.115')
        self.assertIsNone(first.writable_environment)
        self.assertTrue((first.environment / '.exam-env.json').is_file())
        second = FakeDeployment(self.c)
        second_backend = self.python_backend('second')
        with patch.object(second, 'environment_ready', return_value=True), \
                patch.object(second, 'logged_build_step') as installed:
            second.prepare_python(second_backend, 1000, 1000)
        installed.assert_not_called()
        self.assertEqual((second_backend / '.venv').resolve(), first.environment)
        (second_backend / '.venv').unlink()
        (second_backend / 'pyproject.toml').write_text(
            '[project]\nname="exam"\nrequires-python=">=3.12"\ndependencies=["fastapi>=0.116"]\n')
        third = FakeDeployment(self.c)
        with patch.object(deploy.os, 'chown'), \
                patch.object(third, 'logged_build_step', side_effect=deploy.DeploymentError('stop')):
            with self.assertRaises(deploy.DeploymentError):
                third.prepare_python(second_backend, 1000, 1000)
        self.assertNotEqual(third.new_environment, first.environment)
        self.assertIsNone(third.writable_environment)
        self.assertFalse((third.new_environment / '.exam-env.json').exists())

    def test_dependency_key_changes_for_runtime_and_file_changes(self):
        manifest = self.c.source / 'manifest'
        manifest.write_text('one')
        initial = deploy.Deployment.dependency_key([manifest], 'python-a')
        self.assertNotEqual(initial, deploy.Deployment.dependency_key([manifest], 'python-b'))
        manifest.write_text('two')
        self.assertNotEqual(initial, deploy.Deployment.dependency_key([manifest], 'python-a'))

    def test_python_unsupported_packaging_stops_before_install(self):
        backend = self.python_backend('unsupported')
        with (backend / 'pyproject.toml').open('a') as output:
            output.write('dynamic=["version"]\n')
        job = FakeDeployment(self.c)
        with patch.object(job, 'logged_build_step') as installed:
            with self.assertRaises(deploy.DeploymentError):
                job.prepare_python(backend, 1000, 1000)
        installed.assert_not_called()

    def test_environment_marker_must_be_immutable_valid_and_not_a_link(self):
        env = self.c.environments / 'environment'
        (env / 'bin').mkdir(parents=True)
        (env / 'bin/python').write_text('python')
        marker = env / '.exam-env.json'
        marker.write_text('{"key":"expected"}')
        env.chmod(0o755)
        marker.chmod(0o644)
        original_stat = Path.stat
        def root_stat(path, *args, **kwargs):
            values = list(original_stat(path, *args, **kwargs))
            values[4] = 0  # Simulate controller ownership without host root privileges.
            return deploy.os.stat_result(values)
        with patch.object(Path, 'stat', root_stat):
            self.assertTrue(deploy.Deployment.environment_ready(env, 'expected'))
            self.assertFalse(deploy.Deployment.environment_ready(env, 'other'))
            marker.chmod(0o666)
            self.assertFalse(deploy.Deployment.environment_ready(env, 'expected'))
            marker.chmod(0o644)
            marker.write_text('invalid-json')
            self.assertFalse(deploy.Deployment.environment_ready(env, 'expected'))
            marker.unlink()
            marker.symlink_to(self.c.source / '.env')
            self.assertFalse(deploy.Deployment.environment_ready(env, 'expected'))

    def test_sandbox_only_allows_writes_to_fresh_python_environment(self):
        job = FakeDeployment(self.c)
        job.candidate = self.c.releases / 'candidate'
        job.environment = self.c.environments / 'reused'
        with patch.object(job, 'command', return_value='') as command, \
                patch.object(deploy.subprocess, 'run'):
            job.build_step(self.c.source, ['true'])
            args = command.call_args.args[0]
            writable = [arg for arg in args if arg.startswith('--property=ReadWritePaths=')]
            self.assertEqual(len(writable), 1)
            self.assertNotIn(str(self.c.environments), writable[0])
            job.writable_environment = self.c.environments / 'fresh'
            job.build_step(self.c.source, ['true'])
            writable = [arg for arg in command.call_args.args[0] if arg.startswith('--property=ReadWritePaths=')]
            self.assertEqual(len(writable), 1)
            self.assertIn(str(job.writable_environment), writable[0])
            self.assertNotIn(str(job.environment), writable[0])
            self.assertNotIn(str(self.c.build_home), writable[0])

    def test_prepare_freezes_dependencies_before_executing_app_source(self):
        job = FakeDeployment(self.c)
        job.candidate = self.c.releases / 'candidate'
        job.environment = self.c.environments / 'python'
        job.environment.mkdir()
        order = []
        def unpack(archive, destination):
            (destination / 'backend/alembic/versions').mkdir(parents=True)
            (destination / 'frontend/dist').mkdir(parents=True)
            (destination / 'frontend/dist/index.html').write_text('built')
            (destination / 'frontend/node_modules').mkdir()
        def python_ready(backend, uid, gid):
            order.append('python-ready')
            (backend / '.venv').symlink_to(job.environment, target_is_directory=True)
            return str(backend / '.venv/bin/python')
        def frontend_ready(frontend):
            order.append('frontend-ready')
            return 'key'
        def run(label, cwd, args, *, capture=False):
            order.append('heads' if capture else 'app-import')
            return '["0010"]' if capture else ''
        with patch.object(job, 'as_user'), patch.object(deploy, 'unpack_archive', side_effect=unpack), \
                patch('pwd.getpwnam'), patch.object(job, 'change_owner'), patch.object(deploy.os, 'chown'), \
                patch.object(job, 'freeze_release'), \
                patch.object(job, 'prepare_python', side_effect=python_ready), \
                patch.object(job, 'prepare_frontend', side_effect=frontend_ready), \
                patch.object(job, 'logged_build_step', side_effect=run):
            deploy.Deployment.prepare(job)
        self.assertEqual(order, ['python-ready', 'frontend-ready', 'app-import', 'heads'])
        self.assertFalse((job.candidate / '.build-home').exists())
        self.assertFalse((job.candidate / 'frontend/node_modules').exists())

    def test_frontend_reuse_is_copy_not_install_or_shared_write(self):
        job = FakeDeployment(self.c)
        job.previous = self.c.releases / 'previous'
        old = job.previous / '.node-dependencies'
        (old / '.bin').mkdir(parents=True)
        (old / 'package').mkdir()
        (old / 'package/tool').write_text('original')
        (old / '.bin/tool').symlink_to('../package/tool')
        (old / '.package-lock.json').write_text('{}')
        (job.previous / '.exam-release.json').write_text(json.dumps({'frontend_dependencies_key': 'same'}))
        frontend = self.c.releases / 'candidate/frontend'
        frontend.mkdir(parents=True)
        calls = []
        def build(label, cwd, args, **kwargs):
            calls.append(args)
            if args[0] == 'cp':
                subprocess.run(args, check=True)
            return ''
        with patch.object(deploy.os, 'chown'), patch.object(job, 'freeze_release'), \
                patch.object(job, 'frontend_dependency_key', return_value='same'), \
                patch.object(job, 'logged_build_step', side_effect=build):
            self.assertEqual(job.prepare_frontend(frontend), 'same')
        self.assertEqual([args[0] for args in calls], ['cp', 'npm'])
        self.assertEqual(calls[-1], ['npm', 'run', 'build'])
        (frontend / 'node_modules/package/tool').write_text('candidate')
        self.assertEqual((old / 'package/tool').read_text(), 'original')
        self.assertEqual((frontend.parent / '.node-dependencies/package/tool').read_text(), 'original')
        self.assertTrue((frontend / 'node_modules/.bin/tool').is_symlink())

    def test_frontend_invalid_cache_falls_back_to_install(self):
        job = FakeDeployment(self.c)
        job.previous = self.c.releases / 'previous'
        old = job.previous / '.node-dependencies'
        old.mkdir(parents=True)
        (old / '.package-lock.json').write_text('{}')
        (old / 'escape').symlink_to(self.c.source / '.env')
        (job.previous / '.exam-release.json').write_text(json.dumps({'frontend_dependencies_key': 'same'}))
        frontend = self.c.source / 'frontend'
        frontend.mkdir()
        with patch.object(job, 'frontend_dependency_key', return_value='same'), \
                patch.object(job, 'logged_build_step') as build:
            job.prepare_frontend(frontend)
        self.assertEqual(build.call_args_list[0].args[2][:2], ['npm', 'ci'])

    def test_source_dependent_frontend_install_is_not_reused(self):
        frontend = self.c.source / 'frontend'
        frontend.mkdir()
        job = FakeDeployment(self.c)
        for package in ({'scripts': {'postinstall': 'node setup.js'}},
                        {'workspaces': ['packages/*']}, {'dependencies': {'local': 'file:../local'}}):
            with self.subTest(package=package):
                (frontend / 'package.json').write_text(json.dumps(package))
                self.assertEqual(job.frontend_dependency_key(frontend), '')

    def test_environment_pruning_preserves_references_unknown_and_failed_install_cleanup(self):
        job = FakeDeployment(self.c)
        job.previous = self.c.source
        used = self.c.environments / ('a' * 64 + '-used')
        unused = self.c.environments / ('b' * 64 + '-unused')
        unknown = self.c.environments / 'operator-files'
        for path in (used, unused, unknown):
            path.mkdir()
        retained = self.c.releases / 'retained/backend'
        retained.mkdir(parents=True)
        (retained / '.venv').symlink_to(used, target_is_directory=True)
        with patch.object(job, 'environment_ready', return_value=True):
            job.prune_environments()
        self.assertTrue(used.exists())
        self.assertTrue(unknown.exists())
        self.assertFalse(unused.exists())
        job.candidate = self.c.releases / 'failed'
        job.candidate.mkdir()
        job.new_environment = self.c.environments / ('c' * 64 + '-failed')
        job.new_environment.mkdir()
        job.cleanup_candidate()
        self.assertFalse(job.new_environment.exists())
        self.assertTrue(used.exists())


class ArchiveTests(unittest.TestCase):
    def test_unsafe_entries_and_secret_files_rejected(self):
        for name, kind in (('../escape', tarfile.REGTYPE), ('/escape', tarfile.REGTYPE),
                           ('backend/.env', tarfile.REGTYPE), ('backend/.env.production', tarfile.REGTYPE),
                           ('link', tarfile.SYMTYPE), ('device', tarfile.CHRTYPE)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive = root / 'source.tar'
                with tarfile.open(archive, 'w') as output:
                    item = tarfile.TarInfo(name)
                    item.type = kind
                    item.linkname = '/etc/exam/backend.env'
                    output.addfile(item)
                with self.assertRaises(deploy.DeploymentError):
                    deploy.unpack_archive(archive, root / 'out')

    def test_safe_example_file_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'source.tar'
            with tarfile.open(archive, 'w') as output:
                item = tarfile.TarInfo('backend/.env.production.example')
                item.size = 7
                output.addfile(item, io.BytesIO(b'example'))
            deploy.unpack_archive(archive, root / 'out')
            self.assertEqual((root / 'out/backend/.env.production.example').read_text(), 'example')


class ProgressTests(unittest.TestCase):
    def test_monthly_backup_override_replaces_daily_schedule(self):
        bundle = MODULE.parent
        lines = (bundle / 'exam-db-backup-monthly.conf').read_text(encoding='utf-8').splitlines()
        schedules = [line for line in lines if line.startswith('OnCalendar=')]
        self.assertEqual(schedules, ['OnCalendar=', 'OnCalendar=*-*-01 03:20:00 Asia/Seoul'])
        installer = (bundle / 'install.sh').read_text(encoding='utf-8')
        self.assertIn('systemctl disable exam-db-backup.service', installer)
        self.assertIn('systemctl restart exam-db-backup.timer', installer)
        self.assertNotIn('systemctl start exam-db-backup.service', installer)

    def test_build_progress_keeps_captured_output_and_state_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            job = deploy.Deployment(deploy.Config(state=Path(directory)))
            output = io.StringIO()
            with patch.object(deploy.os, 'geteuid', return_value=1000, create=True), \
                    patch.object(job, 'build_step', return_value='["0010"]') as step, \
                    redirect_stdout(output):
                result = job.logged_build_step('3-11 버전 확인', Path(directory),
                                               ['python', 'private-argument'], capture=True)
            self.assertEqual(result, '["0010"]')
            step.assert_called_once_with(Path(directory), ['python', 'private-argument'], capture=True)
            self.assertIn('[3/7][build][running]', output.getvalue())
            self.assertIn('[3/7][완료]', output.getvalue())
            self.assertNotIn('private-argument', output.getvalue())
            record = json.loads((Path(directory) / 'status.json').read_text(encoding='utf-8'))
            self.assertEqual(record['schema_version'], 1)
            self.assertEqual(record['phase'], 'build')
            self.assertEqual(record['status'], 'running')
            self.assertIn('3-11', record['message'])

    def test_failed_build_does_not_print_completion_or_swallow_error(self):
        with tempfile.TemporaryDirectory() as directory:
            job = deploy.Deployment(deploy.Config(state=Path(directory)))
            output = io.StringIO()
            with patch.object(deploy.os, 'geteuid', return_value=1000, create=True), \
                    patch.object(job, 'build_step', side_effect=deploy.DeploymentError('failed')), \
                    redirect_stdout(output), self.assertRaises(deploy.DeploymentError) as failure:
                job.logged_build_step('3-4 Ruff 검사', Path(directory), ['false'])
            self.assertIn('3-4 Ruff 검사', str(failure.exception))
            self.assertEqual(failure.exception.code, 1)
            self.assertIn('3-4 Ruff 검사', output.getvalue())
            self.assertNotIn('[완료]', output.getvalue())


if __name__ == '__main__':
    unittest.main()
