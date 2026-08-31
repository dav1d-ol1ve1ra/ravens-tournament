from datetime import time
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from tournament.models import (
    Group,
    ManualTiebreakResolution,
    Match,
    ScheduleEvent,
    Team,
)
from tournament.services.database_backup import DatabaseBackup


class ResetResultsPageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='organiser',
            password='test-password',
        )
        self.group_a = Group.objects.create(name='Group A', code='A')
        self.group_b = Group.objects.create(name='Group B', code='B')
        self.a1 = Team.objects.create(
            name='Ravens A',
            country='Portugal',
            logo='team_logos/ravens-a.png',
            group_slot='A1',
        )
        self.a2 = Team.objects.create(name='Team A2', group_slot='A2')
        self.b1 = Team.objects.create(name='Team B1', group_slot='B1')
        self.b2 = Team.objects.create(name='Team B2', group_slot='B2')
        self.event = ScheduleEvent.objects.create(
            day=1,
            start_time=time(10, 0),
            end_time=time(11, 5),
            court='Court 1',
            event_type=ScheduleEvent.EventType.MATCH,
            label='Group Stage match',
        )
        self.group_match = self.create_match(
            match_code='GS-A-01',
            group=self.group_a,
            schedule_event=self.event,
            home_slot='A1',
            away_slot='A2',
            referee_slot='B1',
            home_team=self.b1,
            away_team=self.b2,
            referee_team=self.a2,
        )
        self.lower_match = self.create_match(
            day=2,
            match_code='LL-01',
            phase='lower_league',
            home_slot='3A',
            away_slot='3B',
            home_team=self.a1,
            away_team=self.b1,
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
        self.backup = DatabaseBackup(
            source=Path('db.sqlite3'),
            destination=Path('backups/db_web_test.sqlite3'),
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

    def login(self):
        self.client.force_login(self.user)

    def post_reset(self, *, follow=False):
        with patch(
            'tournament.services.result_reset.create_database_backup',
            return_value=self.backup,
        ) as create_backup:
            response = self.client.post(
                reverse('reset_results'),
                {'confirmation': 'RESET'},
                follow=follow,
            )
        return response, create_backup

    def test_anonymous_access_redirects_to_login(self):
        response = self.client.get(reverse('reset_results'))

        self.assertRedirects(
            response,
            f'{reverse("login")}?next={reverse("reset_results")}',
        )

    def test_authenticated_organiser_can_access_page(self):
        self.login()

        response = self.client.get(reverse('reset_results'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Reset Tournament Results')
        self.assertContains(response, 'Type RESET to confirm')

    def test_reset_navigation_is_private(self):
        public_response = self.client.get(reverse('home'))
        self.assertNotContains(public_response, 'href="/reset-results/"')

        self.login()
        organiser_response = self.client.get(reverse('home'))
        self.assertContains(organiser_response, 'href="/reset-results/"')
        self.assertContains(organiser_response, '>Reset<')

    def test_get_does_not_modify_results(self):
        self.login()

        self.client.get(reverse('reset_results'))
        self.group_match.refresh_from_db()

        self.assertEqual(self.group_match.status, Match.Status.FINISHED)
        self.assertEqual(
            (self.group_match.home_score, self.group_match.away_score),
            (3, 1),
        )

    def test_missing_and_incorrect_confirmation_are_rejected(self):
        self.login()
        with patch('tournament.views.reset_tournament_results') as reset_service:
            missing_response = self.client.post(reverse('reset_results'), {})
            wrong_response = self.client.post(
                reverse('reset_results'),
                {'confirmation': 'reset'},
            )

        self.assertContains(missing_response, 'This field is required.')
        self.assertContains(wrong_response, 'Enter RESET exactly to continue.')
        reset_service.assert_not_called()
        self.group_match.refresh_from_db()
        self.assertEqual(self.group_match.status, Match.Status.FINISHED)

    def test_correct_confirmation_resets_results_and_preserves_structure(self):
        self.login()
        ManualTiebreakResolution.objects.create(
            scope='group:A',
            team_set_signature=f'{self.a1.pk},{self.a2.pk}',
            team_order=[self.a2.pk, self.a1.pk],
        )
        team_count = Team.objects.count()
        group_count = Group.objects.count()
        event_count = ScheduleEvent.objects.count()
        match_count = Match.objects.count()

        response, create_backup = self.post_reset()

        self.assertRedirects(response, reverse('reset_results'))
        create_backup.assert_called_once_with(command_name='reset_results')
        self.assertEqual(Team.objects.count(), team_count)
        self.assertEqual(Group.objects.count(), group_count)
        self.assertEqual(ScheduleEvent.objects.count(), event_count)
        self.assertEqual(Match.objects.count(), match_count)
        self.assertFalse(ManualTiebreakResolution.objects.exists())
        self.assertTrue(ScheduleEvent.objects.filter(pk=self.event.pk).exists())
        self.a1.refresh_from_db()
        self.assertEqual(self.a1.group_slot, 'A1')
        self.assertEqual(self.a1.country, 'Portugal')
        self.assertEqual(self.a1.logo.name, 'team_logos/ravens-a.png')
        for match in Match.objects.all():
            self.assertEqual(match.status, Match.Status.SCHEDULED)
            self.assertIsNone(match.home_score)
            self.assertIsNone(match.away_score)

    def test_direct_participants_restore_and_derived_participants_clear(self):
        self.login()

        self.post_reset()

        self.group_match.refresh_from_db()
        self.assertEqual(
            (
                self.group_match.home_team,
                self.group_match.away_team,
                self.group_match.referee_team,
            ),
            (self.a1, self.a2, self.b1),
        )
        for match in (
            self.lower_match,
            self.ub_01,
            self.ub_02,
            self.ub_03,
            self.ub_04,
        ):
            match.refresh_from_db()
            self.assertIsNone(match.home_team)
            self.assertIsNone(match.away_team)
        self.assertEqual(self.ub_03.home_source_match_id, self.ub_01.pk)
        self.assertEqual(
            self.ub_04.home_source_outcome,
            Match.ParticipantOutcome.WINNER,
        )

    def test_backup_is_attempted_before_results_change(self):
        self.login()

        def verify_pre_reset_state(**kwargs):
            self.group_match.refresh_from_db()
            self.assertEqual(self.group_match.status, Match.Status.FINISHED)
            self.assertEqual(self.group_match.home_score, 3)
            return self.backup

        with patch(
            'tournament.services.result_reset.create_database_backup',
            side_effect=verify_pre_reset_state,
        ) as create_backup:
            self.client.post(
                reverse('reset_results'),
                {'confirmation': 'RESET'},
            )

        create_backup.assert_called_once_with(command_name='reset_results')
        self.group_match.refresh_from_db()
        self.assertEqual(self.group_match.status, Match.Status.SCHEDULED)

    def test_backup_failure_aborts_reset_and_shows_error(self):
        self.login()
        with patch(
            'tournament.services.result_reset.create_database_backup',
            side_effect=CommandError('disk unavailable'),
        ):
            response = self.client.post(
                reverse('reset_results'),
                {'confirmation': 'RESET'},
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'Reset aborted. Database backup failed: disk unavailable',
        )
        self.group_match.refresh_from_db()
        self.assertEqual(self.group_match.status, Match.Status.FINISHED)
        self.assertEqual(self.group_match.home_score, 3)

    def test_success_uses_post_redirect_get_and_names_backup(self):
        self.login()

        response, _ = self.post_reset(follow=True)

        self.assertEqual(response.redirect_chain, [(reverse('reset_results'), 302)])
        self.assertEqual(response.request['REQUEST_METHOD'], 'GET')
        self.assertContains(
            response,
            'Tournament results reset successfully. Backup created: '
            'db_web_test.sqlite3',
        )
