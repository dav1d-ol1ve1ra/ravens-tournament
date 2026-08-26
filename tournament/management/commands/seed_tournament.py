from dataclasses import dataclass
from datetime import time

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tournament.models import Group, Match, ScheduleEvent, Team


GROUPS = (
    ('Group A', 'A'),
    ('Group B', 'B'),
)

TEAMS = (
    ('Ravens A', 'Portugal'),
    ('Ravens B', 'Portugal'),
    ('Vulcanense', 'Portugal'),
    ('London Saints', 'United Kingdom'),
    ('London Saints 2', 'United Kingdom'),
    ('Ruddled Raiders', 'United Kingdom'),
    ('To be determined', 'Netherlands'),
    ('Bouncy Badgers', 'Hungary'),
    ('Lord of the Wings', 'United Kingdom'),
)


@dataclass(frozen=True)
class ScheduleSeed:
    day: int
    start_time: time
    end_time: time
    court: str
    event_type: str
    label: str
    phase: str = ''
    home_slot: str = ''
    away_slot: str = ''
    match_code: str = ''
    group_code: str = ''

    @property
    def is_match(self):
        return self.event_type == ScheduleEvent.EventType.MATCH

    @property
    def event_key(self):
        return (
            self.day,
            self.start_time,
            self.end_time,
            self.court,
            self.event_type,
            self.label,
        )

    @property
    def match_key(self):
        return self.phase, self.home_slot, self.away_slot


def event(day, start, end, court, event_type, label):
    return ScheduleSeed(day, start, end, court, event_type, label)


def match(
    day,
    start,
    end,
    court,
    label,
    phase,
    home_slot,
    away_slot,
    *,
    match_code='',
    group_code='',
):
    return ScheduleSeed(
        day,
        start,
        end,
        court,
        ScheduleEvent.EventType.MATCH,
        label,
        phase,
        home_slot,
        away_slot,
        match_code,
        group_code,
    )


SCHEDULE = (
    event(1, time(9, 30), time(10, 0), 'Court 1', 'opening_ceremony', 'Opening Ceremony'),
    event(1, time(9, 30), time(10, 0), 'Court 2', 'opening_ceremony', 'Opening Ceremony'),
    event(1, time(9, 30), time(10, 0), 'Court 3', 'opening_ceremony', 'Opening Ceremony'),
    match(1, time(10, 0), time(11, 5), 'Court 1', 'A1 vs A2', 'group_stage', 'A1', 'A2', group_code='A'),
    match(1, time(10, 0), time(11, 5), 'Court 2', 'A3 vs A4', 'group_stage', 'A3', 'A4', group_code='A'),
    match(1, time(10, 0), time(11, 5), 'Court 3', 'B1 vs B2', 'group_stage', 'B1', 'B2', group_code='B'),
    match(1, time(11, 5), time(12, 10), 'Court 1', 'A1 vs A3', 'group_stage', 'A1', 'A3', group_code='A'),
    match(1, time(11, 5), time(12, 10), 'Court 2', 'A2 vs A5', 'group_stage', 'A2', 'A5', group_code='A'),
    match(1, time(11, 5), time(12, 10), 'Court 3', 'B3 vs B4', 'group_stage', 'B3', 'B4', group_code='B'),
    match(1, time(12, 10), time(13, 15), 'Court 1', 'A1 vs A4', 'group_stage', 'A1', 'A4', group_code='A'),
    match(1, time(12, 10), time(13, 15), 'Court 2', 'A3 vs A5', 'group_stage', 'A3', 'A5', group_code='A'),
    match(1, time(12, 10), time(13, 15), 'Court 3', 'B1 vs B3', 'group_stage', 'B1', 'B3', group_code='B'),
    event(1, time(13, 15), time(14, 45), 'Court 1', 'lunch', 'Lunch'),
    event(1, time(13, 15), time(14, 45), 'Court 2', 'lunch', 'Lunch'),
    event(1, time(13, 15), time(14, 45), 'Court 3', 'lunch', 'Lunch'),
    match(1, time(14, 45), time(15, 50), 'Court 1', 'A2 vs A4', 'group_stage', 'A2', 'A4', group_code='A'),
    match(1, time(14, 45), time(15, 50), 'Court 2', 'A1 vs A5', 'group_stage', 'A1', 'A5', group_code='A'),
    match(1, time(14, 45), time(15, 50), 'Court 3', 'B2 vs B4', 'group_stage', 'B2', 'B4', group_code='B'),
    match(1, time(15, 50), time(16, 55), 'Court 1', 'A2 vs A3', 'group_stage', 'A2', 'A3', group_code='A'),
    match(1, time(15, 50), time(16, 55), 'Court 2', 'A4 vs A5', 'group_stage', 'A4', 'A5', group_code='A'),
    match(1, time(15, 50), time(16, 55), 'Court 3', 'B1 vs B4', 'group_stage', 'B1', 'B4', group_code='B'),
    match(1, time(16, 55), time(18, 0), 'Court 1', 'B2 vs B3', 'group_stage', 'B2', 'B3', group_code='B'),
    event(1, time(16, 55), time(18, 0), 'Court 2', 'free', 'Free / Margin'),
    event(1, time(16, 55), time(18, 0), 'Court 3', 'free', 'Free / Margin'),
    match(2, time(9, 0), time(10, 0), 'Court 1', 'LL-03 — L1 vs L3', 'lower_round_robin', 'L1', 'L3', match_code='LL-03'),
    match(2, time(9, 0), time(10, 0), 'Court 2', 'LL-04 — L2 vs L5', 'lower_round_robin', 'L2', 'L5', match_code='LL-04'),
    match(2, time(9, 0), time(10, 0), 'Court 3', 'LL-05 — L1 vs L4', 'lower_round_robin', 'L1', 'L4', match_code='LL-05'),
    match(2, time(10, 0), time(11, 5), 'Court 1', 'UB-01 — 1A vs 2B', 'upper_semifinal', '1A', '2B', match_code='UB-01'),
    match(2, time(10, 0), time(11, 5), 'Court 2', 'UB-02 — 1B vs 2A', 'upper_semifinal', '1B', '2A', match_code='UB-02'),
    match(2, time(10, 0), time(11, 5), 'Court 3', 'LL-01 — L1 vs L2', 'lower_round_robin', 'L1', 'L2', match_code='LL-01'),
    match(2, time(11, 5), time(12, 5), 'Court 1', 'LL-06 — L3 vs L5', 'lower_round_robin', 'L3', 'L5', match_code='LL-06'),
    match(2, time(11, 5), time(12, 5), 'Court 2', 'LL-07 — L1 vs L5', 'lower_round_robin', 'L1', 'L5', match_code='LL-07'),
    match(2, time(11, 5), time(12, 5), 'Court 3', 'LL-08 — L2 vs L4', 'lower_round_robin', 'L2', 'L4', match_code='LL-08'),
    event(2, time(12, 5), time(13, 35), 'Court 1', 'lunch', 'Lunch'),
    event(2, time(12, 5), time(13, 35), 'Court 2', 'lunch', 'Lunch'),
    event(2, time(12, 5), time(13, 35), 'Court 3', 'lunch', 'Lunch'),
    match(2, time(13, 35), time(14, 35), 'Court 1', 'LL-09 — L2 vs L3', 'lower_round_robin', 'L2', 'L3', match_code='LL-09'),
    match(2, time(13, 35), time(14, 35), 'Court 2', 'LL-10 — L4 vs L5', 'lower_round_robin', 'L4', 'L5', match_code='LL-10'),
    event(2, time(13, 35), time(14, 35), 'Court 3', 'free', 'Free / Margin'),
    match(2, time(14, 35), time(15, 40), 'Court 1', 'UB-03 — Loser UB-01 vs Loser UB-02', 'upper_third_place', 'L-UB-01', 'L-UB-02', match_code='UB-03'),
    match(2, time(14, 35), time(15, 40), 'Court 2', 'UB-04 — Winner UB-01 vs Winner UB-02', 'upper_final', 'W-UB-01', 'W-UB-02', match_code='UB-04'),
    match(2, time(14, 35), time(15, 40), 'Court 3', 'LL-02 — L3 vs L4', 'lower_round_robin', 'L3', 'L4', match_code='LL-02'),
    event(2, time(15, 40), time(16, 10), 'Court 1', 'closing_ceremony', 'Closing Ceremony'),
    event(2, time(15, 40), time(16, 10), 'Court 2', 'closing_ceremony', 'Closing Ceremony'),
    event(2, time(15, 40), time(16, 10), 'Court 3', 'closing_ceremony', 'Closing Ceremony'),
)


class Command(BaseCommand):
    help = 'Seeds the confirmed Ravens Tournament teams and 5+4 schedule.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset-schedule',
            action='store_true',
            help='Delete tournament schedule structure and rebuild the confirmed format.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options['reset_schedule']:
            self._reset_schedule()
        else:
            self._assert_compatible_structure()

        created_teams = self._seed_teams()
        groups_by_code, created_groups = self._seed_groups()
        created_events, created_matches = self._seed_schedule(groups_by_code)

        self.stdout.write(
            self.style.SUCCESS(
                f'Tournament structure now contains {Group.objects.count()} groups, '
                f'{Match.objects.count()} matches, and {ScheduleEvent.objects.count()} '
                f'schedule events. Created {created_teams} team(s), '
                f'{created_groups} group(s), {created_matches} match(es), and '
                f'{created_events} schedule event(s).'
            )
        )

    def _reset_schedule(self):
        match_count = Match.objects.count()
        event_count = ScheduleEvent.objects.count()
        group_count = Group.objects.count()
        assigned_team_count = Team.objects.exclude(group_slot='').count()
        self.stderr.write(
            self.style.WARNING(
                'Resetting tournament structure: removing '
                f'{match_count} match(es), {event_count} schedule event(s), and '
                f'{group_count} group(s); clearing {assigned_team_count} team slot(s). '
                'Team identities, countries, short names, and logos will be preserved.'
            )
        )
        Match.objects.all().delete()
        ScheduleEvent.objects.all().delete()
        Group.objects.all().delete()
        Team.objects.exclude(group_slot='').update(group_slot='')

    def _assert_compatible_structure(self):
        expected_group_codes = {code for _, code in GROUPS}
        existing_group_codes = list(Group.objects.values_list('code', flat=True))
        if (
            any(code not in expected_group_codes for code in existing_group_codes)
            or len(existing_group_codes) != len(set(existing_group_codes))
        ):
            raise CommandError(
                'Existing tournament groups belong to another format. '
                'Run seed_tournament --reset-schedule to replace them explicitly.'
            )

        expected_match_keys = {item.match_key for item in SCHEDULE if item.is_match}
        existing_match_keys = list(
            Match.objects.values_list('phase', 'home_slot', 'away_slot')
        )
        if (
            any(key not in expected_match_keys for key in existing_match_keys)
            or len(existing_match_keys) != len(set(existing_match_keys))
        ):
            raise CommandError(
                'Existing matches belong to another or duplicate schedule. '
                'Run seed_tournament --reset-schedule to replace them explicitly.'
            )

        expected_event_keys = {item.event_key for item in SCHEDULE}
        existing_event_keys = list(
            ScheduleEvent.objects.values_list(
                'day', 'start_time', 'end_time', 'court', 'event_type', 'label'
            )
        )
        if (
            any(key not in expected_event_keys for key in existing_event_keys)
            or len(existing_event_keys) != len(set(existing_event_keys))
        ):
            raise CommandError(
                'Existing schedule events belong to another or duplicate schedule. '
                'Run seed_tournament --reset-schedule to replace them explicitly.'
            )

    def _seed_teams(self):
        created_count = 0
        for name, country in TEAMS:
            _, created = Team.objects.get_or_create(
                name=name,
                defaults={'country': country},
            )
            created_count += created
        return created_count

    def _seed_groups(self):
        groups_by_code = {}
        created_count = 0
        for name, code in GROUPS:
            group, created = Group.objects.update_or_create(
                code=code,
                defaults={'name': name},
            )
            groups_by_code[code] = group
            created_count += created
        return groups_by_code, created_count

    def _seed_schedule(self, groups_by_code):
        created_events = 0
        created_matches = 0
        for item in SCHEDULE:
            schedule_event, event_created = ScheduleEvent.objects.get_or_create(
                day=item.day,
                start_time=item.start_time,
                end_time=item.end_time,
                court=item.court,
                event_type=item.event_type,
                label=item.label,
            )
            created_events += event_created
            if not item.is_match:
                continue

            match_object, match_created = Match.objects.get_or_create(
                phase=item.phase,
                home_slot=item.home_slot,
                away_slot=item.away_slot,
                defaults={
                    'day': item.day,
                    'start_time': item.start_time,
                    'court': item.court,
                    'schedule_event': schedule_event,
                    'match_code': item.match_code,
                    'group': groups_by_code.get(item.group_code),
                },
            )
            created_matches += match_created
            if not match_created:
                structural_values = {
                    'day': item.day,
                    'start_time': item.start_time,
                    'court': item.court,
                    'schedule_event': schedule_event,
                    'match_code': item.match_code,
                    'group': groups_by_code.get(item.group_code),
                }
                changed_fields = []
                for field, value in structural_values.items():
                    if getattr(match_object, field) != value:
                        setattr(match_object, field, value)
                        changed_fields.append(field)
                if changed_fields:
                    match_object.save(update_fields=changed_fields)

        return created_events, created_matches
