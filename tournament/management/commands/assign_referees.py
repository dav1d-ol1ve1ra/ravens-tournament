from django.core.management.base import BaseCommand

from tournament.services.referee_assignment import assign_referees


def _match_label(match):
    if match.match_code:
        return match.match_code
    return f'Day {match.day} {match.start_time:%H:%M} {match.court}'


class Command(BaseCommand):
    help = 'Assigns balanced, conflict-free referee teams to tournament matches.'

    def handle(self, *args, **options):
        result = assign_referees()

        self.stdout.write('Referee assignments:')
        if result.assignments:
            for assignment in result.assignments:
                self.stdout.write(
                    f'  {_match_label(assignment.match)}: '
                    f'{assignment.team.name} ({assignment.source})'
                )
        else:
            self.stdout.write('  None')

        self.stdout.write('Assignments per team:')
        for team, count in result.team_counts.items():
            self.stdout.write(f'  {team.name}: {count}')

        self.stdout.write('Unresolved matches:')
        if result.unresolved:
            for unresolved in result.unresolved:
                self.stdout.write(
                    self.style.WARNING(
                        f'  {_match_label(unresolved.match)}: {unresolved.reason}'
                    )
                )
        else:
            self.stdout.write('  None')

        if result.warnings:
            self.stdout.write('Protected-assignment warnings:')
            for warning in result.warnings:
                self.stdout.write(self.style.WARNING(f'  {warning}'))

        self.stdout.write(
            self.style.SUCCESS(
                f'Updated {result.fields_updated} referee field(s); cleared '
                f'{result.stale_assignments_cleared} stale automatic assignment(s).'
            )
        )
