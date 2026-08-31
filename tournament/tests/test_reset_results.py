from datetime import time
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from tournament.models import Group, Match, ScheduleEvent, Team
from tournament.services.database_backup import DatabaseBackup
from tournament.services.lower_standings import calculate_lower_standings
from tournament.services.standings import calculate_group_stage_standings


class ResetResultsCommandTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='organiser',
            password='test-password',
        )
        self.group_a = Group.objects.create(name='Group A', code='A')
        self.group_b = Group.objects.create(name='Group B', code='B')
        self.a1 = Team.objects.create(
            name='Ravens A',
            short_name='RAV-A',
            country='Portugal',
            logo='team_logos/ravens-a.png',
            group_slot='A1',
        )
        self.a2 = Team.objects.create(name='Team A2', group_slot='A2')
        self.b1 = Team.objects.create(name='Team B1', group_slot='B1')
        self.b2 = Team.objects.create(name='Team B2', group_slot='B2')
        self.ceremony = ScheduleEvent.objects.create(
            day=1,
            start_time=time(9, 30),
            end_time=time(10, 0),
            court='Court 1',
            event_type=ScheduleEvent.EventType.OPENING_CEREMONY,
            label='Opening Ceremony',
        )

        self.group_a_match = self.create_match(
            match_code='GS-A-01',
            group=self.group_a,
            home_slot='A1',
            away_slot='A2',
            referee_slot='B1',
            home_team=self.a1,
            away_team=self.a2,
            referee_team=self.b1,
        )
        self.group_b_match = self.create_match(
            match_code='GS-B-01',
            group=self.group_b,
            home_slot='B1',
            away_slot='B2',
            referee_slot='A1',
            home_team=self.b1,
            away_team=self.b2,
            referee_team=self.a1,
        )
        self.lower_match = self.create_match(
            day=2,
            match_code='LL-01',
            phase='lower_league',
            home_slot='3A',
            away_slot='3B',
            referee_slot='4A',
            home_team=self.a1,
            away_team=self.b1,
            referee_team=self.a2,
        )
        self.ub_01 = self.create_match(
            day=2,
            match_code='UB-01',
            phase='upper_semifinal',
            home_slot='1A',
            away_slot='2B',
            home_team=self.a1,
            away_team=self.b2,
        )
        self.ub_02 = self.create_match(
            day=2,
            match_code='UB-02',
            phase='upper_semifinal',
            home_slot='1B',
            away_slot='2A',
            home_team=self.b1,
            away_team=self.a2,
        )
        self.ub_03 = self.create_match(
            day=2,
            match_code='UB-03',
            phase='upper_third_place',
            home_slot='L-UB-01',
            away_slot='L-UB-02',
            home_team=self.b2,
            away_team=self.a2,
            home_source_match=self.ub_01,
            home_source_outcome=Match.ParticipantOutcome.LOSER,
            away_source_match=self.ub_02,
            away_source_outcome=Match.ParticipantOutcome.LOSER,
        )
        self.ub_04 = self.create_match(
            day=2,
            match_code='UB-04',
            phase='upper_final',
            home_slot='W-UB-01',
            away_slot='W-UB-02',
            home_team=self.a1,
            away_team=self.b1,
            home_source_match=self.ub_01,
            home_source_outcome=Match.ParticipantOutcome.WINNER,
            away_source_match=self.ub_02,
            away_source_outcome=Match.ParticipantOutcome.WINNER,
        )

    def create_match(self, **overrides):
        values = {
            'day': 1,
            'start_time': time(10, 0),
            'court': 'Court 1',
            'phase': 'group_stage',
            'home_score': 3,
            'away_score': 1,
            'status': Match.Status.FINISHED,
        }
        values.update(overrides)
        return Match.objects.create(**values)

    def run_reset(self, **options):
        output = StringIO()
        backup = DatabaseBackup(
            source=Path('db.sqlite3'),
            destination=Path('backups/db_test.sqlite3'),
        )
        with patch(
            'tournament.services.result_reset.create_database_backup',
            return_value=backup,
        ) as create_backup:
            call_command('reset_results', stdout=output, **options)
        return output.getvalue(), create_backup

    def test_aborts_unless_confirmation_is_exactly_reset(self):
        with (
            patch('builtins.input', return_value='reset'),
            patch(
                'tournament.services.result_reset.create_database_backup'
            ) as create_backup,
        ):
            output = StringIO()
            call_command('reset_results', stdout=output)

        self.group_a_match.refresh_from_db()
        self.assertEqual(self.group_a_match.status, Match.Status.FINISHED)
        self.assertEqual(self.group_a_match.home_score, 3)
        create_backup.assert_not_called()
        self.assertIn('Reset aborted. No data was changed.', output.getvalue())

    def test_yes_skips_confirmation_and_creates_backup(self):
        with patch('builtins.input') as confirmation:
            output, create_backup = self.run_reset(yes=True)

        confirmation.assert_not_called()
        create_backup.assert_called_once_with(command_name='reset_results')
        self.assertIn(
            'Database backup created: backups\\db_test.sqlite3',
            output.replace('/', '\\'),
        )

    def test_exact_interactive_confirmation_runs_reset(self):
        backup = DatabaseBackup(
            source=Path('db.sqlite3'),
            destination=Path('backups/db_test.sqlite3'),
        )
        with (
            patch('builtins.input', return_value='RESET'),
            patch(
                'tournament.services.result_reset.create_database_backup',
                return_value=backup,
            ),
        ):
            call_command('reset_results', stdout=StringIO())

        self.group_a_match.refresh_from_db()
        self.assertEqual(self.group_a_match.status, Match.Status.SCHEDULED)
        self.assertIsNone(self.group_a_match.home_score)

    def test_resets_results_and_preserves_tournament_structure(self):
        match_count = Match.objects.count()
        group_count = Group.objects.count()
        event_count = ScheduleEvent.objects.count()
        team_count = Team.objects.count()

        self.run_reset(yes=True)

        self.assertEqual(Match.objects.count(), match_count)
        self.assertEqual(Group.objects.count(), group_count)
        self.assertEqual(ScheduleEvent.objects.count(), event_count)
        self.assertTrue(ScheduleEvent.objects.filter(pk=self.ceremony.pk).exists())
        self.assertEqual(Team.objects.count(), team_count)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())
        for match in Match.objects.all():
            self.assertEqual(match.status, Match.Status.SCHEDULED)
            self.assertIsNone(match.home_score)
            self.assertIsNone(match.away_score)

        self.a1.refresh_from_db()
        self.assertEqual(self.a1.name, 'Ravens A')
        self.assertEqual(self.a1.short_name, 'RAV-A')
        self.assertEqual(self.a1.country, 'Portugal')
        self.assertEqual(self.a1.logo.name, 'team_logos/ravens-a.png')
        self.assertEqual(self.a1.group_slot, 'A1')

    def test_restores_direct_slots_and_clears_derived_participants(self):
        self.run_reset(yes=True)

        self.group_a_match.refresh_from_db()
        self.group_b_match.refresh_from_db()
        self.assertEqual(
            (
                self.group_a_match.home_team,
                self.group_a_match.away_team,
                self.group_a_match.referee_team,
            ),
            (self.a1, self.a2, self.b1),
        )
        self.assertEqual(
            (
                self.group_b_match.home_team,
                self.group_b_match.away_team,
                self.group_b_match.referee_team,
            ),
            (self.b1, self.b2, self.a1),
        )

        for match in (self.lower_match, self.ub_01, self.ub_02, self.ub_03, self.ub_04):
            match.refresh_from_db()
            self.assertIsNone(match.home_team)
            self.assertIsNone(match.away_team)
        self.lower_match.refresh_from_db()
        self.assertIsNone(self.lower_match.referee_team)

    def test_preserves_slots_and_explicit_match_dependencies(self):
        definitions = {
            match.pk: (
                match.match_code,
                match.day,
                match.start_time,
                match.court,
                match.phase,
                match.group_id,
                match.schedule_event_id,
                match.home_slot,
                match.away_slot,
                match.referee_slot,
                match.referee_locked,
                match.home_source_match_id,
                match.home_source_outcome,
                match.away_source_match_id,
                match.away_source_outcome,
            )
            for match in Match.objects.all()
        }

        self.run_reset(yes=True)

        for match in Match.objects.all():
            self.assertEqual(
                (
                    match.match_code,
                    match.day,
                    match.start_time,
                    match.court,
                    match.phase,
                    match.group_id,
                    match.schedule_event_id,
                    match.home_slot,
                    match.away_slot,
                    match.referee_slot,
                    match.referee_locked,
                    match.home_source_match_id,
                    match.home_source_outcome,
                    match.away_source_match_id,
                    match.away_source_outcome,
                ),
                definitions[match.pk],
            )

    def test_standings_return_to_zero_and_lower_waiting_state(self):
        self.run_reset(yes=True)

        standings = calculate_group_stage_standings()
        for group_code in ('A', 'B'):
            for row in standings[group_code]:
                self.assertEqual(row.played, 0)
                self.assertEqual(row.ranking_points, 0)
        lower = calculate_lower_standings()
        self.assertFalse(lower.is_resolved)
        self.assertEqual(lower.rows, [])

    def test_running_twice_is_safe(self):
        self.run_reset(yes=True)
        first_state = list(
            Match.objects.order_by('pk').values(
                'status',
                'home_score',
                'away_score',
                'home_team_id',
                'away_team_id',
                'referee_team_id',
            )
        )

        self.run_reset(yes=True)

        self.assertEqual(
            list(
                Match.objects.order_by('pk').values(
                    'status',
                    'home_score',
                    'away_score',
                    'home_team_id',
                    'away_team_id',
                    'referee_team_id',
                )
            ),
            first_state,
        )
