from datetime import time
from itertools import combinations
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from tournament.models import (
    Group,
    ManualTiebreakResolution,
    Match,
    ScheduleEvent,
    Team,
)
from tournament.services.database_backup import DatabaseBackup
from tournament.services.final_ranking import calculate_final_ranking
from tournament.services.manual_tiebreaks import (
    LOWER_SCOPE,
    get_manual_tiebreak_requirements,
    group_scope,
    save_manual_team_order,
)
from tournament.services.result_reset import reset_tournament_results
from tournament.services.standings import calculate_group_stage_standings


class ManualTiebreakTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='organiser',
            password='test-password',
        )

    def create_drawn_group(self, code='A', team_count=2):
        group = Group.objects.create(name=f'Group {code}', code=code)
        teams = [
            Team.objects.create(
                name=f'Team {code}{position}',
                group_slot=f'{code}{position}',
            )
            for position in range(1, team_count + 1)
        ]
        for index, (home, away) in enumerate(combinations(teams, 2), start=1):
            Match.objects.create(
                day=1,
                start_time=time(9 + index),
                court='Court 1',
                phase='group_stage',
                group=group,
                home_slot=home.group_slot,
                away_slot=away.group_slot,
                home_team=home,
                away_team=away,
                home_score=1,
                away_score=1,
                status=Match.Status.FINISHED,
            )
        return group, teams

    def create_drawn_lower_league(self):
        slots = ('3A', '4A', '5A', '3B', '4B')
        teams = {
            slot: Team.objects.create(name=f'Lower {slot}') for slot in slots
        }
        for index, (home_slot, away_slot) in enumerate(
            combinations(slots, 2), start=1
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
                home_score=2,
                away_score=2,
                status=Match.Status.FINISHED,
            )
        return teams

    def post_requirement(self, requirement, ordered_teams, *, follow=False):
        data = {
            'scope': requirement.scope,
            'team_set_signature': requirement.signature,
        }
        data.update(
            {
                f'order_{position}': team.pk
                for position, team in enumerate(ordered_teams, start=1)
            }
        )
        return self.client.post(
            reverse('manual_tiebreaks'),
            data,
            follow=follow,
        )

    def login(self):
        self.client.force_login(self.user)

    def test_genuine_group_a_and_group_b_ties_are_detected(self):
        self.create_drawn_group('A')
        self.create_drawn_group('B')

        requirements = get_manual_tiebreak_requirements()

        self.assertEqual(
            {requirement.competition_label for requirement in requirements},
            {'Group A', 'Group B'},
        )

    def test_anonymous_redirect_and_authenticated_access(self):
        response = self.client.get(reverse('manual_tiebreaks'))
        self.assertRedirects(
            response,
            f'{reverse("login")}?next={reverse("manual_tiebreaks")}',
        )

        self.login()
        response = self.client.get(reverse('manual_tiebreaks'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'No manual tie-breaks are currently required.',
        )

    def test_navigation_is_private(self):
        public_response = self.client.get(reverse('home'))
        self.assertNotContains(public_response, 'href="/manual-tiebreaks/"')

        self.login()
        organiser_response = self.client.get(reverse('home'))
        self.assertContains(organiser_response, 'href="/manual-tiebreaks/"')
        self.assertContains(organiser_response, '>Tie-breaks<')

    def test_two_team_manual_order_resolves_standings(self):
        _, teams = self.create_drawn_group(team_count=2)
        self.login()
        requirement = get_manual_tiebreak_requirements()[0]

        response = self.post_requirement(requirement, teams[::-1], follow=True)

        rows = calculate_group_stage_standings()['A']
        self.assertEqual([row.team for row in rows], teams[::-1])
        self.assertEqual([row.position for row in rows], [1, 2])
        self.assertFalse(any(row.requires_manual_tiebreak for row in rows))
        self.assertContains(response, 'Group A manual tie-break saved.')

    def test_three_team_manual_order_is_supported(self):
        _, teams = self.create_drawn_group(team_count=3)
        self.login()
        requirement = get_manual_tiebreak_requirements()[0]
        manual_order = (teams[2], teams[0], teams[1])

        self.post_requirement(requirement, manual_order)

        rows = calculate_group_stage_standings()['A']
        self.assertEqual([row.team for row in rows], list(manual_order))
        self.assertEqual([row.position for row in rows], [1, 2, 3])

    def test_duplicate_and_missing_teams_are_rejected(self):
        _, teams = self.create_drawn_group(team_count=2)
        self.login()
        requirement = get_manual_tiebreak_requirements()[0]

        duplicate = self.post_requirement(requirement, (teams[0], teams[0]))
        missing = self.client.post(
            reverse('manual_tiebreaks'),
            {
                'scope': requirement.scope,
                'team_set_signature': requirement.signature,
                'order_1': teams[0].pk,
            },
        )

        self.assertContains(duplicate, 'Each tied team may appear only once.')
        self.assertContains(missing, 'Select every tied team exactly once.')
        self.assertFalse(ManualTiebreakResolution.objects.exists())

    def test_unrelated_team_is_rejected(self):
        _, teams = self.create_drawn_group(team_count=2)
        unrelated = Team.objects.create(name='Unrelated')
        self.login()
        requirement = get_manual_tiebreak_requirements()[0]

        response = self.post_requirement(requirement, (teams[0], unrelated))

        self.assertContains(response, 'Select a valid choice.')
        self.assertFalse(ManualTiebreakResolution.objects.exists())

    def test_stale_submission_is_rejected(self):
        self.create_drawn_group(team_count=2)
        self.login()
        requirement = get_manual_tiebreak_requirements()[0]
        match = Match.objects.get(phase='group_stage')
        match.home_score = 3
        match.away_score = 1
        match.save(update_fields=['home_score', 'away_score'])

        response = self.post_requirement(requirement, requirement.teams)

        self.assertContains(response, 'tied-team set has changed')
        self.assertFalse(ManualTiebreakResolution.objects.exists())

    def test_corrected_results_make_a_stored_resolution_inapplicable(self):
        _, teams = self.create_drawn_group(team_count=2)
        requirement = get_manual_tiebreak_requirements()[0]
        save_manual_team_order(
            requirement.scope,
            (team.pk for team in requirement.teams),
            (teams[1].pk, teams[0].pk),
        )
        match = Match.objects.get(phase='group_stage')
        match.home_score = 4
        match.away_score = 1
        match.save(update_fields=['home_score', 'away_score'])

        rows = calculate_group_stage_standings()['A']

        self.assertEqual(rows[0].team, match.home_team)
        self.assertEqual(rows[0].position, 1)
        self.assertTrue(ManualTiebreakResolution.objects.exists())

    def test_group_manual_order_triggers_ranking_and_lower_progression(self):
        _, teams = self.create_drawn_group(team_count=3)
        upper = Match.objects.create(
            day=2,
            start_time=time(9),
            court='Court 1',
            match_code='UB-TEST',
            phase='upper_semifinal',
            home_slot='1A',
            away_slot='2A',
            referee_slot='3A',
        )
        lower = Match.objects.create(
            day=2,
            start_time=time(10),
            court='Court 2',
            match_code='LL-TEST',
            phase='lower_league',
            home_slot='3A',
            away_slot='',
        )
        self.login()
        requirement = get_manual_tiebreak_requirements()[0]
        manual_order = (teams[2], teams[1], teams[0])

        self.post_requirement(requirement, manual_order)
        upper.refresh_from_db()
        lower.refresh_from_db()

        self.assertEqual(
            (upper.home_team, upper.away_team, upper.referee_team),
            manual_order,
        )
        self.assertEqual(lower.home_team, teams[0])

    def test_lower_manual_order_updates_final_ranking(self):
        teams_by_slot = self.create_drawn_lower_league()
        self.login()
        requirement = next(
            requirement
            for requirement in get_manual_tiebreak_requirements()
            if requirement.scope == LOWER_SCOPE
        )
        manual_order = tuple(reversed(requirement.teams))

        self.post_requirement(requirement, manual_order)

        lower_placements = calculate_final_ranking().placements[4:]
        self.assertEqual(
            [placement.team for placement in lower_placements],
            list(manual_order),
        )
        self.assertEqual(set(teams_by_slot.values()), set(manual_order))

    def test_reset_service_clears_manual_resolutions_and_preserves_schedule(self):
        _, teams = self.create_drawn_group(team_count=2)
        requirement = get_manual_tiebreak_requirements()[0]
        save_manual_team_order(
            group_scope('A'),
            (team.pk for team in teams),
            (teams[1].pk, teams[0].pk),
        )
        event = ScheduleEvent.objects.create(
            day=1,
            start_time=time(8),
            end_time=time(9),
            court='Court 1',
            event_type=ScheduleEvent.EventType.OPENING_CEREMONY,
            label='Opening Ceremony',
        )
        backup = DatabaseBackup(
            source=Path('db.sqlite3'),
            destination=Path('backups/db_test.sqlite3'),
        )

        with patch(
            'tournament.services.result_reset.create_database_backup',
            return_value=backup,
        ):
            reset_tournament_results()

        self.assertFalse(ManualTiebreakResolution.objects.exists())
        self.assertTrue(ScheduleEvent.objects.filter(pk=event.pk).exists())
