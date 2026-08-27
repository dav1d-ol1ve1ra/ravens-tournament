from datetime import time

from django.test import TestCase

from tournament.models import Match, ScheduleEvent, Team
from tournament.services.referee_assignment import assign_referees


class RefereeAssignmentTests(TestCase):
    def setUp(self):
        self.teams = [
            Team.objects.create(name=f'Team {number}', group_slot=f'A{number}')
            for number in range(1, 10)
        ]

    def create_match(
        self,
        code,
        start,
        end,
        home,
        away,
        *,
        court='Court 1',
        day=1,
        referee=None,
        referee_locked=False,
        home_slot=None,
        away_slot=None,
    ):
        event = ScheduleEvent.objects.create(
            day=day,
            start_time=start,
            end_time=end,
            court=court,
            event_type=ScheduleEvent.EventType.MATCH,
            label=code,
        )
        return Match.objects.create(
            day=day,
            start_time=start,
            court=court,
            schedule_event=event,
            match_code=code,
            phase='group_stage',
            home_slot=home_slot if home_slot is not None else home.group_slot,
            away_slot=away_slot if away_slot is not None else away.group_slot,
            home_team=home,
            away_team=away,
            referee_team=referee,
            referee_locked=referee_locked,
        )

    def test_referee_cannot_be_home_team(self):
        match = self.create_match(
            'M-01', time(10), time(11), self.teams[0], self.teams[1]
        )

        assign_referees()
        match.refresh_from_db()

        self.assertNotEqual(match.referee_team, match.home_team)

    def test_referee_cannot_be_away_team(self):
        match = self.create_match(
            'M-01', time(10), time(11), self.teams[0], self.teams[1]
        )

        assign_referees()
        match.refresh_from_db()

        self.assertNotEqual(match.referee_team, match.away_team)

    def test_referee_cannot_be_playing_an_overlapping_match(self):
        first = self.create_match(
            'M-01', time(10), time(11), self.teams[0], self.teams[1], court='Court 1'
        )
        second = self.create_match(
            'M-02', time(10), time(11), self.teams[2], self.teams[3], court='Court 2'
        )

        assign_referees()
        first.refresh_from_db()
        second.refresh_from_db()

        playing = {team.id for team in self.teams[:4]}
        self.assertNotIn(first.referee_team_id, playing)
        self.assertNotIn(second.referee_team_id, playing)

    def test_referee_cannot_cover_two_simultaneous_matches(self):
        first = self.create_match(
            'M-01', time(10), time(11), self.teams[0], self.teams[1], court='Court 1'
        )
        second = self.create_match(
            'M-02', time(10), time(11), self.teams[2], self.teams[3], court='Court 2'
        )

        assign_referees()
        first.refresh_from_db()
        second.refresh_from_db()

        self.assertNotEqual(first.referee_team, second.referee_team)

    def test_three_simultaneous_matches_use_three_different_free_teams(self):
        matches = [
            self.create_match(
                f'M-0{index + 1}',
                time(10),
                time(11, 5),
                self.teams[index * 2],
                self.teams[index * 2 + 1],
                court=f'Court {index + 1}',
            )
            for index in range(3)
        ]

        assign_referees()
        for match in matches:
            match.refresh_from_db()

        self.assertEqual(
            {match.referee_team_id for match in matches},
            {team.id for team in self.teams[6:]},
        )

    def test_one_match_slot_chooses_an_eligible_referee(self):
        match = self.create_match(
            'M-01', time(10), time(11), self.teams[0], self.teams[1]
        )

        result = assign_referees()
        match.refresh_from_db()

        self.assertIsNotNone(match.referee_team)
        self.assertFalse(result.unresolved)

    def test_two_match_slot_uses_two_different_referee_teams(self):
        matches = (
            self.create_match(
                'M-01', time(10), time(11), self.teams[0], self.teams[1], court='Court 1'
            ),
            self.create_match(
                'M-02', time(10), time(11), self.teams[2], self.teams[3], court='Court 2'
            ),
        )

        assign_referees()
        for match in matches:
            match.refresh_from_db()

        self.assertEqual(len({match.referee_team_id for match in matches}), 2)

    def test_assignments_are_reasonably_balanced(self):
        for index in range(18):
            slot_index = index % 9
            self.create_match(
                f'M-{index + 1:02}',
                time(8 + slot_index),
                time(9 + slot_index),
                self.teams[slot_index],
                self.teams[(slot_index + 1) % len(self.teams)],
                day=1 + (index // 9),
            )

        result = assign_referees()
        counts = list(result.team_counts.values())

        self.assertLessEqual(max(counts) - min(counts), 1)

    def test_repeated_runs_are_deterministic(self):
        matches = [
            self.create_match(
                f'M-0{index + 1}',
                time(10),
                time(11),
                self.teams[index * 2],
                self.teams[index * 2 + 1],
                court=f'Court {index + 1}',
            )
            for index in range(3)
        ]
        assign_referees()
        first_assignments = {
            match.id: Match.objects.get(pk=match.id).referee_team_id
            for match in matches
        }

        assign_referees()
        second_assignments = {
            match.id: Match.objects.get(pk=match.id).referee_team_id
            for match in matches
        }

        self.assertEqual(first_assignments, second_assignments)

    def test_manually_locked_referee_is_preserved(self):
        match = self.create_match(
            'M-01',
            time(10),
            time(11),
            self.teams[0],
            self.teams[1],
            referee=self.teams[8],
            referee_locked=True,
        )

        assign_referees()
        match.refresh_from_db()

        self.assertEqual(match.referee_team, self.teams[8])
        self.assertTrue(match.referee_locked)

    def test_changed_schedule_clears_stale_automatic_assignment(self):
        target = self.create_match(
            'M-01', time(10), time(11), self.teams[0], self.teams[1]
        )
        unresolved = self.create_match(
            'M-02',
            time(11),
            time(12),
            self.teams[2],
            self.teams[3],
            home_slot='1A',
        )
        unresolved.home_team = None
        unresolved.save(update_fields=['home_team'])
        assign_referees()
        target.refresh_from_db()
        self.assertIsNotNone(target.referee_team)

        unresolved.schedule_event.start_time = time(10, 30)
        unresolved.schedule_event.end_time = time(10, 45)
        unresolved.schedule_event.save(update_fields=['start_time', 'end_time'])
        result = assign_referees()
        target.refresh_from_db()

        self.assertIsNone(target.referee_team)
        self.assertGreaterEqual(result.stale_assignments_cleared, 1)

    def test_partial_time_overlap_is_detected_from_explicit_times(self):
        first = self.create_match(
            'M-01', time(10), time(11, 5), self.teams[0], self.teams[1]
        )
        self.create_match(
            'M-02', time(11), time(12), self.teams[2], self.teams[3], court='Court 2'
        )

        assign_referees()
        first.refresh_from_db()

        self.assertNotIn(first.referee_team_id, {self.teams[2].id, self.teams[3].id})

    def test_adjacent_events_are_not_simultaneous_conflicts(self):
        target = self.create_match(
            'M-01', time(10), time(11), self.teams[0], self.teams[1], court='Court 1'
        )
        for index, pair in enumerate(((3, 4), (5, 6), (7, 8)), start=2):
            self.create_match(
                f'M-0{index}',
                time(10),
                time(11),
                self.teams[pair[0]],
                self.teams[pair[1]],
                court=f'Court {index}',
            )
        self.create_match(
            'M-05', time(11), time(12), self.teams[2], self.teams[0]
        )

        assign_referees()
        target.refresh_from_db()

        self.assertEqual(target.referee_team, self.teams[2])
