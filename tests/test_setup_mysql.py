"""Provisioning against a dedicated MySQL test server; never touches a business DB."""
import os
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import patch
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from Setup.modules import configuration as cfg, database


class SetupMySQLTests(unittest.TestCase):
    def setUp(self):
        self.url = make_url(os.environ['TEST_DATABASE_URL'])
        if self.url.drivername != 'mysql+pymysql' or not self.url.database.endswith('_test'):
            raise RuntimeError('Only a dedicated MySQL *_test connection is permitted')
        self.admin_url = self.url.set(database=None).render_as_string(hide_password=False)
        self.engine = create_engine(self.admin_url)
        self.name = 'setup_regress_' + secrets.token_hex(5) + '_test'
        self.user = 'setup_user_' + secrets.token_hex(5)
        self.secret = secrets.token_urlsafe(24)
        self.temp = tempfile.TemporaryDirectory()
        self.local_patch = patch.object(cfg, 'LOCAL', Path(self.temp.name) / '.local')
        self.local_patch.start()

    def tearDown(self):
        with self.engine.begin() as conn:
            conn.exec_driver_sql(f'DROP DATABASE IF EXISTS `{self.name}`')
            hosts = conn.execute(text('SELECT Host FROM mysql.user WHERE User=:user'), {'user': self.user}).scalars().all()
            for host in hosts:
                conn.exec_driver_sql('DROP USER %s@%s', (self.user, host))
        self.engine.dispose()
        self.local_patch.stop()
        self.temp.cleanup()

    def test_restore_counts_passwords_permissions_and_repeat_refusal(self):
        from backend.app import create_app
        from tools.manage import counts
        app_url = database.initialize(self.admin_url, self.name, self.user, self.secret,
                                      'admin-test-password', 'clerk-test-password')
        database.verify(app_url)
        engine = create_engine(app_url)
        try:
            before = counts(engine)
            self.assertEqual(before['total'], 106005)
            with engine.connect() as conn:
                self.assertEqual(str(conn.exec_driver_sql('SELECT price FROM product WHERE id=1').scalar()), '10.07')
                self.assertEqual(conn.exec_driver_sql('SELECT role FROM account WHERE username=\'admin\'').scalar(), 'admin')
                with self.assertRaises(DBAPIError):
                    conn.exec_driver_sql('CREATE TABLE forbidden_table (id INT)')
            app = create_app(engine, secrets.token_urlsafe(48), self.temp.name)
            try:
                for role in ('admin', 'clerk'):
                    response = app.test_client().post('/api/login', json={'username': role, 'password': role + '-test-password'})
                    self.assertEqual(response.status_code, 200)
            finally:
                app.extensions['access_log_handler'].close()
            with self.assertRaises(cfg.SetupError):
                database.initialize(self.admin_url, self.name, self.user, self.secret,
                                    'admin-test-password', 'clerk-test-password')
            self.assertEqual(counts(engine), before)
        finally:
            engine.dispose()

    def test_import_failure_is_recorded_and_partial_schema_preserved(self):
        root = Path(self.temp.name) / 'code'
        root.mkdir()
        data = root.parent / 'data'
        data.mkdir()
        (data / 'schema_mysql.sql').write_text('CREATE TABLE partial (id INT);', encoding='utf-8')
        (data / 'backup_mysql.sql').write_text('INSERT INTO missing_table VALUES (1);', encoding='utf-8')
        with patch.object(cfg, 'ROOT', root):
            with self.assertRaises(Exception):
                database.initialize(self.admin_url, self.name, self.user, self.secret,
                                    'admin-test-password', 'clerk-test-password')
        self.assertEqual(cfg.read_json(cfg.LOCAL / 'install-state.json')['phase'], 'needs-review')
        with self.engine.connect() as conn:
            self.assertEqual(conn.exec_driver_sql(f'SELECT COUNT(*) FROM `{self.name}`.partial').scalar(), 0)


if __name__ == '__main__':
    unittest.main()
