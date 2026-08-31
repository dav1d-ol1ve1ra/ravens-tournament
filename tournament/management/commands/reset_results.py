from django.core.management.base import BaseCommand

from tournament.services.result_reset import reset_tournament_results


class Command(BaseCommand):
    help = (
        'Clear tournament results and derived progression assignments while '
        'preserving teams, groups, matches, and schedule structure.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--yes',
            action='store_true',
            help='Skip interactive confirmation and reset results immediately.',
        )

    def handle(self, *args, **options):
        if not options['yes']:
            self.stdout.write(
                self.style.WARNING(
                    'WARNING: This will permanently clear all tournament results '
                    'and progression state.'
                )
            )
            self.stdout.write(
                'Team data, group assignments and schedule structure will be preserved.'
            )
            if input('Type RESET to continue: ') != 'RESET':
                self.stdout.write('Reset aborted. No data was changed.')
                return

        result = reset_tournament_results()
        self.stdout.write(f'Database backup created: {result.backup.destination}')
        self.stdout.write(self.style.SUCCESS('Results reset successfully.'))
        self.stdout.write(f'Matches reset: {result.matches_reset}')
        self.stdout.write(
            'Group Stage direct participants restored: '
            f'{result.direct_fields_restored} field(s) across '
            f'{result.direct_matches_updated} match(es).'
        )
        self.stdout.write(
            'Derived Lower/Upper participants cleared: '
            f'{result.derived_fields_cleared} field(s).'
        )
