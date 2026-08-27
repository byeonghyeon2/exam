"""No production services, secrets, network, or third-party packages are used."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
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
                               current=root / 'current', web=root / 'web', state=root / 'state')
        self.c.source.mkdir()
        (self.c.source / '.env').write_text('DO_NOT_DELETE')
        old_web = root / 'old-web'
        old_web.mkdir()
        (old_web / 'index.html').write_text('old')
        self.c.releases.mkdir()
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
        self.assertEqual(job.calls, ['build', 'schema', 'backup', 'restart', 'health'])
        self.assertEqual(self.state()['status'], 'succeeded')
        self.assertEqual(self.c.current.resolve(), job.candidate)
        self.assertTrue((self.c.source / '.env').exists())

    def test_pre_activation_failures_preserve_service_and_env(self):
        for failure in ('dirty', 'nonfastforward', 'build', 'schema', 'backup'):
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


if __name__ == '__main__':
    unittest.main()
