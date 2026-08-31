import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError
from django.utils import timezone


@dataclass(frozen=True)
class DatabaseBackup:
    source: Path
    destination: Path


def _reserve_destination(backup_directory):
    timestamp = timezone.localtime(timezone.now()).strftime('%Y-%m-%d_%H%M%S')
    for suffix in range(1000):
        filename = f'db_{timestamp}.sqlite3'
        if suffix:
            filename = f'db_{timestamp}_{suffix}.sqlite3'
        destination = backup_directory / filename
        try:
            destination.touch(exist_ok=False)
        except FileExistsError:
            continue
        return destination

    raise CommandError('Could not reserve a unique backup filename.')


def create_database_backup(command_name='backup_database'):
    """Create a consistent SQLite backup and return its source and destination."""
    database_settings = settings.DATABASES['default']
    if database_settings['ENGINE'] != 'django.db.backends.sqlite3':
        raise CommandError(f'{command_name} only supports SQLite databases.')

    source = Path(database_settings['NAME'])
    if not source.is_file():
        raise CommandError(f'Configured SQLite database was not found: {source}')

    backup_directory = Path(settings.BASE_DIR) / 'backups'
    try:
        backup_directory.mkdir(parents=True, exist_ok=True)
        destination = _reserve_destination(backup_directory)
    except OSError as error:
        raise CommandError(f'Could not prepare backup destination: {error}') from error

    try:
        with (
            closing(sqlite3.connect(source)) as source_connection,
            closing(sqlite3.connect(destination)) as destination_connection,
        ):
            source_connection.backup(destination_connection)
    except sqlite3.Error as error:
        destination.unlink(missing_ok=True)
        raise CommandError(f'Could not create SQLite backup: {error}') from error

    return DatabaseBackup(
        source=source.resolve(),
        destination=destination.resolve(),
    )
