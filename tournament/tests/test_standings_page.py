from datetime import time
from itertools import combinations

from django.test import TestCase
from django.urls import reverse

from tournament.models import Group, Match, Team


LOWER_SLOTS = ('3A', '4A', '5A', '3B', '4B')


class StandingsPageTests(TestCase):
    def setUp(self):
        self.group_a = Group.objects.create(name='Group A', code='A')
        self.group_b = Group.objects.create(name='Group B', code='B')
        self.team_a = Team.objects.create(name='Ravens A', group_slot='A1')
        self.team_b = Team.objects.create(name='London Saints', group_slot='B1')

    def create_lower_league(self, *, all_draws=False):
        teams = {
            slot: Team.objects.create(
                name=f'Lower Team {slot}',
                group_slot=f'{slot[-1]}{slot[:-1]}',
            )
            for slot in LOWER_SLOTS
        }
        matches = []
        for index, (home_slot, away_slot) in enumerate(
            combinations(LOWER_SLOTS, 2), start=1
        ):
            match = Match.objects.create(
                day=2,
                start_time=time(8 + index),
                court='Court 1',
                match_code=f'LL-{index:02}',
                phase='lower_league',
                home_slot=home_slot,
                away_slot=away_slot,
                home_team=teams[home_slot],
                away_team=teams[away_slot],
            )
            if all_draws:
                match.home_score = 1
                match.away_score = 1
                match.status = Match.Status.FINISHED
                match.save(update_fields=['home_score', 'away_score', 'status'])
            matches.append(match)
        return teams, matches

    def test_page_returns_200_and_exposes_only_groups_a_and_b(self):
        Group.objects.create(name='Group C', code='C')
        Team.objects.create(name='Old Group C Team', group_slot='C1')

        response = self.client.get(reverse('standings'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Group A')
        self.assertContains(response, 'Group B')
        self.assertNotContains(response, 'Group C')
        self.assertNotContains(response, 'Old Group C Team')

    def test_page_uses_mobile_cards_and_desktop_tables_from_the_same_rows(self):
        response = self.client.get(reverse('standings'))

        self.assertContains(response, 'class="standings-mobile"')
        self.assertContains(response, 'class="standings-table"')
        self.assertContains(response, 'Ravens A', count=2)

    def test_upper_bracket_is_not_rendered_as_standings(self):
        Match.objects.create(
            day=2,
            start_time=time(10),
            court='Court 1',
            match_code='UB-01',
            phase='upper_semifinal',
            home_slot='1A',
            away_slot='2B',
        )

        response = self.client.get(reverse('standings'))

        self.assertNotContains(response, 'Upper Bracket')
        self.assertNotContains(response, 'UB-01')

    def test_unresolved_lower_participants_show_waiting_message(self):
        response = self.client.get(reverse('standings'))

        self.assertContains(response, 'Lower League')
        self.assertContains(
            response,
            'Lower League teams will be determined after the Group Stage.',
        )

    def test_resolved_lower_participants_appear(self):
        teams, _ = self.create_lower_league()

        response = self.client.get(reverse('standings'))

        for team in teams.values():
            self.assertContains(response, team.name)

    def test_lower_result_affects_only_lower_standings_and_ordering(self):
        teams, matches = self.create_lower_league()
        first_match = matches[0]
        first_match.home_score = 5
        first_match.away_score = 2
        first_match.status = Match.Status.FINISHED
        first_match.save(update_fields=['home_score', 'away_score', 'status'])

        response = self.client.get(reverse('standings'))
        lower_rows = response.context['lower_standings'].rows
        group_rows = response.context['standings_by_group']['A']
        winner = next(row for row in lower_rows if row.team == teams['3A'])
        group_winner = next(row for row in group_rows if row.team == teams['3A'])

        self.assertEqual(lower_rows[0].team, teams['3A'])
        self.assertEqual((winner.played, winner.wins, winner.ranking_points), (1, 1, 2))
        self.assertEqual((group_winner.played, group_winner.ranking_points), (0, 0))

    def test_group_stage_result_does_not_affect_lower_standings(self):
        teams, _ = self.create_lower_league()
        Match.objects.create(
            day=1,
            start_time=time(10),
            court='Court 1',
            phase='group_stage',
            group=self.group_a,
            home_slot='A3',
            away_slot='A4',
            home_team=teams['3A'],
            away_team=teams['4A'],
            home_score=9,
            away_score=0,
            status=Match.Status.FINISHED,
        )

        response = self.client.get(reverse('standings'))

        self.assertTrue(
            all(row.played == 0 for row in response.context['lower_standings'].rows)
        )

    def test_completed_lower_tie_shows_manual_tiebreak_warning(self):
        self.create_lower_league(all_draws=True)

        response = self.client.get(reverse('standings'))

        self.assertContains(response, 'Manual tie-break required')
