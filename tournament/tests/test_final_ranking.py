from datetime import time
from itertools import combinations

from django.test import TestCase
from django.urls import reverse

from tournament.models import Match, Team
from tournament.services.final_ranking import calculate_final_ranking


LOWER_SLOTS = ('3A', '4A', '5A', '3B', '4B')


class FinalRankingPageTests(TestCase):
    def create_upper_match(self, code, home_team, away_team, home_score, away_score):
        phase = 'upper_final' if code == 'UB-04' else 'upper_third_place'
        return Match.objects.create(
            day=2,
            start_time=time(14, 35),
            court='Court 1',
            match_code=code,
            phase=phase,
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            status=Match.Status.FINISHED,
        )

    def create_lower_league(self, *, all_draws=False):
        teams = {
            slot: Team.objects.create(name=f'Lower Team {slot}')
            for slot in LOWER_SLOTS
        }
        for index, (home_slot, away_slot) in enumerate(
            combinations(LOWER_SLOTS, 2),
            start=1,
        ):
            Match.objects.create(
                day=2,
                start_time=time(8 + index),
                court='Court 1',
                match_code=f'LL-{index:02}',
                phase='lower_league',
                home_slot=home_slot,
                away_slot=away_slot,
                home_team=teams[home_slot],
                away_team=teams[away_slot],
                home_score=1 if all_draws else 3,
                away_score=1 if all_draws else 0,
                status=Match.Status.FINISHED,
            )
        return teams

    def test_page_returns_200_and_shows_all_nine_positions(self):
        response = self.client.get(reverse('final_ranking'))

        self.assertEqual(response.status_code, 200)
        for label in ('1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th'):
            self.assertContains(response, f'<span class="final-position">{label}</span>')

    def test_unresolved_upper_positions_show_source_placeholders(self):
        home = Team.objects.create(name='Scheduled Home')
        away = Team.objects.create(name='Scheduled Away')
        for code, phase in (
            ('UB-03', 'upper_third_place'),
            ('UB-04', 'upper_final'),
        ):
            Match.objects.create(
                day=2,
                start_time=time(14, 35),
                court='Court 1',
                match_code=code,
                phase=phase,
                home_team=home,
                away_team=away,
                status=Match.Status.SCHEDULED,
            )

        response = self.client.get(reverse('final_ranking'))

        for placeholder in (
            'Winner UB-04',
            'Loser UB-04',
            'Winner UB-03',
            'Loser UB-03',
        ):
            self.assertContains(response, placeholder)

    def test_finished_final_populates_first_and_second(self):
        champion = Team.objects.create(name='Final Winner')
        runner_up = Team.objects.create(name='Final Runner-up')
        self.create_upper_match('UB-04', champion, runner_up, 7, 5)

        ranking = calculate_final_ranking().placements

        self.assertEqual(ranking[0].team, champion)
        self.assertEqual(ranking[1].team, runner_up)

    def test_finished_third_place_match_populates_third_and_fourth(self):
        third = Team.objects.create(name='Third Place Team')
        fourth = Team.objects.create(name='Fourth Place Team')
        self.create_upper_match('UB-03', third, fourth, 6, 4)

        ranking = calculate_final_ranking().placements

        self.assertEqual(ranking[2].team, third)
        self.assertEqual(ranking[3].team, fourth)

    def test_completed_lower_standings_populate_fifth_through_ninth(self):
        teams = self.create_lower_league()

        lower_placements = calculate_final_ranking().placements[4:]

        self.assertEqual(
            [placement.team for placement in lower_placements],
            [teams[slot] for slot in LOWER_SLOTS],
        )

    def test_lower_results_do_not_affect_upper_placements(self):
        champion = Team.objects.create(name='Champion')
        runner_up = Team.objects.create(name='Runner-up')
        third = Team.objects.create(name='Third')
        fourth = Team.objects.create(name='Fourth')
        self.create_upper_match('UB-04', champion, runner_up, 7, 4)
        self.create_upper_match('UB-03', third, fourth, 6, 3)
        upper_before = [
            placement.team for placement in calculate_final_ranking().placements[:4]
        ]

        self.create_lower_league()
        upper_after = [
            placement.team for placement in calculate_final_ranking().placements[:4]
        ]

        self.assertEqual(upper_after, upper_before)

    def test_upper_results_do_not_affect_lower_ordering(self):
        self.create_lower_league()
        lower_before = [
            placement.team for placement in calculate_final_ranking().placements[4:]
        ]
        final_home = Team.objects.create(name='Upper Home')
        final_away = Team.objects.create(name='Upper Away')

        self.create_upper_match('UB-04', final_home, final_away, 8, 2)
        lower_after = [
            placement.team for placement in calculate_final_ranking().placements[4:]
        ]

        self.assertEqual(lower_after, lower_before)

    def test_manual_lower_tie_keeps_placeholders_and_shows_warning(self):
        teams = self.create_lower_league(all_draws=True)

        response = self.client.get(reverse('final_ranking'))
        lower_placements = response.context['final_placements'][4:]

        self.assertTrue(all(placement.team is None for placement in lower_placements))
        self.assertTrue(
            all(placement.requires_manual_tiebreak for placement in lower_placements)
        )
        self.assertContains(response, 'Manual tie-break required', count=5)
        for team in teams.values():
            self.assertNotContains(response, team.name)

    def test_public_navigation_contains_final_ranking(self):
        response = self.client.get(reverse('home'))

        self.assertContains(response, 'href="/final-ranking/"')
        self.assertContains(response, '>Final Ranking<')
