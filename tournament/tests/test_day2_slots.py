from datetime import time

from django.test import TestCase

from tournament.models import Match, Team
from tournament.services.day2_slots import resolve_day2_slots


class Day2SlotResolutionTests(TestCase):
    def create_group(self, code):
        return [
            Team.objects.create(name=f'Team {code}{position}', group_slot=f'{code}{position}')
            for position in range(1, 4)
        ]

    def create_group_match(
        self,
        home_team,
        away_team,
        home_score,
        away_score,
        status=Match.Status.FINISHED,
    ):
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
            status=status,
        )

    def complete_group(self, teams):
        first, second, third = teams
        matches = [
            self.create_group_match(first, second, 3, 0),
            self.create_group_match(second, third, 2, 0),
            self.create_group_match(first, third, 1, 0),
        ]
        return matches

    def create_day2_match(self, home_slot='1A', away_slot='2A', referee_slot='3A'):
        return Match.objects.create(
            day=2,
            start_time=time(9, 0),
            court='Court A',
            phase='final_1_3',
            home_slot=home_slot,
            away_slot=away_slot,
            referee_slot=referee_slot,
        )

    def test_complete_group_resolves_all_three_positions(self):
        teams = self.create_group('A')
        self.complete_group(teams)
        self.create_day2_match()

        result = resolve_day2_slots()

        self.assertEqual(
            result.resolved_slots,
            {'1A': teams[0], '2A': teams[1], '3A': teams[2]},
        )

    def test_incomplete_group_does_not_resolve_ranking_slots(self):
        teams = self.create_group('A')
        self.create_group_match(teams[0], teams[1], 2, 0)
        match = self.create_day2_match()

        result = resolve_day2_slots()
        match.refresh_from_db()

        self.assertIsNone(match.home_team)
        self.assertIn('incomplete', result.unresolved_slots['1A'])

    def test_manual_tie_prevents_affected_ranking_resolution(self):
        teams = self.create_group('A')
        self.create_group_match(teams[0], teams[1], 1, 1)
        self.create_group_match(teams[1], teams[2], 1, 1)
        self.create_group_match(teams[0], teams[2], 1, 1)
        match = self.create_day2_match()

        result = resolve_day2_slots()
        match.refresh_from_db()

        self.assertIsNone(match.home_team)
        self.assertIn('manual tie-break', result.unresolved_slots['1A'])

    def test_resolves_day2_home_team(self):
        teams = self.create_group('A')
        self.complete_group(teams)
        match = self.create_day2_match(home_slot='1A', away_slot='', referee_slot='')

        resolve_day2_slots()
        match.refresh_from_db()

        self.assertEqual(match.home_team, teams[0])

    def test_resolves_day2_away_team(self):
        teams = self.create_group('A')
        self.complete_group(teams)
        match = self.create_day2_match(home_slot='', away_slot='2A', referee_slot='')

        resolve_day2_slots()
        match.refresh_from_db()

        self.assertEqual(match.away_team, teams[1])

    def test_resolves_day2_referee_team(self):
        teams = self.create_group('A')
        self.complete_group(teams)
        match = self.create_day2_match(home_slot='', away_slot='', referee_slot='3A')

        resolve_day2_slots()
        match.refresh_from_db()

        self.assertEqual(match.referee_team, teams[2])

    def test_changed_standings_update_previous_assignments(self):
        teams = self.create_group('A')
        matches = self.complete_group(teams)
        match = self.create_day2_match(home_slot='1A', away_slot='', referee_slot='')
        resolve_day2_slots()

        matches[0].home_score = 0
        matches[0].away_score = 3
        matches[0].save(update_fields=['home_score', 'away_score'])
        resolve_day2_slots()
        match.refresh_from_db()

        self.assertEqual(match.home_team, teams[1])

    def test_assignment_is_cleared_if_group_becomes_incomplete(self):
        teams = self.create_group('A')
        matches = self.complete_group(teams)
        match = self.create_day2_match(home_slot='1A', away_slot='', referee_slot='')
        resolve_day2_slots()

        matches[0].status = Match.Status.SCHEDULED
        matches[0].save(update_fields=['status'])
        result = resolve_day2_slots()
        match.refresh_from_db()

        self.assertIsNone(match.home_team)
        self.assertEqual(result.stale_fields_cleared, 1)

    def test_each_group_is_resolved_independently(self):
        teams_a = self.create_group('A')
        self.complete_group(teams_a)
        teams_b = self.create_group('B')
        self.create_group_match(teams_b[0], teams_b[1], 2, 0)
        match = self.create_day2_match(
            home_slot='1A',
            away_slot='1B',
            referee_slot='',
        )

        result = resolve_day2_slots()
        match.refresh_from_db()

        self.assertEqual(match.home_team, teams_a[0])
        self.assertIsNone(match.away_team)
        self.assertIn('1A', result.resolved_slots)
        self.assertIn('1B', result.unresolved_slots)
