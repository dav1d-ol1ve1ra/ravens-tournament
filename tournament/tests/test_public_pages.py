from datetime import time

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from tournament.models import Match, Team


class PublicPageTests(TestCase):
    def test_admin_link_is_only_shown_to_authenticated_users(self):
        response = self.client.get(reverse('home'))

        self.assertNotContains(response, 'href="/admin/"')

        user = get_user_model().objects.create_user(
            username='organiser',
            password='test-password',
        )
        self.client.force_login(user)
        response = self.client.get(reverse('home'))

        self.assertContains(response, 'href="/admin/"')

    def test_homepage_shows_up_to_four_scheduled_matches(self):
        team = Team.objects.create(name='Ravens A', country='Portugal')
        for index in range(5):
            Match.objects.create(
                day=1,
                start_time=time(10 + index, 0),
                court='Court A',
                home_slot='A1',
                away_slot='A2',
                home_team=team,
            )

        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'IV Ravens Tournament')
        self.assertContains(response, 'Ravens A')
        self.assertContains(response, 'https://linktr.ee/4th_ravens_tournament')
        self.assertEqual(response.content.count(b'<article class="next-match">'), 4)

    def test_teams_page_shows_country_and_placeholder(self):
        Team.objects.create(name='Ravens A', country='Portugal')

        response = self.client.get(reverse('teams'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ravens A')
        self.assertContains(response, 'Portugal')
        self.assertContains(response, 'RA')

    def test_teams_page_renders_long_team_names(self):
        for name in (
            'Bouncy Badgers',
            'Lord of the Wings',
            'London Saints A',
            'London Saints B',
        ):
            Team.objects.create(name=name)

        response = self.client.get(reverse('teams'))

        for name in (
            'Bouncy Badgers',
            'Lord of the Wings',
            'London Saints A',
            'London Saints B',
        ):
            self.assertContains(response, name)

    def test_teams_page_shows_the_england_flag(self):
        Team.objects.create(name='London Saints A', country='England')

        response = self.client.get(reverse('teams'))

        self.assertContains(response, 'England')
        self.assertContains(response, '🏴')

    def test_teams_page_shows_an_uploaded_logo_when_available(self):
        team = Team.objects.create(
            name='Ravens A',
            country='Portugal',
            logo=SimpleUploadedFile('ravens-logo.png', b'logo-content'),
        )

        response = self.client.get(reverse('teams'))

        self.assertContains(response, team.logo.url)
        self.assertContains(response, 'Ravens A logo')
        team.logo.delete(save=False)
