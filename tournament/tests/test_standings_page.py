from datetime import time

from django.test import TestCase
from django.urls import reverse

from tournament.models import Group, Match, Team


class StandingsPageTests(TestCase):
    def setUp(self):
        Group.objects.create(name='Group A', code='A')
        Group.objects.create(name='Group B', code='B')
        self.team_a = Team.objects.create(name='Ravens A', group_slot='A1')
        self.team_b = Team.objects.create(name='London Saints', group_slot='B1')

    def create_upper_match(
        self,
        code,
        home_slot,
        away_slot,
        *,
        home_team=None,
        away_team=None,
        home_score=None,
        away_score=None,
        status=Match.Status.SCHEDULED,
    ):
        labels = {
            'UB-01': 'upper_semifinal',
            'UB-02': 'upper_semifinal',
            'UB-03': 'upper_third_place',
            'UB-04': 'upper_final',
        }
        return Match.objects.create(
            day=2,
            start_time=time(10),
            court='Court 1',
            match_code=code,
            phase=labels[code],
            home_slot=home_slot,
            away_slot=away_slot,
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            status=status,
        )

    def create_upper_bracket(self):
        self.create_upper_match('UB-01', '1A', '2B')
        self.create_upper_match('UB-02', '1B', '2A')
        self.create_upper_match('UB-03', 'L-UB-01', 'L-UB-02')
        self.create_upper_match('UB-04', 'W-UB-01', 'W-UB-02')

    def test_page_returns_200_and_shows_groups_a_and_b_without_group_c(self):
        response = self.client.get(reverse('standings'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Group A')
        self.assertContains(response, 'Group B')
        self.assertNotContains(response, 'Group C')

    def test_upper_section_and_all_confirmed_match_codes_appear(self):
        self.create_upper_bracket()

        response = self.client.get(reverse('standings'))

        self.assertContains(response, 'Upper Bracket — 1st to 4th Place')
        for code in ('UB-01', 'UB-02', 'UB-03', 'UB-04'):
            self.assertContains(response, code)

    def test_unresolved_upper_symbolic_slots_display(self):
        self.create_upper_bracket()

        response = self.client.get(reverse('standings'))

        self.assertContains(response, '1A')
        self.assertContains(response, '2B')
        self.assertContains(response, 'W-UB-01')
        self.assertContains(response, 'L-UB-02')

    def test_resolved_upper_team_names_display(self):
        self.create_upper_match(
            'UB-01',
            '1A',
            '2B',
            home_team=self.team_a,
            away_team=self.team_b,
        )

        response = self.client.get(reverse('standings'))

        self.assertContains(response, 'Ravens A')
        self.assertContains(response, 'London Saints')

    def test_finished_upper_score_displays(self):
        self.create_upper_match(
            'UB-01',
            '1A',
            '2B',
            home_team=self.team_a,
            away_team=self.team_b,
            home_score=5,
            away_score=4,
            status=Match.Status.FINISHED,
        )

        response = self.client.get(reverse('standings'))

        self.assertContains(response, '5&ndash;4')
        self.assertContains(response, 'Finished')

    def test_unresolved_lower_participants_show_safe_message(self):
        response = self.client.get(reverse('standings'))

        self.assertContains(response, 'Lower League — 5th to 9th Place')
        self.assertContains(response, 'Lower League participants are not resolved yet')

    def test_manual_lower_tiebreak_indicator_displays(self):
        lower_teams = {
            f'L{position}': Team.objects.create(name=f'Lower Team {position}')
            for position in range(1, 6)
        }
        pairs = (
            ('L1', 'L2'),
            ('L3', 'L4'),
            ('L1', 'L3'),
            ('L2', 'L5'),
            ('L1', 'L4'),
            ('L1', 'L5'),
            ('L3', 'L5'),
            ('L2', 'L4'),
            ('L2', 'L3'),
            ('L4', 'L5'),
        )
        for index, (home_slot, away_slot) in enumerate(pairs, start=1):
            Match.objects.create(
                day=2,
                start_time=time(9 + index),
                court='Court 1',
                match_code=f'LL-{index:02}',
                phase='lower_round_robin',
                home_slot=home_slot,
                away_slot=away_slot,
                home_team=lower_teams[home_slot],
                away_team=lower_teams[away_slot],
                home_score=1,
                away_score=1,
                status=Match.Status.FINISHED,
            )

        response = self.client.get(reverse('standings'))

        self.assertContains(response, 'Manual tie-break required')
