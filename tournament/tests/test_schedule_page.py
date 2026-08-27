from datetime import time

from django.test import TestCase
from django.urls import reverse

from tournament.models import Match, ScheduleEvent, Team


class SchedulePageTests(TestCase):
    def setUp(self):
        self.opening = ScheduleEvent.objects.create(
            day=1,
            start_time=time(9, 30),
            end_time=time(10, 0),
            court='Court 1',
            event_type=ScheduleEvent.EventType.OPENING_CEREMONY,
            label='Opening Ceremony',
        )
        self.scheduled_event = ScheduleEvent.objects.create(
            day=1,
            start_time=time(10, 0),
            end_time=time(11, 5),
            court='Court 1',
            event_type=ScheduleEvent.EventType.MATCH,
            label='A1 vs A2',
        )
        self.scheduled_match = Match.objects.create(
            day=9,
            start_time=time(23, 0),
            court='Legacy Court',
            schedule_event=self.scheduled_event,
            phase='group_stage',
            home_slot='A1',
            away_slot='A2',
        )
        self.finished_event = ScheduleEvent.objects.create(
            day=1,
            start_time=time(11, 5),
            end_time=time(12, 10),
            court='Court 2',
            event_type=ScheduleEvent.EventType.MATCH,
            label='Finished fixture',
        )
        self.finished_match = Match.objects.create(
            day=1,
            start_time=time(11, 5),
            court='Court 2',
            schedule_event=self.finished_event,
            phase='group_stage',
            home_slot='B1',
            away_slot='B2',
            home_score=4,
            away_score=2,
            status=Match.Status.FINISHED,
        )
        ScheduleEvent.objects.create(
            day=1,
            start_time=time(12, 10),
            end_time=time(13, 15),
            court='Court 3',
            event_type=ScheduleEvent.EventType.LUNCH,
            label='Lunch',
        )
        ScheduleEvent.objects.create(
            day=1,
            start_time=time(13, 15),
            end_time=time(14, 20),
            court='Court 3',
            event_type=ScheduleEvent.EventType.FREE,
            label='Free / Margin',
        )
        ScheduleEvent.objects.create(
            day=2,
            start_time=time(15, 40),
            end_time=time(16, 10),
            court='Court 1',
            event_type=ScheduleEvent.EventType.CLOSING_CEREMONY,
            label='Closing Ceremony',
        )
        legacy_team = Team.objects.create(name='Legacy Only Team')
        Match.objects.create(
            day=1,
            start_time=time(8, 0),
            court='Legacy Court',
            home_team=legacy_team,
            away_slot='A2',
        )

    def test_schedule_uses_schedule_events_not_unlinked_legacy_matches(self):
        response = self.client.get(reverse('schedule'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Opening Ceremony')
        self.assertContains(response, 'Court 1')
        self.assertNotContains(response, 'Legacy Court')
        self.assertNotContains(response, 'Legacy Only Team')

    def test_non_match_event_types_appear_publicly(self):
        response = self.client.get(reverse('schedule'))

        self.assertContains(response, 'Opening Ceremony')
        self.assertContains(response, 'Lunch')
        self.assertContains(response, 'Closing Ceremony')
        self.assertContains(response, 'Free / Margin')

    def test_identical_all_court_non_match_events_are_visually_grouped(self):
        for court in ('Court 2', 'Court 3'):
            ScheduleEvent.objects.create(
                day=1,
                start_time=time(9, 30),
                end_time=time(10, 0),
                court=court,
                event_type=ScheduleEvent.EventType.OPENING_CEREMONY,
                label='Opening Ceremony',
            )

        list_response = self.client.get(reverse('schedule'))
        courts_response = self.client.get(f'{reverse("schedule")}?view=courts')

        self.assertContains(list_response, 'All Courts', count=1)
        self.assertContains(courts_response, 'colspan="3"')

    def test_match_event_shows_linked_match_and_symbolic_participants(self):
        response = self.client.get(reverse('schedule'))

        self.assertContains(response, 'A1')
        self.assertContains(response, 'A2')
        self.assertContains(response, '4 - 2')
        self.assertContains(response, 'Group Stage')

    def test_resolved_team_name_is_preferred_to_symbolic_slot(self):
        team = Team.objects.create(name='Ravens A')
        self.scheduled_match.home_team = team
        self.scheduled_match.save(update_fields=['home_team'])

        response = self.client.get(reverse('schedule'))

        self.assertContains(response, 'Ravens A')

    def test_list_and_court_views_return_success(self):
        self.assertEqual(self.client.get(f'{reverse("schedule")}?view=list').status_code, 200)
        self.assertEqual(
            self.client.get(f'{reverse("schedule")}?view=courts').status_code,
            200,
        )

    def test_court_view_discovers_all_courts_and_explicit_time_ranges(self):
        response = self.client.get(f'{reverse("schedule")}?view=courts')

        self.assertContains(response, 'Court 1')
        self.assertContains(response, 'Court 2')
        self.assertContains(response, 'Court 3')
        self.assertContains(response, '09:30&ndash;10:00', html=False)
        self.assertContains(response, '13:15&ndash;14:20', html=False)

    def test_day_filters_limit_events_to_the_selected_day(self):
        day_one = self.client.get(f'{reverse("schedule")}?day=1')
        day_two = self.client.get(f'{reverse("schedule")}?day=2')

        self.assertContains(day_one, 'Opening Ceremony')
        self.assertNotContains(day_one, 'Closing Ceremony')
        self.assertContains(day_two, 'Closing Ceremony')
        self.assertNotContains(day_two, 'Opening Ceremony')

    def test_match_status_filters_keep_non_match_events_visible(self):
        finished = self.client.get(f'{reverse("schedule")}?status=finished')
        scheduled = self.client.get(f'{reverse("schedule")}?status=scheduled')

        self.assertContains(finished, '4 - 2')
        self.assertNotContains(finished, 'A1')
        self.assertContains(finished, 'Lunch')
        self.assertContains(finished, 'Opening Ceremony')
        self.assertContains(scheduled, 'A1')
        self.assertNotContains(scheduled, '4 - 2')
        self.assertContains(scheduled, 'Free / Margin')
