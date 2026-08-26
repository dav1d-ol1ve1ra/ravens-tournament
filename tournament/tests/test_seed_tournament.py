from datetime import time
from io import StringIO
from itertools import combinations

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import F
from django.test import TestCase

from tournament.models import Group, Match, ScheduleEvent, Team
from tournament.services.day2_slots import resolve_day2_slots


class ConfirmedTournamentSeedTests(TestCase):
    def setUp(self):
        call_command(
            'seed_tournament',
            reset_schedule=True,
            stdout=StringIO(),
            stderr=StringIO(),
        )

    def test_seeds_exactly_two_groups(self):
        self.assertEqual(
            list(Group.objects.order_by('code').values_list('name', 'code')),
            [('Group A', 'A'), ('Group B', 'B')],
        )

    def test_seeds_the_nine_existing_team_identities(self):
        self.assertEqual(Team.objects.count(), 9)
        self.assertEqual(
            set(Team.objects.values_list('name', flat=True)),
            {
                'Ravens A',
                'Ravens B',
                'Vulcanense',
                'London Saints',
                'London Saints 2',
                'Ruddled Raiders',
                'To be determined',
                'Bouncy Badgers',
                'Lord of the Wings',
            },
        )

    def test_seeds_complete_group_round_robins(self):
        group_matches = Match.objects.filter(phase='group_stage')

        self.assertEqual(group_matches.filter(group__code='A').count(), 10)
        self.assertEqual(group_matches.filter(group__code='B').count(), 6)
        self.assertEqual(group_matches.count(), 16)
        for code, team_count in (('A', 5), ('B', 4)):
            expected_pairs = {
                frozenset((f'{code}{home}', f'{code}{away}'))
                for home, away in combinations(range(1, team_count + 1), 2)
            }
            actual_pairs = {
                frozenset((home_slot, away_slot))
                for home_slot, away_slot in group_matches.filter(
                    group__code=code
                ).values_list('home_slot', 'away_slot')
            }
            self.assertEqual(actual_pairs, expected_pairs)

    def test_seeds_upper_lower_and_total_match_counts(self):
        self.assertEqual(Match.objects.filter(phase__startswith='upper_').count(), 4)
        self.assertEqual(Match.objects.filter(phase='lower_round_robin').count(), 10)
        self.assertEqual(Match.objects.count(), 30)

    def test_upper_matches_use_symbolic_progression_slots(self):
        upper_matches = {
            match.match_code: (match.phase, match.home_slot, match.away_slot)
            for match in Match.objects.filter(match_code__startswith='UB-')
        }

        self.assertEqual(
            upper_matches,
            {
                'UB-01': ('upper_semifinal', '1A', '2B'),
                'UB-02': ('upper_semifinal', '1B', '2A'),
                'UB-03': ('upper_third_place', 'L-UB-01', 'L-UB-02'),
                'UB-04': ('upper_final', 'W-UB-01', 'W-UB-02'),
            },
        )

    def test_lower_round_robin_contains_the_exact_matches(self):
        lower_matches = {
            match.match_code: (match.home_slot, match.away_slot)
            for match in Match.objects.filter(phase='lower_round_robin')
        }

        self.assertEqual(
            lower_matches,
            {
                'LL-01': ('L1', 'L2'),
                'LL-02': ('L3', 'L4'),
                'LL-03': ('L1', 'L3'),
                'LL-04': ('L2', 'L5'),
                'LL-05': ('L1', 'L4'),
                'LL-06': ('L3', 'L5'),
                'LL-07': ('L1', 'L5'),
                'LL-08': ('L2', 'L4'),
                'LL-09': ('L2', 'L3'),
                'LL-10': ('L4', 'L5'),
            },
        )

    def test_schedule_events_store_expected_variable_times(self):
        expected_events = (
            (1, time(9, 30), time(10, 0), 'opening_ceremony'),
            (1, time(10, 0), time(11, 5), 'match'),
            (1, time(13, 15), time(14, 45), 'lunch'),
            (1, time(16, 55), time(18, 0), 'free'),
            (2, time(9, 0), time(10, 0), 'match'),
            (2, time(10, 0), time(11, 5), 'match'),
            (2, time(12, 5), time(13, 35), 'lunch'),
            (2, time(15, 40), time(16, 10), 'closing_ceremony'),
        )

        for day, start_time, end_time, event_type in expected_events:
            with self.subTest(day=day, start_time=start_time, event_type=event_type):
                self.assertTrue(
                    ScheduleEvent.objects.filter(
                        day=day,
                        start_time=start_time,
                        end_time=end_time,
                        event_type=event_type,
                    ).exists()
                )

    def test_non_match_events_do_not_create_matches(self):
        expected_counts = {
            ScheduleEvent.EventType.OPENING_CEREMONY: 3,
            ScheduleEvent.EventType.LUNCH: 6,
            ScheduleEvent.EventType.CLOSING_CEREMONY: 3,
            ScheduleEvent.EventType.FREE: 3,
        }
        for event_type, expected_count in expected_counts.items():
            with self.subTest(event_type=event_type):
                self.assertEqual(
                    ScheduleEvent.objects.filter(event_type=event_type).count(),
                    expected_count,
                )
                self.assertFalse(
                    Match.objects.filter(schedule_event__event_type=event_type).exists()
                )

    def test_every_match_is_linked_to_matching_event_on_a_valid_court(self):
        self.assertEqual(ScheduleEvent.objects.count(), 45)
        self.assertFalse(Match.objects.filter(schedule_event__isnull=True).exists())
        self.assertFalse(Match.objects.exclude(day=F('schedule_event__day')).exists())
        self.assertFalse(
            Match.objects.exclude(start_time=F('schedule_event__start_time')).exists()
        )
        self.assertFalse(Match.objects.exclude(court=F('schedule_event__court')).exists())
        self.assertFalse(
            Match.objects.exclude(court__in=('Court 1', 'Court 2', 'Court 3')).exists()
        )

    def test_referee_assignments_are_empty(self):
        self.assertEqual(Match.objects.filter(referee_slot='').count(), 30)
        self.assertEqual(Match.objects.filter(referee_team__isnull=True).count(), 30)

    def test_legacy_day2_resolver_does_not_resolve_new_upper_slots(self):
        result = resolve_day2_slots()
        semifinal = Match.objects.get(match_code='UB-01')

        self.assertIsNone(semifinal.home_team)
        self.assertIsNone(semifinal.away_team)
        self.assertIn('disabled', result.unresolved_slots['1A'])
        self.assertIn('disabled', result.unresolved_slots['2B'])

    def test_repeated_non_destructive_seed_does_not_duplicate_or_erase_results(self):
        existing_match = Match.objects.get(match_code='UB-01')
        existing_match.home_score = 3
        existing_match.away_score = 1
        existing_match.status = Match.Status.FINISHED
        existing_match.save(update_fields=['home_score', 'away_score', 'status'])

        call_command('seed_tournament', stdout=StringIO(), stderr=StringIO())
        existing_match.refresh_from_db()

        self.assertEqual(Group.objects.count(), 2)
        self.assertEqual(Match.objects.count(), 30)
        self.assertEqual(ScheduleEvent.objects.count(), 45)
        self.assertEqual((existing_match.home_score, existing_match.away_score), (3, 1))
        self.assertEqual(existing_match.status, Match.Status.FINISHED)


class TournamentSeedResetSafetyTests(TestCase):
    def test_reset_preserves_team_profile_and_clears_only_group_slot(self):
        team = Team.objects.create(
            name='Ravens A',
            short_name='RA',
            country='Custom profile country',
            logo='team_logos/ravens-a.png',
            group_slot='A1',
        )
        original_id = team.id
        Group.objects.create(name='Group C', code='C')
        Match.objects.create(
            day=1,
            start_time=time(10, 0),
            court='Court A',
            phase='group_stage',
            home_slot='C1',
            away_slot='C2',
        )

        call_command(
            'seed_tournament',
            reset_schedule=True,
            stdout=StringIO(),
            stderr=StringIO(),
        )
        team.refresh_from_db()

        self.assertEqual(team.id, original_id)
        self.assertEqual(team.short_name, 'RA')
        self.assertEqual(team.country, 'Custom profile country')
        self.assertEqual(team.logo.name, 'team_logos/ravens-a.png')
        self.assertEqual(team.group_slot, '')

    def test_normal_seed_refuses_to_mix_old_format(self):
        Group.objects.create(name='Group C', code='C')

        with self.assertRaisesMessage(CommandError, '--reset-schedule'):
            call_command('seed_tournament', stdout=StringIO(), stderr=StringIO())
