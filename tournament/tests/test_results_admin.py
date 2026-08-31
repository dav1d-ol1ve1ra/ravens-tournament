from datetime import time
from itertools import combinations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from tournament.models import Group, Match, Team


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
        if not match.home_team_id or not match.away_team_id:
            match.home_team = match.home_team or Team.objects.create(
                name=f'Home team {match.pk}'
            )
            match.away_team = match.away_team or Team.objects.create(
                name=f'Away team {match.pk}'
            )
            match.save(update_fields=['home_team', 'away_team'])
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

    def test_scheduled_matches_are_the_default_view(self):
        self.client.force_login(self.user)
        scheduled = self.create_match(match_code='GS-A-01')
        finished = self.create_match(
            start_time=time(11, 5),
            match_code='GS-A-02',
            status=Match.Status.FINISHED,
            home_score=2,
            away_score=1,
        )

        response = self.client.get(reverse('results_admin'))

        self.assertContains(response, scheduled.match_code)
        self.assertNotContains(response, finished.match_code)
        self.assertEqual(response.context['selected_status'], Match.Status.SCHEDULED)

    def test_finished_matches_remain_editable(self):
        self.client.force_login(self.user)
        match = self.create_match(
            match_code='GS-A-01',
            home_score=2,
            away_score=1,
            status=Match.Status.FINISHED,
        )
        self.post_result(match, 2, 1)

        response = self.client.get(reverse('results_admin'), {'status': 'finished'})

        self.assertContains(response, 'Finished')
        self.assertContains(response, 'Save Result')
        self.assertContains(response, 'value="2"', html=False)

    def test_unresolved_participants_cannot_receive_result(self):
        self.client.force_login(self.user)
        match = self.create_match(match_code='UB-01')

        response = self.client.post(
            reverse('results_admin'),
            {'match_id': match.pk, 'home_score': 3, 'away_score': 1},
        )
        match.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Participants not determined yet.')
        self.assertEqual(match.status, Match.Status.SCHEDULED)
        self.assertIsNone(match.home_score)
        self.assertIsNone(match.away_score)

    def test_incomplete_score_submission_is_rejected(self):
        self.client.force_login(self.user)
        match = self.create_match()
        match.home_team = Team.objects.create(name='Home')
        match.away_team = Team.objects.create(name='Away')
        match.save(update_fields=['home_team', 'away_team'])

        response = self.client.post(
            reverse('results_admin'),
            {'match_id': match.pk, 'home_score': 3, 'away_score': ''},
        )
        match.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This field is required.')
        self.assertEqual(match.status, Match.Status.SCHEDULED)

    def test_success_feedback_identifies_match_and_result(self):
        self.client.force_login(self.user)
        home = Team.objects.create(name='Ravens A')
        away = Team.objects.create(name='London Saints')
        match = self.create_match(
            match_code='UB-01',
            phase='upper_semifinal',
            home_team=home,
            away_team=away,
        )

        response = self.client.post(
            reverse('results_admin'),
            {'match_id': match.pk, 'home_score': 7, 'away_score': 5},
            follow=True,
        )

        self.assertContains(
            response,
            'UB-01 saved: Ravens A 7–5 London Saints',
        )

    def test_summary_counts_scheduled_and_finished_matches(self):
        self.client.force_login(self.user)
        self.create_match()
        self.create_match(
            start_time=time(11, 5),
            status=Match.Status.FINISHED,
            home_score=1,
            away_score=0,
        )

        response = self.client.get(reverse('results_admin'))

        self.assertEqual(response.context['summary_counts']['scheduled'], 1)
        self.assertEqual(response.context['summary_counts']['finished'], 1)

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

    def test_final_group_result_triggers_progression_slot_resolution(self):
        self.client.force_login(self.user)
        group = Group.objects.create(name='Group A', code='A')
        teams = [
            Team.objects.create(name=f'Team A{position}', group_slot=f'A{position}')
            for position in range(1, 6)
        ]
        pairings = list(combinations(teams, 2))
        for home_team, away_team in pairings[:-1]:
            self.create_match(
                group=group,
                home_slot=home_team.group_slot,
                away_slot=away_team.group_slot,
                home_team=home_team,
                away_team=away_team,
                home_score=3,
                away_score=0,
                status=Match.Status.FINISHED,
            )

        final_home, final_away = pairings[-1]
        final_group_match = self.create_match(
            group=group,
            home_slot=final_home.group_slot,
            away_slot=final_away.group_slot,
            home_team=final_home,
            away_team=final_away,
        )
        upper_match = self.create_match(
            day=2,
            phase='upper_semifinal',
            home_slot='1A',
            away_slot='',
            referee_slot='',
        )

        self.post_result(final_group_match, 3, 0)
        upper_match.refresh_from_db()

        self.assertEqual(upper_match.home_team, teams[0])

    def test_upper_semifinal_results_trigger_knockout_resolution(self):
        self.client.force_login(self.user)
        teams = [Team.objects.create(name=f'Team {index}') for index in range(1, 5)]
        ub_01 = self.create_match(
            day=2,
            phase='upper_semifinal',
            match_code='UB-01',
            home_team=teams[0],
            away_team=teams[1],
        )
        ub_02 = self.create_match(
            day=2,
            phase='upper_semifinal',
            match_code='UB-02',
            home_team=teams[2],
            away_team=teams[3],
        )
        third_place = self.create_match(
            day=2,
            phase='upper_third_place',
            match_code='UB-03',
            home_slot='L-UB-01',
            away_slot='L-UB-02',
            referee_slot='',
        )
        final = self.create_match(
            day=2,
            phase='upper_final',
            match_code='UB-04',
            home_slot='W-UB-01',
            away_slot='W-UB-02',
            referee_slot='',
        )

        self.post_result(ub_01, 8, 5)
        self.post_result(ub_02, 4, 7)
        third_place.refresh_from_db()
        final.refresh_from_db()

        self.assertEqual(
            (third_place.home_team, third_place.away_team),
            (teams[1], teams[2]),
        )
        self.assertEqual((final.home_team, final.away_team), (teams[0], teams[3]))

    def test_result_entry_resolves_explicit_match_dependencies(self):
        self.client.force_login(self.user)
        teams = [Team.objects.create(name=f'Team {index}') for index in range(1, 3)]
        semifinal = self.create_match(
            day=2,
            phase='upper_semifinal',
            match_code='UB-01',
            home_team=teams[0],
            away_team=teams[1],
        )
        final = self.create_match(
            day=2,
            phase='upper_final',
            match_code='UB-04',
            referee_slot='',
            home_source_match=semifinal,
            home_source_outcome=Match.ParticipantOutcome.WINNER,
        )

        self.post_result(semifinal, 8, 5)
        final.refresh_from_db()

        self.assertEqual(final.home_team, teams[0])

    def test_tied_upper_result_is_rejected(self):
        self.client.force_login(self.user)
        teams = [Team.objects.create(name=f'Team {index}') for index in range(1, 3)]
        semifinal = self.create_match(
            day=2,
            phase='upper_semifinal',
            match_code='UB-01',
            home_team=teams[0],
            away_team=teams[1],
        )

        response = self.post_result(semifinal, 5, 5)
        semifinal.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Upper knockout matches cannot finish in a draw.')
        self.assertEqual(semifinal.status, Match.Status.SCHEDULED)
        self.assertIsNone(semifinal.home_score)
        self.assertIsNone(semifinal.away_score)
