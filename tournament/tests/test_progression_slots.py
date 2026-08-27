from datetime import time
from itertools import combinations

from django.test import TestCase

from tournament.models import Group, Match, Team
from tournament.services.progression_slots import resolve_progression_slots


class ProgressionSlotResolutionTests(TestCase):
    def create_group(self, code, team_count):
        group = Group.objects.create(name=f'Group {code}', code=code)
        teams = [
            Team.objects.create(
                name=f'Team {code}{position}',
                group_slot=f'{code}{position}',
            )
            for position in range(1, team_count + 1)
        ]
        return group, teams

    def create_round_robin(self, group, teams, *, finished=True, all_draws=False):
        matches = []
        pairings = list(combinations(teams, 2))
        for index, (home_team, away_team) in enumerate(pairings):
            is_finished = finished or index < len(pairings) - 1
            matches.append(
                Match.objects.create(
                    day=1,
                    start_time=time(10, 0),
                    court='Court 1',
                    group=group,
                    phase='group_stage',
                    home_slot=home_team.group_slot,
                    away_slot=away_team.group_slot,
                    home_team=home_team,
                    away_team=away_team,
                    home_score=1 if all_draws and is_finished else (3 if is_finished else None),
                    away_score=1 if all_draws and is_finished else (0 if is_finished else None),
                    status=(
                        Match.Status.FINISHED if is_finished else Match.Status.SCHEDULED
                    ),
                )
            )
        return matches

    def create_progression_match(
        self,
        home_slot='',
        away_slot='',
        referee_slot='',
        match_code='',
    ):
        return Match.objects.create(
            day=2,
            start_time=time(10, 0),
            court='Court 1',
            phase='upper_semifinal' if match_code.startswith('UB-') else 'lower_round_robin',
            home_slot=home_slot,
            away_slot=away_slot,
            referee_slot=referee_slot,
            match_code=match_code,
        )

    def test_incomplete_group_a_does_not_resolve_its_slots(self):
        group_a, teams_a = self.create_group('A', 5)
        self.create_round_robin(group_a, teams_a, finished=False)
        stale_team = teams_a[0]
        target = self.create_progression_match(home_slot='1A')
        target.home_team = stale_team
        target.save(update_fields=['home_team'])

        result = resolve_progression_slots()
        target.refresh_from_db()

        self.assertIsNone(target.home_team)
        self.assertIn('incomplete', result.unresolved_slots['1A'])
        self.assertTrue(all(slot not in result.resolved_slots for slot in ('1A', '2A', 'L1', 'L2', 'L3')))

    def test_complete_group_a_resolves_all_upper_and_lower_positions(self):
        group_a, teams_a = self.create_group('A', 5)
        self.create_round_robin(group_a, teams_a)

        result = resolve_progression_slots()

        self.assertEqual(
            {slot: result.resolved_slots[slot] for slot in ('1A', '2A', 'L1', 'L2', 'L3')},
            {
                '1A': teams_a[0],
                '2A': teams_a[1],
                'L1': teams_a[2],
                'L2': teams_a[3],
                'L3': teams_a[4],
            },
        )

    def test_complete_group_b_resolves_all_upper_and_lower_positions(self):
        group_b, teams_b = self.create_group('B', 4)
        self.create_round_robin(group_b, teams_b)

        result = resolve_progression_slots()

        self.assertEqual(
            {slot: result.resolved_slots[slot] for slot in ('1B', '2B', 'L4', 'L5')},
            {
                '1B': teams_b[0],
                '2B': teams_b[1],
                'L4': teams_b[2],
                'L5': teams_b[3],
            },
        )

    def test_group_a_resolves_independently_of_group_b(self):
        group_a, teams_a = self.create_group('A', 5)
        group_b, teams_b = self.create_group('B', 4)
        self.create_round_robin(group_a, teams_a)
        self.create_round_robin(group_b, teams_b, finished=False)

        result = resolve_progression_slots()

        self.assertEqual(result.resolved_slots['1A'], teams_a[0])
        self.assertIn('1B', result.unresolved_slots)

    def test_group_b_resolves_independently_of_group_a(self):
        group_a, teams_a = self.create_group('A', 5)
        group_b, teams_b = self.create_group('B', 4)
        self.create_round_robin(group_a, teams_a, finished=False)
        self.create_round_robin(group_b, teams_b)

        result = resolve_progression_slots()

        self.assertEqual(result.resolved_slots['1B'], teams_b[0])
        self.assertIn('1A', result.unresolved_slots)

    def test_upper_semifinals_receive_correct_teams(self):
        group_a, teams_a = self.create_group('A', 5)
        group_b, teams_b = self.create_group('B', 4)
        self.create_round_robin(group_a, teams_a)
        self.create_round_robin(group_b, teams_b)
        ub_01 = self.create_progression_match('1A', '2B', match_code='UB-01')
        ub_02 = self.create_progression_match('1B', '2A', match_code='UB-02')

        resolve_progression_slots()
        ub_01.refresh_from_db()
        ub_02.refresh_from_db()

        self.assertEqual((ub_01.home_team, ub_01.away_team), (teams_a[0], teams_b[1]))
        self.assertEqual((ub_02.home_team, ub_02.away_team), (teams_b[0], teams_a[1]))

    def test_lower_matches_and_future_referee_slots_receive_correct_teams(self):
        group_a, teams_a = self.create_group('A', 5)
        group_b, teams_b = self.create_group('B', 4)
        self.create_round_robin(group_a, teams_a)
        self.create_round_robin(group_b, teams_b)
        first_lower = self.create_progression_match('L1', 'L2', 'L5', 'LL-01')
        second_lower = self.create_progression_match('L3', 'L4', match_code='LL-02')

        resolve_progression_slots()
        first_lower.refresh_from_db()
        second_lower.refresh_from_db()

        self.assertEqual(
            (first_lower.home_team, first_lower.away_team, first_lower.referee_team),
            (teams_a[2], teams_a[3], teams_b[3]),
        )
        self.assertEqual(
            (second_lower.home_team, second_lower.away_team),
            (teams_a[4], teams_b[2]),
        )

    def test_changed_results_update_previous_assignments(self):
        group_a, teams_a = self.create_group('A', 5)
        matches = self.create_round_robin(group_a, teams_a)
        target = self.create_progression_match(home_slot='1A')
        resolve_progression_slots()

        head_to_head = next(
            match
            for match in matches
            if match.home_team == teams_a[0] and match.away_team == teams_a[1]
        )
        head_to_head.home_score = 0
        head_to_head.away_score = 3
        head_to_head.save(update_fields=['home_score', 'away_score'])
        resolve_progression_slots()
        target.refresh_from_db()

        self.assertEqual(target.home_team, teams_a[1])

    def test_stale_assignment_is_cleared_when_group_becomes_incomplete(self):
        group_a, teams_a = self.create_group('A', 5)
        matches = self.create_round_robin(group_a, teams_a)
        target = self.create_progression_match(home_slot='1A')
        resolve_progression_slots()

        matches[0].status = Match.Status.SCHEDULED
        matches[0].save(update_fields=['status'])
        result = resolve_progression_slots()
        target.refresh_from_db()

        self.assertIsNone(target.home_team)
        self.assertEqual(result.stale_fields_cleared, 1)

    def test_manual_tie_break_prevents_affected_resolutions(self):
        group_a, teams_a = self.create_group('A', 5)
        self.create_round_robin(group_a, teams_a, all_draws=True)
        target = self.create_progression_match('1A', 'L1')

        result = resolve_progression_slots()
        target.refresh_from_db()

        self.assertIsNone(target.home_team)
        self.assertIsNone(target.away_team)
        for slot in ('1A', '2A', 'L1', 'L2', 'L3'):
            self.assertIn('manual tie-break', result.unresolved_slots[slot])

    def test_winner_and_loser_slots_are_not_resolved(self):
        group_a, teams_a = self.create_group('A', 5)
        group_b, teams_b = self.create_group('B', 4)
        self.create_round_robin(group_a, teams_a)
        self.create_round_robin(group_b, teams_b)
        final = self.create_progression_match('W-UB-01', 'W-UB-02', match_code='UB-04')

        resolve_progression_slots()
        final.refresh_from_db()

        self.assertIsNone(final.home_team)
        self.assertIsNone(final.away_team)
