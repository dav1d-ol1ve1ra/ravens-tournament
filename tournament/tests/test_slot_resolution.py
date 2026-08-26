from datetime import time

from django.test import TestCase

from tournament.models import Group, Match, Team
from tournament.slot_resolution import resolve_group_stage_slots


class DirectGroupSlotResolutionTests(TestCase):
    def setUp(self):
        Group.objects.create(name='Group A', code='A')
        Group.objects.create(name='Group B', code='B')

    def create_match(self, **overrides):
        values = {
            'day': 1,
            'start_time': time(10, 0),
            'court': 'Court 1',
            'phase': 'group_stage',
        }
        values.update(overrides)
        return Match.objects.create(**values)

    def test_resolves_a1_a5_and_b4_for_all_team_roles(self):
        home = Team.objects.create(name='Team A1', group_slot='A1')
        away = Team.objects.create(name='Team A5', group_slot='A5')
        referee = Team.objects.create(name='Team B4', group_slot='B4')
        match = self.create_match(
            home_slot='A1',
            away_slot='A5',
            referee_slot='B4',
        )

        first_result = resolve_group_stage_slots()
        second_result = resolve_group_stage_slots()
        match.refresh_from_db()

        self.assertEqual(match.home_team, home)
        self.assertEqual(match.away_team, away)
        self.assertEqual(match.referee_team, referee)
        self.assertEqual(first_result, (3, 1))
        self.assertEqual(second_result, (0, 0))

    def test_resolves_arbitrary_positive_integer_slot(self):
        team = Team.objects.create(name='Team A12345', group_slot='A12345')
        match = self.create_match(home_slot='A12345')

        resolve_group_stage_slots()
        match.refresh_from_db()

        self.assertEqual(match.home_team, team)

    def test_ranking_slot_is_not_treated_as_direct(self):
        team = Team.objects.create(name='Team A1', group_slot='A1')
        match = self.create_match(home_slot='1A', home_team=team)

        self.assertEqual(resolve_group_stage_slots(), (0, 0))
        match.refresh_from_db()

        self.assertEqual(match.home_team, team)

    def test_lower_slot_is_not_treated_as_direct(self):
        Group.objects.create(name='Lower Group', code='L')
        lower_team = Team.objects.create(name='Lower Team', group_slot='L1')
        match = self.create_match(home_slot='L1')

        self.assertEqual(resolve_group_stage_slots(), (0, 0))
        match.refresh_from_db()

        self.assertIsNone(match.home_team)
        self.assertEqual(lower_team.group_slot, 'L1')

    def test_changed_group_assignment_updates_resolved_team(self):
        original_team = Team.objects.create(name='Original Team', group_slot='A1')
        match = self.create_match(home_slot='A1')
        resolve_group_stage_slots()

        original_team.group_slot = 'A2'
        original_team.save(update_fields=['group_slot'])
        replacement_team = Team.objects.create(name='Replacement Team', group_slot='A1')
        resolve_group_stage_slots()
        match.refresh_from_db()

        self.assertEqual(match.home_team, replacement_team)

    def test_stale_assignment_is_cleared_when_slot_has_no_team(self):
        team = Team.objects.create(name='Team A1', group_slot='A1')
        match = self.create_match(home_slot='A1')
        resolve_group_stage_slots()

        team.group_slot = ''
        team.save(update_fields=['group_slot'])
        fields_updated, matches_updated = resolve_group_stage_slots()
        match.refresh_from_db()

        self.assertIsNone(match.home_team)
        self.assertEqual((fields_updated, matches_updated), (1, 1))
