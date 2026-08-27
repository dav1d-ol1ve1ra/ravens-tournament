from datetime import time

from django.core.exceptions import ValidationError
from django.test import TestCase

from tournament.models import Match, Team
from tournament.services.knockout_slots import resolve_knockout_slots


class KnockoutSlotResolutionTests(TestCase):
    def setUp(self):
        self.team_a = Team.objects.create(name='Team A')
        self.team_b = Team.objects.create(name='Team B')
        self.team_c = Team.objects.create(name='Team C')
        self.team_d = Team.objects.create(name='Team D')

    def create_match(self, **overrides):
        values = {
            'day': 2,
            'start_time': time(10, 0),
            'court': 'Court 1',
            'phase': 'upper_semifinal',
        }
        values.update(overrides)
        return Match.objects.create(**values)

    def create_finished_semifinal(
        self,
        match_code,
        home_team,
        away_team,
        home_score,
        away_score,
    ):
        return self.create_match(
            match_code=match_code,
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            status=Match.Status.FINISHED,
        )

    def test_finished_ub_01_resolves_winner_and_loser(self):
        self.create_finished_semifinal(
            'UB-01', self.team_a, self.team_b, 8, 5
        )
        third_place = self.create_match(
            match_code='UB-03',
            phase='upper_third_place',
            home_slot='L-UB-01',
        )
        final = self.create_match(
            match_code='UB-04',
            phase='upper_final',
            home_slot='W-UB-01',
        )

        first_result = resolve_knockout_slots()
        second_result = resolve_knockout_slots()
        third_place.refresh_from_db()
        final.refresh_from_db()

        self.assertEqual(first_result.resolved_slots['W-UB-01'], self.team_a)
        self.assertEqual(first_result.resolved_slots['L-UB-01'], self.team_b)
        self.assertEqual(third_place.home_team, self.team_b)
        self.assertEqual(final.home_team, self.team_a)
        self.assertEqual(second_result.fields_updated, 0)

    def test_finished_ub_02_resolves_winner_and_loser(self):
        self.create_finished_semifinal(
            'UB-02', self.team_c, self.team_d, 4, 7
        )
        third_place = self.create_match(
            match_code='UB-03',
            phase='upper_third_place',
            away_slot='L-UB-02',
        )
        final = self.create_match(
            match_code='UB-04',
            phase='upper_final',
            away_slot='W-UB-02',
        )

        result = resolve_knockout_slots()
        third_place.refresh_from_db()
        final.refresh_from_db()

        self.assertEqual(result.resolved_slots['W-UB-02'], self.team_d)
        self.assertEqual(result.resolved_slots['L-UB-02'], self.team_c)
        self.assertEqual(third_place.away_team, self.team_c)
        self.assertEqual(final.away_team, self.team_d)

    def test_ub_03_and_ub_04_receive_both_semifinal_participants(self):
        self.create_finished_semifinal(
            'UB-01', self.team_a, self.team_b, 8, 5
        )
        self.create_finished_semifinal(
            'UB-02', self.team_c, self.team_d, 4, 7
        )
        third_place = self.create_match(
            match_code='UB-03',
            phase='upper_third_place',
            home_slot='L-UB-01',
            away_slot='L-UB-02',
        )
        final = self.create_match(
            match_code='UB-04',
            phase='upper_final',
            home_slot='W-UB-01',
            away_slot='W-UB-02',
        )

        resolve_knockout_slots()
        third_place.refresh_from_db()
        final.refresh_from_db()

        self.assertEqual(
            (third_place.home_team, third_place.away_team),
            (self.team_b, self.team_c),
        )
        self.assertEqual(
            (final.home_team, final.away_team),
            (self.team_a, self.team_d),
        )

    def test_unfinished_source_match_does_not_resolve(self):
        self.create_match(
            match_code='UB-01',
            home_team=self.team_a,
            away_team=self.team_b,
        )
        final = self.create_match(home_slot='W-UB-01')

        result = resolve_knockout_slots()
        final.refresh_from_db()

        self.assertIsNone(final.home_team)
        self.assertIn('not finished', result.unresolved_slots['W-UB-01'])

    def test_finished_source_with_missing_scores_does_not_resolve(self):
        self.create_match(
            match_code='UB-01',
            home_team=self.team_a,
            away_team=self.team_b,
            status=Match.Status.FINISHED,
        )
        final = self.create_match(home_slot='W-UB-01')

        result = resolve_knockout_slots()
        final.refresh_from_db()

        self.assertIsNone(final.home_team)
        self.assertIn('does not have both scores', result.unresolved_slots['W-UB-01'])

    def test_tied_upper_result_does_not_resolve(self):
        self.create_finished_semifinal(
            'UB-01', self.team_a, self.team_b, 5, 5
        )
        final = self.create_match(home_slot='W-UB-01')

        result = resolve_knockout_slots()
        final.refresh_from_db()

        self.assertIsNone(final.home_team)
        self.assertIn('tied Upper knockout result', result.unresolved_slots['W-UB-01'])

    def test_corrected_result_updates_final_and_third_place(self):
        semifinal = self.create_finished_semifinal(
            'UB-01', self.team_a, self.team_b, 8, 5
        )
        third_place = self.create_match(home_slot='L-UB-01')
        final = self.create_match(away_slot='W-UB-01')
        resolve_knockout_slots()

        semifinal.home_score = 5
        semifinal.away_score = 8
        semifinal.save(update_fields=['home_score', 'away_score'])
        resolve_knockout_slots()
        third_place.refresh_from_db()
        final.refresh_from_db()

        self.assertEqual(third_place.home_team, self.team_a)
        self.assertEqual(final.away_team, self.team_b)

    def test_stale_assignments_are_cleared(self):
        semifinal = self.create_finished_semifinal(
            'UB-01', self.team_a, self.team_b, 8, 5
        )
        final = self.create_match(home_slot='W-UB-01')
        resolve_knockout_slots()

        semifinal.status = Match.Status.SCHEDULED
        semifinal.save(update_fields=['status'])
        result = resolve_knockout_slots()
        final.refresh_from_db()

        self.assertIsNone(final.home_team)
        self.assertEqual(result.stale_fields_cleared, 1)

    def test_group_stage_and_lower_round_robin_draws_remain_valid(self):
        for phase in ('group_stage', 'lower_round_robin'):
            with self.subTest(phase=phase):
                match = self.create_match(
                    phase=phase,
                    status=Match.Status.FINISHED,
                    home_score=4,
                    away_score=4,
                )
                match.full_clean()

    def test_finished_upper_draw_fails_model_validation(self):
        match = self.create_match(
            status=Match.Status.FINISHED,
            home_score=4,
            away_score=4,
        )

        with self.assertRaisesMessage(
            ValidationError,
            'Upper knockout matches cannot finish in a draw.',
        ):
            match.full_clean()
