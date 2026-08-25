from django.core.management.base import BaseCommand

from tournament.slot_resolution import resolve_group_stage_slots


class Command(BaseCommand):
    help = 'Resolves assigned Day 1 group slots to teams in tournament matches.'

    def handle(self, *args, **options):
        fields_updated, matches_updated = resolve_group_stage_slots()
        self.stdout.write(
            self.style.SUCCESS(
                f'Updated {fields_updated} field(s) across {matches_updated} match(es).'
            )
        )
