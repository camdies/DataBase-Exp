"""Setup regressions: private config, ownership, read-only checks and graceful IO."""
import io
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import urllib.request

from Setup.modules import configuration as cfg, database, environment, service, diagnostics


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='课程 setup ')
        self.root = Path(self.temp.name)
        self.stack = []
        for name, value in [('ROOT', self.root), ('LOCAL', self.root / 'Setup/.local'),
                            ('LOGS', self.root / 'runtime_logs/setup')]:
            item = patch.object(cfg, name, value)
            item.start()
            self.stack.append(item)

    def tearDown(self):
        for item in reversed(self.stack):
            item.stop()
        self.temp.cleanup()

    def values(self):
        return cfg.new_env(database.url_for('127.0.0.1', 3306, 'test', 'a@b:#%\\中 $() !', 'inventory'))

    def test_private_config_roundtrip_and_special_password(self):
        from sqlalchemy.engine import make_url
        values = self.values()
        cfg.write_env(values)
        self.assertEqual(cfg.read_env(), values)
        self.assertEqual(make_url(values['DATABASE_URL']).password, 'a@b:#%\\中 $() !')
        cfg.write_env(cfg.read_env())
        self.assertEqual(cfg.read_env()['JWT_SECRET'], values['JWT_SECRET'])

    def test_config_does_not_evaluate_shell_syntax(self):
        values = self.values()
        values['ACCESS_LOG_DIR'] = '$(touch bad); %PATH%'
        cfg.write_env(values)
        self.assertEqual(cfg.read_env()['ACCESS_LOG_DIR'], values['ACCESS_LOG_DIR'])
        self.assertFalse((self.root / 'bad').exists())

    def test_duplicate_keys_and_weak_secret_fail_closed(self):
        values = self.values()
        values['JWT_SECRET'] = 'a' * 50
        with self.assertRaises(cfg.SetupError):
            cfg.write_env(values)
        cfg.write_env(self.values())
        with (self.root / '.env').open('a', encoding='utf-8') as output:
            output.write('JWT_SECRET=duplicate\n')
        with self.assertRaises(cfg.SetupError):
            cfg.read_env()

    def test_check_does_not_create_directories(self):
        before = list(self.root.rglob('*'))
        results = environment.check()
        self.assertTrue(any(not item['ok'] for item in results))
        self.assertEqual(before, list(self.root.rglob('*')))

    def test_frontend_missing_asset_is_detected(self):
        dist = self.root / 'frontend/dist'
        dist.mkdir(parents=True)
        (dist / 'index.html').write_text('<script src="/assets/missing.js"></script>', encoding='utf-8')
        with self.assertRaises(cfg.SetupError):
            environment.check_assets()

    def test_process_identity_rejects_pid_reuse_and_command_mismatch(self):
        info = service.process_record(os.getpid())
        self.assertIsNotNone(service.owned_process(info))
        # mysqld changes cwd to its datadir after launch on Linux.
        self.assertIsNotNone(service.owned_process(info | {'cwd': '/old-working-directory'}))
        if 'start_ticks' in info:
            self.assertIsNone(service.owned_process(info | {'start_ticks': '0'}))
            self.assertIsNotNone(service.owned_process(info | {'created': info['created'] - 10}))
            self.assertIsNone(service.owned_process(info | {'boot_id': 'different-boot'}))
        else:
            self.assertIsNone(service.owned_process(info | {'created': info['created'] - 10}))
        self.assertIsNone(service.owned_process(info | {'cmdline': ['unrelated']}))

    def test_stop_does_not_kill_foreign_process(self):
        info = service.process_record(os.getpid()) | {'cmdline': ['unrelated'], 'instance': secrets.token_hex(16)}
        cfg.save_json(cfg.LOCAL / 'service-state.json', info)
        with patch('psutil.Process.kill') as kill:
            service.stop(force=True, timeout=0)
            kill.assert_not_called()

    def test_private_stop_path_rejects_traversal(self):
        with self.assertRaises(cfg.SetupError):
            service.stop_path({'instance': '../not-a-token'})

    def test_wait_stopped_does_not_wait_for_reaping_nonchild_zombie(self):
        with patch.object(service, 'owned_process', return_value=None):
            service.wait_stopped({'pid': 123}, 0)

    def test_busy_port_fails_before_database_or_spawn(self):
        cfg.write_env(self.values())
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            sock.listen()
            cfg.save_json(cfg.LOCAL / 'settings.json', cfg.DEFAULTS | {'port': sock.getsockname()[1]})
            with patch.object(environment, 'check_assets'), patch.object(database, 'verify') as verify, \
                    patch.object(service, 'spawn') as spawn:
                with self.assertRaises(cfg.SetupError):
                    service.start(False)
                verify.assert_not_called()
                spawn.assert_not_called()

    @unittest.skipIf(os.name == 'nt', 'POSIX TIME_WAIT semantics')
    def test_recently_closed_listener_can_restart(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
            listener.listen()
            with socket.create_connection(('127.0.0.1', port)) as client:
                peer, _ = listener.accept()
                peer.sendall(b'x')
                peer.close()
                self.assertEqual(client.recv(1), b'x')
                self.assertEqual(client.recv(1), b'')
        self.assertTrue(environment.port_free('127.0.0.1', port))

    def test_diagnostics_never_exports_raw_exception_or_credentials(self):
        with patch.object(database, 'verify', side_effect=RuntimeError('mysql://secret-password')), \
                patch.object(cfg, 'read_env', return_value=self.values()):
            path = diagnostics.export_report()
        content = path.read_text(encoding='utf-8')
        self.assertNotIn('secret-password', content)
        self.assertNotIn('DATABASE_URL', content)
        self.assertIn('checks', json.loads(content))

    def test_new_database_name_rejects_sql_syntax(self):
        for value in ('db`; DROP DATABASE x', 'db-name', '', 'a' * 49):
            with self.assertRaises(cfg.SetupError):
                database.identifier(value)

    def test_middleware_releases_active_count_when_iterator_close_fails(self):
        class Result:
            def __iter__(self):
                return iter([b'body'])
            def close(self):
                raise RuntimeError('close failed')
        def app(environ, start):
            start('200 OK', [])
            return Result()
        gate = service.DrainMiddleware(app, secrets.token_hex(16))
        with self.assertRaises(RuntimeError):
            list(gate({}, lambda *args: None))
        self.assertEqual(gate.active, 0)

    def test_check_repair_returns_failure_when_user_declines(self):
        import argparse
        from Setup import manager
        with patch.object(manager, 'check', return_value=1), patch.object(manager, 'ask', return_value='N'):
            self.assertEqual(manager.execute(argparse.Namespace(action='check-repair')), 1)

    def test_first_run_starts_existing_managed_database_before_validation(self):
        from Setup import manager
        cfg.write_env(self.values())
        cfg.save_json(cfg.LOCAL / 'settings.json', cfg.DEFAULTS | {'database_mode': 'managed'})
        calls = []
        with patch.object(service, 'owned_process', return_value=None), \
                patch.object(database, 'ensure_managed', side_effect=lambda: calls.append('start')), \
                patch.object(database, 'verify', side_effect=lambda url: calls.append('verify')), \
                patch.object(manager.frontend, 'build', side_effect=lambda: calls.append('build')), \
                patch.object(service, 'start', side_effect=lambda browser: calls.append(('web', browser))):
            manager.configure(first=True, open_browser=False)
        self.assertEqual(calls, ['build', 'start', 'verify', ('web', False)])

    def test_repair_rebuilds_venv_that_inherits_unrelated_system_packages(self):
        venv = self.root / '.venv'
        venv.mkdir()
        (venv / 'pyvenv.cfg').write_text('include-system-site-packages = true\n')
        with patch.object(environment.subprocess, 'run') as run:
            environment.repair()
        self.assertTrue(list(self.root.glob('.venv-old-*')))
        self.assertEqual(run.call_args_list[0].args[0][1:3], ['-m', 'venv'])

    def test_operation_lock_excludes_other_operations(self):
        with cfg.operation_lock():
            with self.assertRaises(cfg.SetupError):
                with cfg.operation_lock():
                    pass

    def test_waitress_finishes_inflight_request_before_stop(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        instance = secrets.token_hex(16)
        cfg.LOCAL.mkdir(parents=True)
        code = '''
import sys, time
from pathlib import Path
from Setup.modules import configuration as cfg, service
cfg.LOCAL = Path(sys.argv[1])
def app(environ, start):
    if environ['PATH_INFO'] == '/slow':
        (cfg.LOCAL / 'accepted').write_text('1')
        time.sleep(1)
    start('200 OK', [('Content-Type', 'text/plain')])
    return [b'complete-body']
service.run_server(app, dict(host='127.0.0.1', port=int(sys.argv[2]), threads=2), sys.argv[3])
'''
        project = Path(__file__).resolve().parents[1]
        child = subprocess.Popen([sys.executable, '-c', code, str(cfg.LOCAL), str(port), instance],
                                 cwd=project, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            value = service.process_record(child.pid) | {'port': port, 'instance': instance}
            for _ in range(100):
                try:
                    service.verify_http(value)
                    break
                except OSError:
                    if child.poll() is not None:
                        self.fail(child.communicate()[1].decode())
                    time.sleep(0.05)
            else:
                self.fail('worker did not start')
            cfg.save_json(cfg.LOCAL / 'service-state.json', value)
            with ThreadPoolExecutor(max_workers=1) as executor:
                def request():
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    with opener.open(f'http://127.0.0.1:{port}/slow', timeout=10) as response:
                        return response.read()
                pending = executor.submit(request)
                for _ in range(100):
                    if (cfg.LOCAL / 'accepted').exists():
                        break
                    time.sleep(0.02)
                self.assertTrue((cfg.LOCAL / 'accepted').exists())
                service.stop(timeout=10)
                self.assertEqual(pending.result(), b'complete-body')
            child.wait(timeout=5)
            self.assertEqual(child.returncode, 0, child.communicate()[1].decode())
            self.assertFalse((cfg.LOCAL / 'service-state.json').exists())
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=5)


if __name__ == '__main__':
    unittest.main()
