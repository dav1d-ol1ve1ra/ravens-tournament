from datetime import time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from tournament.forms import ALL_GROUP_ASSIGNMENT_SLOTS
from tournament.models import Group, Match, Team


class GroupAssignmentPageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='organiser',
            password='test-password',
        )
        Group.objects.create(name='Group A', code='A')
        Group.objects.create(name='Group B', code='B')
        self.teams = [
            Team.objects.create(name=f'Team {index}') for index in range(1, 10)
        ]

    def assignment_data(self):
        return {
            slot: team.pk
            for slot, team in zip(ALL_GROUP_ASSIGNMENT_SLOTS, self.teams)
        }

    def login(self):
        self.client.force_login(self.user)

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('group_assignment'))

        self.assertRedirects(
            response,
            f'{reverse("login")}?next={reverse("group_assignment")}',
        )

    def test_authenticated_user_can_access_page(self):
        self.login()

        response = self.client.get(reverse('group_assignment'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Group A')
        self.assertContains(response, 'Group B')
        self.assertContains(response, 'Save Group Assignment')

    def test_current_assignments_are_preselected(self):
        self.teams[0].group_slot = 'A1'
        self.teams[0].save(update_fields=['group_slot'])
        self.login()

        response = self.client.get(reverse('group_assignment'))

        self.assertEqual(response.context['form'].fields['A1'].initial, self.teams[0])
        self.assertContains(
            response,
            f'<option value="{self.teams[0].pk}" selected>Team 1</option>',
            html=True,
        )

    def test_valid_five_plus_four_assignment_saves(self):
        self.login()

        response = self.client.post(
            reverse('group_assignment'),
            self.assignment_data(),
        )

        self.assertRedirects(response, reverse('group_assignment'))
        self.assertEqual(
            dict(Team.objects.values_list('group_slot', 'name')),
            {
                slot: team.name
                for slot, team in zip(ALL_GROUP_ASSIGNMENT_SLOTS, self.teams)
            },
        )

    def test_duplicate_team_is_rejected(self):
        self.login()
        data = self.assignment_data()
        data['A2'] = data['A1']

        response = self.client.post(reverse('group_assignment'), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Each team may be assigned to only one slot.')
        self.assertFalse(Team.objects.exclude(group_slot='').exists())

    def test_incomplete_assignment_is_rejected(self):
        self.login()
        data = self.assignment_data()
        data['B4'] = ''

        response = self.client.post(reverse('group_assignment'), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'All nine group slots must be assigned.')
        self.assertFalse(Team.objects.exclude(group_slot='').exists())

    def test_saving_resolves_group_stage_home_team(self):
        match = Match.objects.create(
            day=1,
            start_time=time(10),
            court='Court 1',
            phase='group_stage',
            home_slot='A1',
        )
        self.login()

        self.client.post(reverse('group_assignment'), self.assignment_data())
        match.refresh_from_db()

        self.assertEqual(match.home_team, self.teams[0])

    def test_saving_resolves_group_stage_away_team(self):
        match = Match.objects.create(
            day=1,
            start_time=time(10),
            court='Court 1',
            phase='group_stage',
            away_slot='A2',
        )
        self.login()

        self.client.post(reverse('group_assignment'), self.assignment_data())
        match.refresh_from_db()

        self.assertEqual(match.away_team, self.teams[1])

    def test_saving_resolves_group_stage_referee_team(self):
        match = Match.objects.create(
            day=1,
            start_time=time(10),
            court='Court 1',
            phase='group_stage',
            referee_slot='B3',
        )
        self.login()

        self.client.post(reverse('group_assignment'), self.assignment_data())
        match.refresh_from_db()

        self.assertEqual(match.referee_team, self.teams[7])

    def test_finished_group_stage_result_locks_assignment_changes(self):
        for slot, team in zip(ALL_GROUP_ASSIGNMENT_SLOTS, self.teams):
            team.group_slot = slot
        Team.objects.bulk_update(self.teams, ['group_slot'])
        Match.objects.create(
            day=1,
            start_time=time(10),
            court='Court 1',
            phase='group_stage',
            status=Match.Status.FINISHED,
            home_score=3,
            away_score=1,
        )
        self.login()
        reversed_teams = list(reversed(self.teams))
        changed_assignment = {
            slot: team.pk
            for slot, team in zip(ALL_GROUP_ASSIGNMENT_SLOTS, reversed_teams)
        }

        response = self.client.post(
            reverse('group_assignment'),
            changed_assignment,
            follow=True,
        )

        self.assertContains(
            response,
            'Group assignments are locked because Group Stage results already exist.',
        )
        self.assertEqual(
            list(Team.objects.order_by('pk').values_list('group_slot', flat=True)),
            list(ALL_GROUP_ASSIGNMENT_SLOTS),
        )

    def test_groups_navigation_is_private_to_authenticated_users(self):
        public_response = self.client.get(reverse('home'))

        self.assertNotContains(public_response, 'href="/group-assignment/"')

        self.login()
        authenticated_response = self.client.get(reverse('home'))

        self.assertContains(authenticated_response, 'href="/group-assignment/"')
        self.assertContains(authenticated_response, '>Groups<')
