from dataclasses import dataclass
from datetime import time
from itertools import combinations

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
    ('London Saints A', 'England'),
    ('London Saints B', 'England'),
    ('Ruddled Raiders', 'United Kingdom'),
    ('Wild Cards', 'Netherlands'),
    ('Bouncy Badgers', 'Hungary'),
    ('Lord of the Wings', 'England'),
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
    referee_slot: str = ''
    match_code: str = ''
    group_code: str = ''
    home_source_code: str = ''
    home_source_outcome: str = ''
    away_source_code: str = ''
    away_source_outcome: str = ''

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
    referee_slot,
    match_code,
    *,
    group_code='',
    home_source_code='',
    home_source_outcome='',
    away_source_code='',
    away_source_outcome='',
):
    return ScheduleSeed(
        day=day,
        start_time=start,
        end_time=end,
        court=court,
        event_type=ScheduleEvent.EventType.MATCH,
        label=label,
        phase=phase,
        home_slot=home_slot,
        away_slot=away_slot,
        referee_slot=referee_slot,
        match_code=match_code,
        group_code=group_code,
        home_source_code=home_source_code,
        home_source_outcome=home_source_outcome,
        away_source_code=away_source_code,
        away_source_outcome=away_source_outcome,
    )


SCHEDULE = (
    event(1, time(9, 30), time(10), 'Court 1', 'opening_ceremony', 'Opening Ceremony'),
    event(1, time(9, 30), time(10), 'Court 2', 'opening_ceremony', 'Opening Ceremony'),
    event(1, time(9, 30), time(10), 'Court 3', 'opening_ceremony', 'Opening Ceremony'),
    match(1, time(10), time(11, 5), 'Court 1', 'GS-A-01 — A1 vs A2', 'group_stage', 'A1', 'A2', 'B3', 'GS-A-01', group_code='A'),
    match(1, time(10), time(11, 5), 'Court 2', 'GS-A-02 — A3 vs A4', 'group_stage', 'A3', 'A4', 'B4', 'GS-A-02', group_code='A'),
    match(1, time(10), time(11, 5), 'Court 3', 'GS-B-01 — B1 vs B2', 'group_stage', 'B1', 'B2', 'A5', 'GS-B-01', group_code='B'),
    match(1, time(11, 5), time(12, 10), 'Court 1', 'GS-A-03 — A1 vs A3', 'group_stage', 'A1', 'A3', 'B1', 'GS-A-03', group_code='A'),
    match(1, time(11, 5), time(12, 10), 'Court 2', 'GS-A-04 — A2 vs A5', 'group_stage', 'A2', 'A5', 'B2', 'GS-A-04', group_code='A'),
    match(1, time(11, 5), time(12, 10), 'Court 3', 'GS-B-02 — B3 vs B4', 'group_stage', 'B3', 'B4', 'A4', 'GS-B-02', group_code='B'),
    match(1, time(12, 10), time(13, 15), 'Court 1', 'GS-A-05 — A1 vs A4', 'group_stage', 'A1', 'A4', 'B2', 'GS-A-05', group_code='A'),
    match(1, time(12, 10), time(13, 15), 'Court 2', 'GS-A-06 — A3 vs A5', 'group_stage', 'A3', 'A5', 'B4', 'GS-A-06', group_code='A'),
    match(1, time(12, 10), time(13, 15), 'Court 3', 'GS-B-03 — B1 vs B3', 'group_stage', 'B1', 'B3', 'A2', 'GS-B-03', group_code='B'),
    event(1, time(13, 15), time(14, 45), 'Court 1', 'lunch', 'Lunch Break'),
    event(1, time(13, 15), time(14, 45), 'Court 2', 'lunch', 'Lunch Break'),
    event(1, time(13, 15), time(14, 45), 'Court 3', 'lunch', 'Lunch Break'),
    match(1, time(14, 45), time(15, 50), 'Court 1', 'GS-A-07 — A2 vs A4', 'group_stage', 'A2', 'A4', 'B1', 'GS-A-07', group_code='A'),
    match(1, time(14, 45), time(15, 50), 'Court 2', 'GS-A-08 — A1 vs A5', 'group_stage', 'A1', 'A5', 'B3', 'GS-A-08', group_code='A'),
    match(1, time(14, 45), time(15, 50), 'Court 3', 'GS-B-04 — B2 vs B4', 'group_stage', 'B2', 'B4', 'A3', 'GS-B-04', group_code='B'),
    match(1, time(15, 50), time(16, 55), 'Court 1', 'GS-A-09 — A2 vs A3', 'group_stage', 'A2', 'A3', 'B2', 'GS-A-09', group_code='A'),
    match(1, time(15, 50), time(16, 55), 'Court 2', 'GS-A-10 — A4 vs A5', 'group_stage', 'A4', 'A5', 'B3', 'GS-A-10', group_code='A'),
    match(1, time(15, 50), time(16, 55), 'Court 3', 'GS-B-05 — B1 vs B4', 'group_stage', 'B1', 'B4', 'A1', 'GS-B-05', group_code='B'),
    match(1, time(16, 55), time(18), 'Court 1', 'GS-B-06 — B2 vs B3', 'group_stage', 'B2', 'B3', 'B1', 'GS-B-06', group_code='B'),
    match(1, time(16, 55), time(18), 'Court 2', 'LL-01 — 4A vs 5A', 'lower_league', '4A', '5A', 'B4', 'LL-01'),
    event(1, time(16, 55), time(18), 'Court 3', 'free', 'Free / Buffer'),
    match(2, time(9), time(10, 5), 'Court 1', 'LL-03 — 4A vs 3A', 'lower_league', '4A', '3A', '2A', 'LL-03'),
    match(2, time(9), time(10, 5), 'Court 2', 'LL-04 — 5A vs 4B', 'lower_league', '5A', '4B', '1B', 'LL-04'),
    match(2, time(9), time(10, 5), 'Court 3', 'UB-01 — 1A vs 2B', 'upper_semifinal', '1A', '2B', '3B', 'UB-01'),
    match(2, time(10, 5), time(11, 10), 'Court 1', 'LL-05 — 4A vs 3B', 'lower_league', '4A', '3B', '1A', 'LL-05'),
    match(2, time(10, 5), time(11, 10), 'Court 2', 'LL-06 — 3A vs 4B', 'lower_league', '3A', '4B', '2B', 'LL-06'),
    match(2, time(10, 5), time(11, 10), 'Court 3', 'UB-02 — 1B vs 2A', 'upper_semifinal', '1B', '2A', '5A', 'UB-02'),
    match(2, time(11, 10), time(12, 10), 'Court 1', 'LL-09 — 5A vs 3A', 'lower_league', '5A', '3A', '1A', 'LL-09'),
    match(2, time(11, 10), time(12, 10), 'Court 2', 'LL-10 — 3B vs 4B', 'lower_league', '3B', '4B', '1B', 'LL-10'),
    event(2, time(11, 10), time(12, 10), 'Court 3', 'free', 'Free / Buffer'),
    event(2, time(12, 10), time(13, 35), 'Court 1', 'lunch', 'Lunch Break'),
    event(2, time(12, 10), time(13, 35), 'Court 2', 'lunch', 'Lunch Break'),
    event(2, time(12, 10), time(13, 35), 'Court 3', 'lunch', 'Lunch Break'),
    match(2, time(13, 35), time(14, 35), 'Court 1', 'LL-07 — 4A vs 4B', 'lower_league', '4A', '4B', '2A', 'LL-07'),
    match(2, time(13, 35), time(14, 35), 'Court 2', 'LL-08 — 5A vs 3B', 'lower_league', '5A', '3B', '3A', 'LL-08'),
    event(2, time(13, 35), time(14, 35), 'Court 3', 'free', 'Free / Buffer'),
    match(2, time(14, 35), time(15, 40), 'Court 1', 'UB-03 — Loser UB-01 vs Loser UB-02', 'upper_third_place', 'L-UB-01', 'L-UB-02', '4A', 'UB-03', home_source_code='UB-01', home_source_outcome='loser', away_source_code='UB-02', away_source_outcome='loser'),
    match(2, time(14, 35), time(15, 40), 'Court 2', 'UB-04 — Winner UB-01 vs Winner UB-02', 'upper_final', 'W-UB-01', 'W-UB-02', '4B', 'UB-04', home_source_code='UB-01', home_source_outcome='winner', away_source_code='UB-02', away_source_outcome='winner'),
    match(2, time(14, 35), time(15, 40), 'Court 3', 'LL-02 — 3A vs 3B', 'lower_league', '3A', '3B', '5A', 'LL-02'),
    event(2, time(15, 40), time(16, 10), 'Court 1', 'closing_ceremony', 'Closing Ceremony'),
    event(2, time(15, 40), time(16, 10), 'Court 2', 'closing_ceremony', 'Closing Ceremony'),
    event(2, time(15, 40), time(16, 10), 'Court 3', 'closing_ceremony', 'Closing Ceremony'),
)


def validate_schedule_definition():
    match_items = [item for item in SCHEDULE if item.is_match]
    if len(match_items) != 30:
        raise CommandError('Seed definition must contain exactly 30 matches.')

    match_codes = [item.match_code for item in match_items]
    if any(not code for code in match_codes) or len(match_codes) != len(set(match_codes)):
        raise CommandError('Every seeded match must have a unique match code.')

    for group_code, team_count in (('A', 5), ('B', 4)):
        group_items = [item for item in match_items if item.group_code == group_code]
        slots = [f'{group_code}{position}' for position in range(1, team_count + 1)]
        expected_pairs = {frozenset(pair) for pair in combinations(slots, 2)}
        actual_pairs = {
            frozenset((item.home_slot, item.away_slot)) for item in group_items
        }
        if len(group_items) != len(expected_pairs) or actual_pairs != expected_pairs:
            raise CommandError(f'Group {group_code} seed is not a complete round robin.')

    lower_items = [item for item in match_items if item.phase == 'lower_league']
    lower_slots = ('3A', '4A', '5A', '3B', '4B')
    expected_lower_pairs = {
        frozenset(pair) for pair in combinations(lower_slots, 2)
    }
    actual_lower_pairs = {
        frozenset((item.home_slot, item.away_slot)) for item in lower_items
    }
    if len(lower_items) != 10 or actual_lower_pairs != expected_lower_pairs:
        raise CommandError('Lower League seed is not a complete five-team round robin.')

    upper_items = [item for item in match_items if item.phase.startswith('upper_')]
    if len(upper_items) != 4:
        raise CommandError('Upper bracket seed must contain exactly four matches.')


class Command(BaseCommand):
    help = 'Seeds the confirmed Ravens Tournament development schedule.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            '--reset-schedule',
            dest='reset_schedule',
            action='store_true',
            help='Explicitly delete development schedule data and rebuild it.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        validate_schedule_definition()
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
                'DEVELOPMENT RESET: removing '
                f'{match_count} match(es), {event_count} schedule event(s), and '
                f'{group_count} group(s); clearing {assigned_team_count} team slot(s). '
                'Users, Team records, countries, short names, and logos are preserved.'
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
                'Run seed_tournament --reset locally to replace them explicitly.'
            )

        expected_match_codes = {
            item.match_code for item in SCHEDULE if item.is_match
        }
        existing_match_codes = list(Match.objects.values_list('match_code', flat=True))
        if (
            any(code not in expected_match_codes for code in existing_match_codes)
            or len(existing_match_codes) != len(set(existing_match_codes))
        ):
            raise CommandError(
                'Existing matches belong to another or duplicate schedule. '
                'Run seed_tournament --reset locally to replace them explicitly.'
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
                'Run seed_tournament --reset locally to replace them explicitly.'
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
        matches_by_code = {}
        items_by_code = {}

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

            structural_values = {
                'day': item.day,
                'start_time': item.start_time,
                'court': item.court,
                'schedule_event': schedule_event,
                'phase': item.phase,
                'home_slot': item.home_slot,
                'away_slot': item.away_slot,
                'referee_slot': item.referee_slot,
                'group': groups_by_code.get(item.group_code),
            }
            match_object, match_created = Match.objects.get_or_create(
                match_code=item.match_code,
                defaults=structural_values,
            )
            created_matches += match_created
            if not match_created:
                changed_fields = []
                for field, value in structural_values.items():
                    if getattr(match_object, field) != value:
                        setattr(match_object, field, value)
                        changed_fields.append(field)
                if changed_fields:
                    match_object.save(update_fields=changed_fields)
            matches_by_code[item.match_code] = match_object
            items_by_code[item.match_code] = item

        for match_code, match_object in matches_by_code.items():
            item = items_by_code[match_code]
            dependency_values = {
                'home_source_match': matches_by_code.get(item.home_source_code),
                'home_source_outcome': item.home_source_outcome,
                'away_source_match': matches_by_code.get(item.away_source_code),
                'away_source_outcome': item.away_source_outcome,
            }
            changed_fields = []
            for field, value in dependency_values.items():
                if getattr(match_object, field) != value:
                    setattr(match_object, field, value)
                    changed_fields.append(field)
            if changed_fields:
                match_object.save(update_fields=changed_fields)

        return created_events, created_matches
