from datetime import time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from tournament.models import Match, Team


class ResultsAdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='organiser',
            password='test-password',
        )

    def create_match(self, **overrides):
        values = {
            'day': 1,
            'start_time': time(10, 0),
            'court': 'Court A',
            'phase': 'group_stage',
            'home_slot': 'A1',
            'away_slot': 'A2',
            'referee_slot': 'B3',
        }
        values.update(overrides)
        return Match.objects.create(**values)

    def post_result(self, match, home_score, away_score):
        return self.client.post(
            reverse('results_admin'),
            {
                'match_id': match.pk,
                'home_score': home_score,
                'away_score': away_score,
            },
        )

    def test_unauthenticated_access_redirects_to_login(self):
        response = self.client.get(reverse('results_admin'))

        self.assertRedirects(
            response,
            f'{reverse("login")}?next={reverse("results_admin")}',
        )

    def test_authenticated_organiser_can_save_result(self):
        self.client.force_login(self.user)
        match = self.create_match()

        response = self.post_result(match, 3, 1)

        self.assertRedirects(response, reverse('results_admin'))
        match.refresh_from_db()
        self.assertEqual((match.home_score, match.away_score), (3, 1))

    def test_saving_result_sets_status_to_finished(self):
        self.client.force_login(self.user)
        match = self.create_match()

        self.post_result(match, 2, 2)
        match.refresh_from_db()

        self.assertEqual(match.status, Match.Status.FINISHED)

    def test_finished_result_can_be_corrected(self):
        self.client.force_login(self.user)
        match = self.create_match(
            home_score=2,
            away_score=1,
            status=Match.Status.FINISHED,
        )

        self.post_result(match, 1, 4)
        match.refresh_from_db()

        self.assertEqual((match.home_score, match.away_score), (1, 4))
        self.assertEqual(match.status, Match.Status.FINISHED)

    def test_negative_scores_are_rejected(self):
        self.client.force_login(self.user)
        match = self.create_match()

        response = self.post_result(match, -1, 2)
        match.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(match.home_score)
        self.assertIsNone(match.away_score)
        self.assertEqual(match.status, Match.Status.SCHEDULED)

    def test_final_group_result_triggers_day2_slot_resolution(self):
        self.client.force_login(self.user)
        teams = [
            Team.objects.create(name=f'Team A{position}', group_slot=f'A{position}')
            for position in range(1, 4)
        ]
        self.create_match(
            home_team=teams[0],
            away_team=teams[1],
            home_score=3,
            away_score=0,
            status=Match.Status.FINISHED,
        )
        self.create_match(
            start_time=time(11, 0),
            home_slot='A2',
            away_slot='A3',
            home_team=teams[1],
            away_team=teams[2],
            home_score=2,
            away_score=0,
            status=Match.Status.FINISHED,
        )
        final_group_match = self.create_match(
            start_time=time(12, 0),
            home_slot='A1',
            away_slot='A3',
            home_team=teams[0],
            away_team=teams[2],
        )
        day2_match = self.create_match(
            day=2,
            phase='final_1_3',
            home_slot='1A',
            away_slot='',
            referee_slot='',
        )

        self.post_result(final_group_match, 1, 0)
        day2_match.refresh_from_db()

        self.assertEqual(day2_match.home_team, teams[0])
