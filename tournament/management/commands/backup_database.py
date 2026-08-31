from django.core.management.base import BaseCommand

from tournament.services.database_backup import create_database_backup


class Command(BaseCommand):
    help = 'Create a timestamped backup of the configured SQLite database.'

    def handle(self, *args, **options):
        backup = create_database_backup()
        self.stdout.write(
            self.style.SUCCESS(
                f'Backed up database from {backup.source} to {backup.destination}'
            )
        )
