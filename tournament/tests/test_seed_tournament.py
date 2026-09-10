from datetime import time
from io import StringIO
from itertools import combinations

from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth import get_user_model
from django.db.models import F
from django.test import TestCase
from django.urls import reverse

from tournament.models import Group, Match, ScheduleEvent, Team
from tournament.services.knockout_slots import resolve_knockout_slots
from tournament.services.progression_slots import resolve_progression_slots
from tournament.slot_resolution import resolve_group_stage_slots


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
                'London Saints A',
                'London Saints B',
                'Ruddled Raiders',
                'Wild Cards',
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
        self.assertEqual(Match.objects.filter(phase='lower_league').count(), 10)
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
            for match in Match.objects.filter(phase='lower_league')
        }

        self.assertEqual(
            lower_matches,
            {
                'LL-01': ('4A', '5A'),
                'LL-02': ('3A', '3B'),
                'LL-03': ('3A', '4A'),
                'LL-04': ('5A', '4B'),
                'LL-05': ('4A', '3B'),
                'LL-06': ('3A', '4B'),
                'LL-07': ('4A', '4B'),
                'LL-08': ('5A', '3B'),
                'LL-09': ('3A', '5A'),
                'LL-10': ('3B', '4B'),
            },
        )
        self.assertEqual(
            {
                frozenset(pair)
                for pair in lower_matches.values()
            },
            {
                frozenset(pair)
                for pair in combinations(('3A', '4A', '5A', '3B', '4B'), 2)
            },
        )

    def test_schedule_events_store_expected_variable_times(self):
        expected_events = (
            (1, time(9, 30), time(10, 0), 'opening_ceremony'),
            (1, time(10, 0), time(11, 5), 'match'),
            (1, time(13, 15), time(14, 45), 'lunch'),
            (1, time(16, 55), time(18, 0), 'free'),
            (2, time(9, 0), time(10, 5), 'match'),
            (2, time(10, 5), time(11, 10), 'match'),
            (2, time(12, 10), time(13, 35), 'lunch'),
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

    def test_final_saturday_schedule_includes_the_delayed_lower_match(self):
        saturday_lower = Match.objects.get(match_code='LL-01')

        self.assertEqual(
            (
                saturday_lower.day,
                saturday_lower.start_time,
                saturday_lower.schedule_event.end_time,
                saturday_lower.court,
                saturday_lower.home_slot,
                saturday_lower.away_slot,
                saturday_lower.referee_slot,
            ),
            (1, time(17, 10), time(18), 'Court 2', '4A', '5A', '3A'),
        )
        self.assertTrue(
            Match.objects.filter(
                match_code='GS-B-06',
                day=1,
                start_time=time(16, 55),
                court='Court 1',
                referee_slot='1A',
            ).exists()
        )
        self.assertTrue(
            ScheduleEvent.objects.filter(
                day=1,
                start_time=time(16, 55),
                end_time=time(18),
                court='Court 3',
                event_type=ScheduleEvent.EventType.FREE,
                label='Free / Buffer',
            ).exists()
        )

    def test_final_saturday_match_schedule(self):
        expected = {
            'GS-A-01': (time(10), 'Court 1', 'A1', 'A2', 'B3'),
            'GS-A-02': (time(10), 'Court 2', 'A3', 'A4', 'B4'),
            'GS-B-01': (time(10), 'Court 3', 'B1', 'B2', 'A5'),
            'GS-A-03': (time(11, 5), 'Court 1', 'A1', 'A3', 'B1'),
            'GS-A-04': (time(11, 5), 'Court 2', 'A2', 'A5', 'B2'),
            'GS-B-02': (time(11, 5), 'Court 3', 'B3', 'B4', 'A4'),
            'GS-A-05': (time(12, 10), 'Court 1', 'A1', 'A4', 'B2'),
            'GS-A-06': (time(12, 10), 'Court 2', 'A3', 'A5', 'B4'),
            'GS-B-03': (time(12, 10), 'Court 3', 'B1', 'B3', 'A2'),
            'GS-A-07': (time(14, 45), 'Court 1', 'A2', 'A4', 'B1'),
            'GS-A-08': (time(14, 45), 'Court 2', 'A1', 'A5', 'B3'),
            'GS-B-04': (time(14, 45), 'Court 3', 'B2', 'B4', 'A3'),
            'GS-A-09': (time(15, 50), 'Court 1', 'A2', 'A3', 'B2'),
            'GS-A-10': (time(15, 50), 'Court 2', 'A4', 'A5', 'B3'),
            'GS-B-05': (time(15, 50), 'Court 3', 'B1', 'B4', 'A1'),
            'GS-B-06': (time(16, 55), 'Court 1', 'B2', 'B3', '1A'),
            'LL-01': (time(17, 10), 'Court 2', '4A', '5A', '3A'),
        }

        actual = {
            match.match_code: (
                match.start_time,
                match.court,
                match.home_slot,
                match.away_slot,
                match.referee_slot,
            )
            for match in Match.objects.filter(day=1)
        }

        self.assertEqual(actual, expected)

    def test_final_sunday_lower_schedule(self):
        expected = {
            'LL-03': (time(9), time(10, 5), 'Court 1', '3A', '4A', '2A'),
            'LL-08': (time(9), time(10, 5), 'Court 2', '5A', '3B', '1B'),
            'LL-09': (time(10, 5), time(11, 10), 'Court 1', '3A', '5A', '1A'),
            'LL-10': (time(10, 5), time(11, 10), 'Court 2', '3B', '4B', '4A'),
            'LL-02': (time(11, 10), time(12, 10), 'Court 1', '3A', '3B', '1A'),
            'LL-07': (time(11, 10), time(12, 10), 'Court 2', '4A', '4B', '5A'),
            'LL-05': (time(13, 35), time(14, 35), 'Court 1', '4A', '3B', 'W-UB-01'),
            'LL-06': (time(13, 35), time(14, 35), 'Court 2', '3A', '4B', 'W-UB-02'),
            'LL-04': (time(14, 35), time(15, 40), 'Court 1', '5A', '4B', '3B'),
        }

        for code, details in expected.items():
            with self.subTest(code=code):
                match = Match.objects.select_related('schedule_event').get(
                    match_code=code
                )
                self.assertEqual(
                    (
                        match.start_time,
                        match.schedule_event.end_time,
                        match.court,
                        match.home_slot,
                        match.away_slot,
                        match.referee_slot,
                    ),
                    details,
                )

    def test_final_upper_times_courts_and_referees(self):
        expected = {
            'UB-01': (time(9), time(10, 5), 'Court 3', '4B'),
            'UB-02': (time(10, 5), time(11, 10), 'Court 3', '2B'),
            'UB-03': (time(13, 35), time(14, 35), 'Court 3', '5A'),
            'UB-04': (time(14, 35), time(15, 40), 'Court 3', '4A'),
        }

        for code, details in expected.items():
            with self.subTest(code=code):
                match = Match.objects.select_related('schedule_event').get(
                    match_code=code
                )
                self.assertEqual(
                    (
                        match.start_time,
                        match.schedule_event.end_time,
                        match.court,
                        match.referee_slot,
                    ),
                    details,
                )

    def test_semifinal_winners_resolve_outcome_dependent_referees(self):
        teams = list(Team.objects.order_by('pk')[:4])
        ub_01 = Match.objects.get(match_code='UB-01')
        ub_01.home_team, ub_01.away_team = teams[0], teams[1]
        ub_01.home_score, ub_01.away_score = 7, 4
        ub_01.status = Match.Status.FINISHED
        ub_01.save(
            update_fields=[
                'home_team', 'away_team', 'home_score', 'away_score', 'status'
            ]
        )
        ub_02 = Match.objects.get(match_code='UB-02')
        ub_02.home_team, ub_02.away_team = teams[2], teams[3]
        ub_02.home_score, ub_02.away_score = 3, 6
        ub_02.status = Match.Status.FINISHED
        ub_02.save(
            update_fields=[
                'home_team', 'away_team', 'home_score', 'away_score', 'status'
            ]
        )

        resolve_knockout_slots()

        self.assertEqual(Match.objects.get(match_code='LL-05').referee_team, teams[0])
        self.assertEqual(Match.objects.get(match_code='LL-06').referee_team, teams[3])

    def test_saturday_ranking_referees_resolve_after_group_a_completes(self):
        teams = list(Team.objects.order_by('pk'))
        for position, team in enumerate(teams, start=1):
            team.group_slot = f'A{position}' if position <= 5 else f'B{position - 5}'
        Team.objects.bulk_update(teams, ['group_slot'])
        resolve_group_stage_slots()

        Match.objects.filter(phase='group_stage', group__code='A').update(
            home_score=2,
            away_score=0,
            status=Match.Status.FINISHED,
        )
        resolve_progression_slots()

        self.assertEqual(
            Match.objects.get(match_code='GS-B-06').referee_team,
            teams[0],
        )
        self.assertEqual(
            Match.objects.get(match_code='LL-01').referee_team,
            teams[2],
        )

    def test_public_schedule_keeps_overlapping_saturday_rows_distinct(self):
        list_response = self.client.get(reverse('schedule'))
        courts_response = self.client.get(f'{reverse("schedule")}?view=courts')

        self.assertContains(list_response, '16:55&ndash;18:00', html=False)
        self.assertContains(list_response, '17:10&ndash;18:00', html=False)
        saturday = next(
            day for day in courts_response.context['court_days'] if day['number'] == 1
        )
        late_rows = {
            row['start_time']: row
            for row in saturday['rows']
            if row['start_time'] in (time(16, 55), time(17, 10))
        }

        self.assertEqual(set(late_rows), {time(16, 55), time(17, 10)})
        self.assertEqual(late_rows[time(16, 55)]['cells'][0].match.match_code, 'GS-B-06')
        self.assertIsNone(late_rows[time(16, 55)]['cells'][1])
        self.assertEqual(late_rows[time(17, 10)]['cells'][1].match.match_code, 'LL-01')
        self.assertIsNone(late_rows[time(17, 10)]['cells'][0])

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

    def test_referee_slots_are_seeded_but_teams_remain_unresolved(self):
        self.assertEqual(Match.objects.filter(referee_slot='').count(), 0)
        self.assertEqual(Match.objects.filter(referee_team__isnull=True).count(), 30)

    def test_upper_dependencies_reference_semifinal_outcomes(self):
        third_place = Match.objects.get(match_code='UB-03')
        final = Match.objects.get(match_code='UB-04')

        self.assertEqual(third_place.home_source_match.match_code, 'UB-01')
        self.assertEqual(third_place.home_source_outcome, Match.ParticipantOutcome.LOSER)
        self.assertEqual(third_place.away_source_match.match_code, 'UB-02')
        self.assertEqual(third_place.away_source_outcome, Match.ParticipantOutcome.LOSER)
        self.assertEqual(final.home_source_match.match_code, 'UB-01')
        self.assertEqual(final.home_source_outcome, Match.ParticipantOutcome.WINNER)
        self.assertEqual(final.away_source_match.match_code, 'UB-02')
        self.assertEqual(final.away_source_outcome, Match.ParticipantOutcome.WINNER)

    def test_named_non_match_events_exist_on_the_expected_days(self):
        self.assertEqual(
            ScheduleEvent.objects.filter(label='Opening Ceremony', day=1).count(), 3
        )
        self.assertEqual(
            ScheduleEvent.objects.filter(label='Lunch Break', day=1).count(), 3
        )
        self.assertEqual(
            ScheduleEvent.objects.filter(label='Lunch Break', day=2).count(), 3
        )
        self.assertEqual(
            ScheduleEvent.objects.filter(label='Closing Ceremony', day=2).count(), 3
        )
        self.assertEqual(
            ScheduleEvent.objects.filter(label='Free / Buffer').count(), 3
        )

    def test_unplayed_groups_leave_progression_slots_unresolved(self):
        result = resolve_progression_slots()
        semifinal = Match.objects.get(match_code='UB-01')

        self.assertIsNone(semifinal.home_team)
        self.assertIsNone(semifinal.away_team)
        self.assertIn('does not have enough assigned teams', result.unresolved_slots['1A'])
        self.assertIn('does not have enough assigned teams', result.unresolved_slots['2B'])

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

    def test_reset_preserves_auth_users(self):
        user_model = get_user_model()
        user = user_model.objects.create_user('organiser', password='test-password')

        call_command(
            'seed_tournament',
            reset_schedule=True,
            stdout=StringIO(),
            stderr=StringIO(),
        )

        self.assertTrue(user_model.objects.filter(pk=user.pk).exists())

    def test_normal_seed_refuses_to_mix_old_format(self):
        Group.objects.create(name='Group C', code='C')

        with self.assertRaisesMessage(CommandError, '--reset'):
            call_command('seed_tournament', stdout=StringIO(), stderr=StringIO())
