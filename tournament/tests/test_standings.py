from datetime import time
from types import SimpleNamespace

from django.test import TestCase

from tournament.models import Group, Match, Team
from tournament.services.standings import (
    _tie_break_key,
    calculate_group_stage_standings,
)


class GroupStageStandingsTests(TestCase):
    def setUp(self):
        self.team_a = Team.objects.create(name='Team A', group_slot='A1')
        self.team_b = Team.objects.create(name='Team B', group_slot='A2')
        self.team_c = Team.objects.create(name='Team C', group_slot='A3')

    def create_match(
        self,
        home_team,
        away_team,
        home_score,
        away_score,
        status=Match.Status.FINISHED,
        phase='group_stage',
    ):
        return Match.objects.create(
            day=1,
            start_time=time(10, 0),
            court='Court A',
            phase=phase,
            home_slot=home_team.group_slot,
            away_slot=away_team.group_slot,
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            status=status,
        )

    def group_a_rows(self):
        return calculate_group_stage_standings()['A']

    def row_for(self, team):
        return next(row for row in self.group_a_rows() if row.team == team)

    def test_win_and_loss_scoring(self):
        self.create_match(self.team_a, self.team_b, 3, 1)

        winner = self.row_for(self.team_a)
        loser = self.row_for(self.team_b)

        self.assertEqual((winner.played, winner.wins, winner.ranking_points), (1, 1, 2))
        self.assertEqual((loser.played, loser.losses, loser.ranking_points), (1, 1, 0))

    def test_draw_scoring(self):
        self.create_match(self.team_a, self.team_b, 2, 2)

        for team in (self.team_a, self.team_b):
            row = self.row_for(team)
            self.assertEqual((row.played, row.draws, row.ranking_points), (1, 1, 1))

    def test_set_difference(self):
        self.create_match(self.team_a, self.team_b, 5, 2)
        self.create_match(self.team_c, self.team_a, 4, 1)

        row = self.row_for(self.team_a)

        self.assertEqual(row.sets_for, 6)
        self.assertEqual(row.sets_against, 6)
        self.assertEqual(row.set_difference, 0)

    def test_scheduled_matches_are_ignored(self):
        self.create_match(
            self.team_a,
            self.team_b,
            9,
            0,
            status=Match.Status.SCHEDULED,
        )

        for row in self.group_a_rows():
            self.assertEqual(row.played, 0)
            self.assertEqual(row.ranking_points, 0)

    def test_non_group_stage_matches_are_ignored(self):
        self.create_match(
            self.team_a,
            self.team_b,
            4,
            0,
            phase='final_1_3',
        )

        for row in self.group_a_rows():
            self.assertEqual(row.played, 0)

    def test_groups_are_calculated_independently(self):
        team_b1 = Team.objects.create(name='Team B1', group_slot='B1')
        team_b2 = Team.objects.create(name='Team B2', group_slot='B2')
        self.create_match(self.team_a, self.team_b, 2, 0)
        self.create_match(team_b1, team_b2, 0, 3)

        standings = calculate_group_stage_standings()

        self.assertEqual(standings['A'][0].team, self.team_a)
        self.assertEqual(standings['B'][0].team, team_b2)

    def test_two_team_tie_is_resolved_by_head_to_head(self):
        self.create_match(self.team_a, self.team_b, 1, 0)
        self.create_match(self.team_c, self.team_a, 1, 0)
        self.create_match(self.team_b, self.team_c, 1, 0)
        self.create_match(self.team_c, self.team_a, 1, 0)
        self.create_match(self.team_c, self.team_b, 1, 0)

        rows = self.group_a_rows()

        self.assertEqual([row.team for row in rows], [self.team_c, self.team_a, self.team_b])
        self.assertEqual([row.position for row in rows], [1, 2, 3])
        self.assertFalse(rows[1].requires_manual_tiebreak)
        self.assertFalse(rows[2].requires_manual_tiebreak)

    def test_tie_is_resolved_by_overall_set_difference(self):
        self.create_match(self.team_a, self.team_b, 1, 1)
        self.create_match(self.team_a, self.team_c, 5, 0)
        self.create_match(self.team_b, self.team_c, 2, 0)

        rows = self.group_a_rows()

        self.assertEqual(rows[:2], [self.row_for(self.team_a), self.row_for(self.team_b)])

    def test_tie_is_resolved_by_sets_scored(self):
        self.create_match(self.team_a, self.team_b, 1, 1)
        self.create_match(self.team_a, self.team_c, 3, 1)
        self.create_match(self.team_b, self.team_c, 4, 2)

        rows = self.group_a_rows()

        self.assertEqual(rows[0].team, self.team_b)
        self.assertEqual(rows[1].team, self.team_a)
        self.assertEqual(rows[0].set_difference, rows[1].set_difference)

    def test_tie_is_resolved_by_sets_conceded(self):
        fewer_conceded = SimpleNamespace(
            set_difference=0,
            sets_for=5,
            sets_against=2,
        )
        more_conceded = SimpleNamespace(
            set_difference=0,
            sets_for=5,
            sets_against=3,
        )

        self.assertLess(
            _tie_break_key(fewer_conceded, 1),
            _tie_break_key(more_conceded, 1),
        )

    def test_completely_unresolved_tie_requires_manual_tiebreak(self):
        self.create_match(self.team_a, self.team_b, 1, 1)

        tied_rows = [
            row for row in self.group_a_rows() if row.team in (self.team_a, self.team_b)
        ]

        self.assertEqual(len(tied_rows), 2)
        self.assertTrue(all(row.requires_manual_tiebreak for row in tied_rows))
        self.assertTrue(all(row.position is None for row in tied_rows))


class VariableGroupSizeStandingsTests(TestCase):
    def create_group_teams(self, code, team_count):
        Group.objects.create(name=f'Group {code}', code=code)
        return [
            Team.objects.create(
                name=f'Team {code}{position}',
                group_slot=f'{code}{position}',
            )
            for position in range(1, team_count + 1)
        ]

    def create_match(self, home_team, away_team, home_score, away_score):
        return Match.objects.create(
            day=1,
            start_time=time(10, 0),
            court='Court A',
            phase='group_stage',
            home_slot=home_team.group_slot,
            away_slot=away_team.group_slot,
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            status=Match.Status.FINISHED,
        )

    def test_group_with_three_teams(self):
        teams = self.create_group_teams('A', 3)

        rows = calculate_group_stage_standings()['A']

        self.assertEqual({row.team for row in rows}, set(teams))

    def test_group_with_four_teams(self):
        teams = self.create_group_teams('A', 4)
        self.create_match(teams[3], teams[0], 3, 1)

        rows = calculate_group_stage_standings()['A']

        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0].team, teams[3])
        self.assertEqual(rows[0].ranking_points, 2)

    def test_group_with_five_teams(self):
        teams = self.create_group_teams('A', 5)
        self.create_match(teams[4], teams[0], 2, 0)

        rows = calculate_group_stage_standings()['A']

        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0].team, teams[4])

    def test_multiple_groups_can_have_different_team_counts(self):
        teams_a = self.create_group_teams('A', 5)
        teams_b = self.create_group_teams('B', 4)

        standings = calculate_group_stage_standings()

        self.assertEqual({row.team for row in standings['A']}, set(teams_a))
        self.assertEqual({row.team for row in standings['B']}, set(teams_b))

    def test_head_to_head_tie_breaking_works_in_larger_group(self):
        team_a, team_b, team_c, team_d = self.create_group_teams('A', 4)
        self.create_match(team_d, team_a, 1, 0)
        self.create_match(team_d, team_b, 1, 0)
        self.create_match(team_a, team_b, 1, 0)
        self.create_match(team_b, team_c, 10, 0)

        rows = calculate_group_stage_standings()['A']

        self.assertEqual([row.team for row in rows], [team_d, team_a, team_b, team_c])
        self.assertGreater(rows[2].set_difference, rows[1].set_difference)
        self.assertEqual(rows[2].set_difference, 8)
