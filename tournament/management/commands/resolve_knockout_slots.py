from django.core.management.base import BaseCommand

from tournament.services.knockout_slots import resolve_knockout_slots


class Command(BaseCommand):
    help = 'Resolves winner/loser symbolic slots from finished knockout matches.'

    def handle(self, *args, **options):
        result = resolve_knockout_slots()

        self.stdout.write('Resolved slots:')
        if result.resolved_slots:
            for slot, team in result.resolved_slots.items():
                self.stdout.write(f'  {slot}: {team.name}')
        else:
            self.stdout.write('  None')

        self.stdout.write('Unresolved slots:')
        if result.unresolved_slots:
            for slot, reason in result.unresolved_slots.items():
                self.stdout.write(f'  {slot}: {reason}')
        else:
            self.stdout.write('  None')

        self.stdout.write(
            self.style.SUCCESS(
                f'Updated {result.fields_updated} field(s) across '
                f'{result.matches_updated} match(es); cleared '
                f'{result.stale_fields_cleared} stale assignment(s).'
            )
        )
