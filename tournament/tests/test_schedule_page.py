from datetime import time

from django.test import TestCase
from django.urls import reverse

from tournament.models import Group, Match, ScheduleEvent, Team


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
            label='Lunch Break',
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

    def create_match_event(self, *, code, day, start_time, court, phase, group=None):
        event = ScheduleEvent.objects.create(
            day=day,
            start_time=start_time,
            end_time=time(start_time.hour + 1, start_time.minute),
            court=court,
            event_type=ScheduleEvent.EventType.MATCH,
            label=code,
        )
        return Match.objects.create(
            day=day,
            start_time=start_time,
            court=court,
            schedule_event=event,
            match_code=code,
            phase=phase,
            group=group,
            home_slot='A1',
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
        self.assertContains(response, 'Lunch Break')
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

    def test_schedule_events_and_matches_are_in_chronological_order(self):
        response = self.client.get(reverse('schedule'))
        content = response.content.decode()

        self.assertLess(content.index('Opening Ceremony'), content.index('A1'))
        self.assertLess(content.index('A1'), content.index('4 - 2'))

    def test_resolved_team_name_is_preferred_to_symbolic_slot(self):
        team = Team.objects.create(name='Ravens A')
        self.scheduled_match.home_team = team
        self.scheduled_match.save(update_fields=['home_team'])

        response = self.client.get(reverse('schedule'))

        self.assertContains(response, 'Ravens A')

    def test_ranking_and_outcome_slots_use_public_labels(self):
        ranking_event = ScheduleEvent.objects.create(
            day=2,
            start_time=time(9, 0),
            end_time=time(10, 5),
            court='Court 2',
            event_type=ScheduleEvent.EventType.MATCH,
            label='Upper fixture',
        )
        Match.objects.create(
            day=2,
            start_time=time(9, 0),
            court='Court 2',
            schedule_event=ranking_event,
            phase='upper_semifinal',
            home_slot='1A',
            away_slot='W-UB-01',
            referee_slot='4B',
        )

        response = self.client.get(reverse('schedule'))

        self.assertContains(response, '1st Group A')
        self.assertContains(response, 'Winner UB-01')
        self.assertContains(response, '4th Group B')

    def test_list_and_court_views_return_success(self):
        self.assertEqual(self.client.get(f'{reverse("schedule")}?view=list').status_code, 200)
        self.assertEqual(
            self.client.get(f'{reverse("schedule")}?view=courts').status_code,
            200,
        )

    def test_default_and_explicit_list_views_render_the_mobile_list(self):
        default_response = self.client.get(reverse('schedule'))
        explicit_response = self.client.get(f'{reverse("schedule")}?view=list')

        self.assertContains(default_response, 'class="schedule-list"')
        self.assertNotContains(default_response, 'class="court-grid"')
        self.assertContains(explicit_response, 'class="schedule-list"')
        self.assertContains(default_response, '?view=courts')

    def test_invalid_view_falls_back_to_list(self):
        response = self.client.get(f'{reverse("schedule")}?view=invalid')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="schedule-list"')
        self.assertNotContains(response, 'class="court-grid"')

    def test_court_view_discovers_all_courts_and_explicit_time_ranges(self):
        response = self.client.get(f'{reverse("schedule")}?view=courts')

        self.assertContains(response, 'Court 1')
        self.assertContains(response, 'Court 2')
        self.assertContains(response, 'Court 3')
        self.assertContains(response, '09:30&ndash;10:00', html=False)
        self.assertContains(response, '13:15&ndash;14:20', html=False)

    def test_court_view_places_events_in_the_correct_court_columns(self):
        response = self.client.get(f'{reverse("schedule")}?view=courts')
        self.assertEqual(response.context['courts'], ['Court 1', 'Court 2', 'Court 3'])

        day_one = response.context['court_days'][0]
        match_row = next(
            row for row in day_one['rows'] if row['start_time'] == time(10, 0)
        )
        lunch_row = next(
            row for row in day_one['rows'] if row['start_time'] == time(12, 10)
        )

        self.assertEqual(match_row['cells'][0].pk, self.scheduled_event.pk)
        self.assertIsNone(match_row['cells'][1])
        self.assertEqual(lunch_row['cells'][2].label, 'Lunch Break')

    def test_court_view_preserves_phase_and_day_filters(self):
        self.create_match_event(
            code='LL-01',
            day=2,
            start_time=time(9),
            court='Court 1',
            phase='lower_league',
        )
        self.create_match_event(
            code='GS-A-01',
            day=1,
            start_time=time(14),
            court='Court 2',
            phase='group_stage',
        )

        response = self.client.get(
            f'{reverse("schedule")}?view=courts&day=2&phase=lower_league'
        )

        self.assertContains(response, 'LL-01')
        self.assertNotContains(response, 'GS-A-01')
        self.assertContains(response, 'Sunday')

    def test_day_filters_limit_events_to_the_selected_day(self):
        day_one = self.client.get(f'{reverse("schedule")}?day=1')
        day_two = self.client.get(f'{reverse("schedule")}?day=2')

        self.assertContains(day_one, 'Opening Ceremony')
        self.assertNotContains(day_one, 'Closing Ceremony')
        self.assertContains(day_two, 'Closing Ceremony')
        self.assertNotContains(day_two, 'Opening Ceremony')

    def test_saturday_and_sunday_labels_are_used_for_day_filters(self):
        response = self.client.get(reverse('schedule'))

        self.assertContains(response, 'Saturday')
        self.assertContains(response, 'Sunday')

    def test_group_filter_controls_offer_only_the_current_groups(self):
        response = self.client.get(reverse('schedule'))

        self.assertContains(response, 'Group A')
        self.assertContains(response, 'Group B')
        self.assertNotContains(response, 'Group C')

    def test_group_filters_include_only_the_requested_group_matches(self):
        group_a = Group.objects.create(name='Group A', code='A')
        group_b = Group.objects.create(name='Group B', code='B')
        self.create_match_event(
            code='GS-A-01',
            day=1,
            start_time=time(14),
            court='Court 1',
            phase='group_stage',
            group=group_a,
        )
        self.create_match_event(
            code='GS-B-01',
            day=1,
            start_time=time(15),
            court='Court 2',
            phase='group_stage',
            group=group_b,
        )

        group_a_response = self.client.get(f'{reverse("schedule")}?group=A')
        group_b_response = self.client.get(f'{reverse("schedule")}?group=B')

        self.assertContains(group_a_response, 'GS-A-01')
        self.assertNotContains(group_a_response, 'GS-B-01')
        self.assertContains(group_b_response, 'GS-B-01')
        self.assertNotContains(group_b_response, 'GS-A-01')

    def test_lower_league_phase_filter_works(self):
        self.create_match_event(
            code='LL-01',
            day=2,
            start_time=time(9),
            court='Court 1',
            phase='lower_league',
        )
        self.create_match_event(
            code='GS-A-01',
            day=2,
            start_time=time(10),
            court='Court 2',
            phase='group_stage',
        )

        response = self.client.get(f'{reverse("schedule")}?phase=lower_league')

        self.assertContains(response, 'LL-01')
        self.assertNotContains(response, 'GS-A-01')

    def test_upper_bracket_filter_includes_all_upper_phases(self):
        for index, (code, phase) in enumerate((
            ('UB-01', 'upper_semifinal'),
            ('UB-03', 'upper_third_place'),
            ('UB-04', 'upper_final'),
        ), start=9):
            self.create_match_event(
                code=code,
                day=2,
                start_time=time(index),
                court='Court 1',
                phase=phase,
            )

        response = self.client.get(f'{reverse("schedule")}?phase=upper')

        for code in ('UB-01', 'UB-03', 'UB-04'):
            self.assertContains(response, code)
        self.assertContains(response, 'Upper Semifinal')
        self.assertContains(response, '3rd Place Match')
        self.assertContains(response, 'Final')

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
