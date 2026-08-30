from datetime import time

from django.test import TestCase
from django.urls import reverse

from tournament.models import Match, Team
from tournament.services.knockout_slots import resolve_knockout_slots


class UpperPageTests(TestCase):
    def setUp(self):
        self.team_a = Team.objects.create(name='Ravens A')
        self.team_b = Team.objects.create(name='London Saints A')
        self.team_c = Team.objects.create(name='Vulcanense')
        self.team_d = Team.objects.create(name='Bouncy Badgers')
        self.matches = self.create_upper_matches()

    def create_upper_matches(self):
        ub_01 = Match.objects.create(
            day=2,
            start_time=time(9),
            court='Court 1',
            match_code='UB-01',
            phase='upper_semifinal',
            home_slot='1A',
            away_slot='2B',
            referee_slot='3B',
        )
        ub_02 = Match.objects.create(
            day=2,
            start_time=time(10),
            court='Court 2',
            match_code='UB-02',
            phase='upper_semifinal',
            home_slot='1B',
            away_slot='2A',
        )
        ub_03 = Match.objects.create(
            day=2,
            start_time=time(14),
            court='Court 1',
            match_code='UB-03',
            phase='upper_third_place',
            home_slot='L-UB-01',
            away_slot='L-UB-02',
        )
        ub_04 = Match.objects.create(
            day=2,
            start_time=time(14),
            court='Court 2',
            match_code='UB-04',
            phase='upper_final',
            home_slot='W-UB-01',
            away_slot='W-UB-02',
        )
        return {'UB-01': ub_01, 'UB-02': ub_02, 'UB-03': ub_03, 'UB-04': ub_04}

    def test_page_returns_200_and_shows_all_upper_matches(self):
        response = self.client.get(reverse('upper'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Semifinals')
        self.assertContains(response, '3rd Place')
        self.assertContains(response, 'Final')
        for match_code in self.matches:
            self.assertContains(response, match_code)

    def test_unresolved_ranking_and_outcome_labels_are_readable(self):
        response = self.client.get(reverse('upper'))

        for label in (
            '1st Group A',
            '2nd Group B',
            '1st Group B',
            '2nd Group A',
            'Loser UB-01',
            'Loser UB-02',
            'Winner UB-01',
            'Winner UB-02',
        ):
            self.assertContains(response, label)

    def test_resolved_teams_replace_ranking_labels(self):
        semifinal = self.matches['UB-01']
        semifinal.home_team = self.team_a
        semifinal.away_team = self.team_b
        semifinal.save(update_fields=['home_team', 'away_team'])

        response = self.client.get(reverse('upper'))

        self.assertContains(response, 'Ravens A')
        self.assertContains(response, 'London Saints A')
        self.assertNotContains(response, '1st Group A')
        self.assertNotContains(response, '2nd Group B')

    def test_finished_semifinal_scores_and_downstream_participants_display(self):
        ub_01 = self.matches['UB-01']
        ub_01.home_team = self.team_a
        ub_01.away_team = self.team_b
        ub_01.home_score = 8
        ub_01.away_score = 5
        ub_01.status = Match.Status.FINISHED
        ub_01.save(
            update_fields=['home_team', 'away_team', 'home_score', 'away_score', 'status']
        )
        ub_02 = self.matches['UB-02']
        ub_02.home_team = self.team_c
        ub_02.away_team = self.team_d
        ub_02.home_score = 3
        ub_02.away_score = 6
        ub_02.status = Match.Status.FINISHED
        ub_02.save(
            update_fields=['home_team', 'away_team', 'home_score', 'away_score', 'status']
        )

        resolve_knockout_slots()
        self.matches['UB-03'].refresh_from_db()
        self.matches['UB-04'].refresh_from_db()
        response = self.client.get(reverse('upper'))

        self.assertEqual(
            (self.matches['UB-03'].home_team, self.matches['UB-03'].away_team),
            (self.team_b, self.team_c),
        )
        self.assertEqual(
            (self.matches['UB-04'].home_team, self.matches['UB-04'].away_team),
            (self.team_a, self.team_d),
        )
        self.assertContains(response, '8&ndash;5', html=False)
        self.assertContains(response, 'Finished')

    def test_public_navigation_contains_upper(self):
        response = self.client.get(reverse('schedule'))

        self.assertContains(response, 'href="/upper/"')
        self.assertContains(response, '>Upper<')
