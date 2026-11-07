import tempfile
import io
from pathlib import Path
import unittest
from unittest.mock import patch
from Setup.modules import configuration as cfg, frontend, service, environment


class FrontendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [patch.object(cfg, key, value) for key, value in
                        [('ROOT', self.root), ('LOCAL', self.root / 'state'), ('LOGS', self.root / 'logs')]]
        for item in self.patches:
            item.start()
        root = self.root / 'frontend'
        (root / 'src').mkdir(parents=True)
        (root / 'package-lock.json').write_text('{}')
        (root / 'src/main.js').write_text('old')
        (root / 'dist').mkdir()
        (root / 'dist/index.html').write_text('old page')

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_failed_build_retains_old_dist(self):
        with patch.object(frontend, 'runtime', return_value=(Path('node'), Path('npm.js'))), \
                patch.object(service, 'owned_process', return_value=None), \
                patch.object(frontend.subprocess, 'run') as run:
            run.return_value.returncode = 1
            with self.assertRaises(cfg.SetupError):
                frontend.build()
        self.assertEqual((self.root / 'frontend/dist/index.html').read_text(), 'old page')

    def test_success_build_records_sources_and_keeps_backup(self):
        def run(*args, **kwargs):
            work = kwargs['cwd']
            if args[0][-1] == 'build':
                (work / 'dist').mkdir()
                (work / 'dist/index.html').write_text('new page')
            from subprocess import CompletedProcess
            return CompletedProcess(args, 0)
        with patch.object(frontend, 'runtime', return_value=(Path('node'), Path('npm.js'))), \
                patch.object(service, 'owned_process', return_value=None), \
                patch.object(frontend.subprocess, 'run', side_effect=run):
            frontend.build()
        frontend.check_fresh()
        self.assertEqual((self.root / 'frontend/dist/index.html').read_text(), 'new page')
        self.assertEqual(len(list((self.root / 'frontend').glob('dist-backup-*'))), 1)
        (self.root / 'frontend/src/main.js').write_text('changed')
        with self.assertRaises(cfg.SetupError):
            frontend.check_fresh()

    def test_live_service_rejects_build_before_install(self):
        with patch.object(service, 'owned_process', return_value=object()), patch.object(frontend, 'runtime') as runtime:
            with self.assertRaises(cfg.SetupError):
                frontend.build()
            runtime.assert_not_called()

    def test_publish_failure_restores_previous_dist(self):
        with self.assertRaises(FileNotFoundError):
            frontend.publish(self.root / 'missing', self.root / 'frontend/dist')
        self.assertEqual((self.root / 'frontend/dist/index.html').read_text(), 'old page')

    def test_missing_staged_asset_rejected(self):
        dist = self.root / 'staged'
        dist.mkdir()
        (dist / 'index.html').write_text('<script src="/assets/missing.js"></script>')
        with self.assertRaises(cfg.SetupError):
            environment.check_assets(dist)

    def test_corrupt_runtime_download_never_extracts_or_runs(self):
        with patch.object(frontend.urllib.request, 'urlopen', return_value=io.BytesIO(b'corrupt')), \
                patch.object(frontend.zipfile, 'ZipFile') as unzip, \
                patch.object(frontend.tarfile, 'open') as untar, \
                patch.object(frontend.subprocess, 'run') as run:
            with self.assertRaisesRegex(cfg.SetupError, '摘要'):
                frontend.runtime(install=True)
            unzip.assert_not_called()
            untar.assert_not_called()
            run.assert_not_called()

    def test_first_run_build_failure_does_not_provision_database(self):
        from Setup import manager
        with patch.object(service, 'owned_process', return_value=None), \
                patch.object(frontend, 'build', side_effect=cfg.SetupError('build failed')), \
                patch.object(manager.database, 'initialize') as initialize, \
                patch.object(manager, 'ask') as ask:
            with self.assertRaises(cfg.SetupError):
                manager.configure(first=True, open_browser=False)
            initialize.assert_not_called()
            ask.assert_not_called()

    def test_check_repair_builds_in_repaired_interpreter(self):
        from Setup import manager
        import argparse
        with patch.object(manager, 'check', return_value=1), \
                patch.object(manager, 'ask', return_value='y'), \
                patch.object(service, 'owned_process', return_value=None), \
                patch.object(environment, 'repair') as repair, \
                patch.object(manager.subprocess, 'run') as run:
            run.return_value.returncode = 0
            self.assertEqual(manager.execute(argparse.Namespace(action='check-repair')), 0)
            repair.assert_called_once()
            self.assertEqual([call.args[0][-1] for call in run.call_args_list if str(call.args[0][0]) == str(environment.python_path())], ['build-frontend', 'check'])
            self.assertEqual(run.call_args.args[0][0], str(environment.python_path()))
