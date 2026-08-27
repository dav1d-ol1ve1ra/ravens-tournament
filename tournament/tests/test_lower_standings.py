from datetime import time

from django.test import TestCase

from tournament.models import Match, Team
from tournament.services.lower_standings import calculate_lower_standings


LOWER_MATCHES = {
    'LL-01': ('L1', 'L2'),
    'LL-02': ('L3', 'L4'),
    'LL-03': ('L1', 'L3'),
    'LL-04': ('L2', 'L5'),
    'LL-05': ('L1', 'L4'),
    'LL-06': ('L3', 'L5'),
    'LL-07': ('L1', 'L5'),
    'LL-08': ('L2', 'L4'),
    'LL-09': ('L2', 'L3'),
    'LL-10': ('L4', 'L5'),
}


class LowerStandingsTests(TestCase):
    def setUp(self):
        self.teams_by_slot = {
            f'L{position}': Team.objects.create(name=f'Lower Team {position}')
            for position in range(1, 6)
        }
        for code, (home_slot, away_slot) in LOWER_MATCHES.items():
            Match.objects.create(
                day=2,
                start_time=time(9),
                court='Court 1',
                match_code=code,
                phase='lower_round_robin',
                home_slot=home_slot,
                away_slot=away_slot,
                home_team=self.teams_by_slot[home_slot],
                away_team=self.teams_by_slot[away_slot],
            )

    def finish(self, code, home_score, away_score):
        match = Match.objects.get(match_code=code)
        match.home_score = home_score
        match.away_score = away_score
        match.status = Match.Status.FINISHED
        match.save(update_fields=['home_score', 'away_score', 'status'])

    def row_for(self, slot):
        team = self.teams_by_slot[slot]
        result = calculate_lower_standings()
        return next(row for row in result.rows if row.team == team)

    def test_non_lower_matches_are_ignored(self):
        Match.objects.create(
            day=1,
            start_time=time(10),
            court='Court 1',
            phase='group_stage',
            home_team=self.teams_by_slot['L1'],
            away_team=self.teams_by_slot['L2'],
            home_score=9,
            away_score=0,
            status=Match.Status.FINISHED,
        )

        self.assertEqual(self.row_for('L1').played, 0)
        self.assertEqual(self.row_for('L2').played, 0)

    def test_scheduled_lower_matches_are_ignored(self):
        match = Match.objects.get(match_code='LL-01')
        match.home_score = 9
        match.away_score = 0
        match.save(update_fields=['home_score', 'away_score'])

        self.assertEqual(self.row_for('L1').played, 0)
        self.assertEqual(self.row_for('L1').ranking_points, 0)

    def test_lower_win_draw_and_loss_scoring(self):
        self.finish('LL-01', 4, 1)
        self.finish('LL-02', 2, 2)

        winner = self.row_for('L1')
        loser = self.row_for('L2')
        drawing_team = self.row_for('L3')

        self.assertEqual((winner.played, winner.wins, winner.ranking_points), (1, 1, 2))
        self.assertEqual((loser.played, loser.losses, loser.ranking_points), (1, 1, 0))
        self.assertEqual(
            (drawing_team.played, drawing_team.draws, drawing_team.ranking_points),
            (1, 1, 1),
        )

    def test_lower_set_difference(self):
        self.finish('LL-01', 5, 2)
        self.finish('LL-03', 1, 4)

        row = self.row_for('L1')

        self.assertEqual((row.sets_for, row.sets_against, row.set_difference), (6, 6, 0))

    def test_lower_tie_is_resolved_by_shared_tie_breaking(self):
        self.finish('LL-01', 1, 1)
        self.finish('LL-03', 5, 0)
        self.finish('LL-09', 2, 0)

        rows = calculate_lower_standings().rows

        self.assertEqual(rows[0].team, self.teams_by_slot['L1'])
        self.assertEqual(rows[1].team, self.teams_by_slot['L2'])
        self.assertGreater(rows[0].set_difference, rows[1].set_difference)

    def test_unresolved_lower_participant_returns_message_instead_of_rows(self):
        Match.objects.filter(home_slot='L5').update(home_team=None)
        Match.objects.filter(away_slot='L5').update(away_team=None)

        result = calculate_lower_standings()

        self.assertFalse(result.is_resolved)
        self.assertEqual(result.rows, [])
        self.assertIn('L5', result.unresolved_slots)
        self.assertIn('not resolved yet', result.unresolved_message)

    def test_incomplete_lower_tie_does_not_require_manual_tiebreak(self):
        self.finish('LL-01', 1, 1)

        tied_rows = [
            row
            for row in calculate_lower_standings().rows
            if row.team in (
                self.teams_by_slot['L1'],
                self.teams_by_slot['L2'],
            )
        ]

        self.assertFalse(any(row.requires_manual_tiebreak for row in tied_rows))
        self.assertTrue(all(row.position is None for row in tied_rows))

    def test_completed_lower_unresolved_tie_requires_manual_tiebreak(self):
        for code in LOWER_MATCHES:
            self.finish(code, 1, 1)

        tied_rows = calculate_lower_standings().rows

        self.assertEqual(len(tied_rows), 5)
        self.assertTrue(all(row.requires_manual_tiebreak for row in tied_rows))
        self.assertTrue(all(row.position is None for row in tied_rows))
