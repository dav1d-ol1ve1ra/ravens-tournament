from datetime import time

from django.core.management.base import BaseCommand

from tournament.models import Group, Match, Team


class Command(BaseCommand):
    help = 'Creates the initial Ravens Tournament groups and teams.'

    def handle(self, *args, **options):
        groups = [
            ('Group A', 'A'),
            ('Group B', 'B'),
            ('Group C', 'C'),
        ]
        teams = [
            ('Ravens A', 'Portugal'),
            ('Ravens B', 'Portugal'),
            ('Vulcanense', 'Portugal'),
            ('London Saints A', 'England'),
            ('London Saints B', 'England'),
            ('Ruddled Raiders', 'United Kingdom'),
            ('Wild Cards', 'Netherlands'),
            ('Bouncy Badgers', 'Hungary'),
            ('Lord of the Wings', 'England'),
        ]

        created_groups = 0
        group_by_code = {}
        for name, code in groups:
            group, created = Group.objects.get_or_create(name=name, code=code)
            group_by_code[code] = group
            created_groups += created

        created_teams = 0
        updated_teams = 0
        for name, country in teams:
            team, created = Team.objects.get_or_create(
                name=name,
                defaults={'country': country},
            )
            created_teams += created
            if not created and team.country != country:
                team.country = country
                team.save(update_fields=['country'])
                updated_teams += 1

        schedule = [
            (1, time(10, 0), 'Court A', group_by_code['A'], 'group_stage', 'A1', 'A2', 'B3'),
            (1, time(10, 0), 'Court B', group_by_code['B'], 'group_stage', 'B1', 'B2', 'C3'),
            (1, time(11, 0), 'Court A', group_by_code['C'], 'group_stage', 'C1', 'C2', 'A3'),
            (1, time(11, 0), 'Court B', group_by_code['A'], 'group_stage', 'A2', 'A3', 'B1'),
            (1, time(12, 0), 'Court A', group_by_code['B'], 'group_stage', 'B2', 'B3', 'C1'),
            (1, time(12, 0), 'Court B', group_by_code['C'], 'group_stage', 'C2', 'C3', 'A1'),
            (1, time(13, 0), 'Court A', group_by_code['A'], 'group_stage', 'A1', 'A3', 'B2'),
            (1, time(13, 0), 'Court B', group_by_code['B'], 'group_stage', 'B1', 'B3', 'C2'),
            (1, time(14, 0), 'Court A', group_by_code['C'], 'group_stage', 'C1', 'C3', 'A2'),
            (2, time(9, 0), 'Court A', None, 'final_1_3', '1A', '1B', '3C'),
            (2, time(9, 0), 'Court B', None, 'final_4_6', '2A', '2B', '1C'),
            (2, time(10, 0), 'Court A', None, 'final_7_9', '3A', '3B', '2C'),
            (2, time(10, 0), 'Court B', None, 'final_1_3', '1B', '1C', '3A'),
            (2, time(11, 0), 'Court A', None, 'final_4_6', '2B', '2C', '1A'),
            (2, time(11, 0), 'Court B', None, 'final_7_9', '3B', '3C', '2A'),
            (2, time(12, 0), 'Court A', None, 'final_1_3', '1A', '1C', '3B'),
            (2, time(12, 0), 'Court B', None, 'final_4_6', '2A', '2C', '1B'),
            (2, time(13, 0), 'Court A', None, 'final_7_9', '3A', '3C', '2B'),
        ]

        created_matches = 0
        for day, start_time, court, group, phase, home_slot, away_slot, referee_slot in schedule:
            _, created = Match.objects.update_or_create(
                day=day,
                phase=phase,
                home_slot=home_slot,
                away_slot=away_slot,
                defaults={
                    'start_time': start_time,
                    'court': court,
                    'group': group,
                    'referee_slot': referee_slot,
                },
            )
            created_matches += created

        self.stdout.write(
            self.style.SUCCESS(
                f'Created {created_groups} group(s), {created_teams} team(s), and '
                f'{created_matches} match(es); updated {updated_teams} team country value(s).'
            )
        )
