from datetime import date, datetime, time

from django.test import TestCase

from tournament.models import Match, ScheduleEvent


class ScheduleEventTests(TestCase):
    def create_event(self, **overrides):
        values = {
            'day': 1,
            'start_time': time(10, 0),
            'end_time': time(11, 5),
            'court': 'Court 1',
            'event_type': ScheduleEvent.EventType.MATCH,
            'label': 'Group match',
        }
        values.update(overrides)
        return ScheduleEvent.objects.create(**values)

    def test_events_support_independent_variable_durations(self):
        match_event = self.create_event()
        lunch_event = self.create_event(
            start_time=time(13, 15),
            end_time=time(14, 45),
            court='',
            event_type=ScheduleEvent.EventType.LUNCH,
            label='Lunch',
        )

        match_duration = datetime.combine(date.min, match_event.end_time) - datetime.combine(
            date.min, match_event.start_time
        )
        lunch_duration = datetime.combine(date.min, lunch_event.end_time) - datetime.combine(
            date.min, lunch_event.start_time
        )

        self.assertEqual(match_duration.total_seconds() // 60, 65)
        self.assertEqual(lunch_duration.total_seconds() // 60, 90)

    def test_all_required_event_types_are_supported(self):
        event_types = {
            ScheduleEvent.EventType.MATCH,
            ScheduleEvent.EventType.OPENING_CEREMONY,
            ScheduleEvent.EventType.LUNCH,
            ScheduleEvent.EventType.CLOSING_CEREMONY,
            ScheduleEvent.EventType.FREE,
        }

        for index, event_type in enumerate(event_types, start=1):
            with self.subTest(event_type=event_type):
                event = self.create_event(
                    start_time=time(8 + index, 0),
                    end_time=time(8 + index, 30),
                    event_type=event_type,
                    label=ScheduleEvent.EventType(event_type).label,
                )
                event.full_clean()

        self.assertEqual(ScheduleEvent.objects.count(), len(event_types))

    def test_match_can_link_to_event_without_synchronizing_legacy_timing(self):
        event = self.create_event(
            day=2,
            start_time=time(12, 0),
            end_time=time(13, 0),
            court='Court 3',
        )

        match = Match.objects.create(
            day=1,
            start_time=time(9, 0),
            court='Court 1',
            schedule_event=event,
        )

        self.assertEqual(match.schedule_event, event)
        self.assertEqual((match.day, match.start_time, match.court), (1, time(9, 0), 'Court 1'))
