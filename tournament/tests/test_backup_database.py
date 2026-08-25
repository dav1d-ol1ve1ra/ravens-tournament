import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase


class BackupDatabaseCommandTests(SimpleTestCase):
    def test_creates_a_timestamped_copy_of_configured_sqlite_database(self):
        with TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            source = temporary_path / 'source.sqlite3'
            with closing(sqlite3.connect(source)) as connection:
                connection.execute('CREATE TABLE test_data (value TEXT)')
                connection.execute("INSERT INTO test_data VALUES ('original')")
                connection.commit()

            database_settings = {
                'default': {
                    'ENGINE': 'django.db.backends.sqlite3',
                    'NAME': source,
                }
            }
            with self.settings(BASE_DIR=temporary_path, DATABASES=database_settings):
                call_command('backup_database', verbosity=0)

            backups = list((temporary_path / 'backups').glob('db_*.sqlite3'))
            self.assertEqual(len(backups), 1)
            with closing(sqlite3.connect(backups[0])) as connection:
                self.assertEqual(
                    connection.execute('SELECT value FROM test_data').fetchone()[0],
                    'original',
                )
            with closing(sqlite3.connect(source)) as connection:
                self.assertEqual(
                    connection.execute('SELECT value FROM test_data').fetchone()[0],
                    'original',
                )

    def test_fails_for_a_non_sqlite_database(self):
        database_settings = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': 'tournament',
            }
        }
        with self.settings(DATABASES=database_settings):
            with self.assertRaisesMessage(
                CommandError,
                'backup_database only supports SQLite databases.',
            ):
                call_command('backup_database', verbosity=0)
