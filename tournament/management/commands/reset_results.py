from django.core.management.base import BaseCommand
from django.db import transaction

from tournament.models import Match
from tournament.services.database_backup import create_database_backup
from tournament.services.knockout_slots import resolve_knockout_slots
from tournament.services.progression_slots import resolve_progression_slots
from tournament.slot_resolution import resolve_group_stage_slots


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

        backup = create_database_backup(command_name='reset_results')
        self.stdout.write(f'Database backup created: {backup.destination}')

        with transaction.atomic():
            matches_reset = Match.objects.count()
            Match.objects.update(
                home_score=None,
                away_score=None,
                status=Match.Status.SCHEDULED,
            )
            progression_result = resolve_progression_slots()
            knockout_result = resolve_knockout_slots()
            direct_fields, direct_matches = resolve_group_stage_slots()

        derived_fields_cleared = (
            progression_result.stale_fields_cleared
            + knockout_result.stale_fields_cleared
        )
        self.stdout.write(self.style.SUCCESS('Results reset successfully.'))
        self.stdout.write(f'Matches reset: {matches_reset}')
        self.stdout.write(
            'Group Stage direct participants restored: '
            f'{direct_fields} field(s) across {direct_matches} match(es).'
        )
        self.stdout.write(
            'Derived Lower/Upper participants cleared: '
            f'{derived_fields_cleared} field(s).'
        )
