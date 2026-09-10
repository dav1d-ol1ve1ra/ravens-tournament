from datetime import time
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from tournament.management.commands.seed_tournament import SCHEDULE
from tournament.models import ManualTiebreakResolution, Match, ScheduleEvent, Team


class SyncFinalScheduleTests(TestCase):
    def setUp(self):
        call_command(
            'seed_tournament',
            reset_schedule=True,
            stdout=StringIO(),
            stderr=StringIO(),
        )
        self.teams = list(Team.objects.order_by('pk'))
        for position, team in enumerate(self.teams, start=1):
            team.group_slot = f'A{position}' if position <= 5 else f'B{position - 5}'
        Team.objects.bulk_update(self.teams, ['group_slot'])
        self.user = get_user_model().objects.create_user(
            username='organiser',
            password='test-password',
        )
        self.manual_resolution = ManualTiebreakResolution.objects.create(
            scope='group:A',
            team_set_signature=f'{self.teams[0].pk},{self.teams[1].pk}',
            team_order=[self.teams[1].pk, self.teams[0].pk],
        )
        self.unrelated_event = ScheduleEvent.objects.create(
            day=3,
            start_time=time(12),
            end_time=time(12, 30),
            court='Meeting Room',
            event_type=ScheduleEvent.EventType.FREE,
            label='Organiser Meeting',
        )
        self._restore_previous_schedule_values()

    def _restore_previous_schedule_values(self):
        ll_01 = Match.objects.get(match_code='LL-01')
        ll_01.start_time = time(16, 55)
        ll_01.referee_slot = 'A3'
        ll_01.save(update_fields=['start_time', 'referee_slot'])
        ScheduleEvent.objects.filter(pk=ll_01.schedule_event_id).update(
            start_time=time(16, 55)
        )

        group_b_06 = Match.objects.get(match_code='GS-B-06')
        group_b_06.referee_slot = 'B1'
        group_b_06.save(update_fields=['referee_slot'])

        ll_03 = Match.objects.get(match_code='LL-03')
        ll_03.home_slot, ll_03.away_slot = '4A', '3A'
        ll_03.home_team, ll_03.away_team = self.teams[3], self.teams[2]
        ll_03.home_score, ll_03.away_score = 6, 2
        ll_03.status = Match.Status.FINISHED
        ll_03.save(
            update_fields=[
                'home_slot', 'away_slot', 'home_team', 'away_team',
                'home_score', 'away_score', 'status',
            ]
        )

        ll_09 = Match.objects.get(match_code='LL-09')
        ll_09.home_slot, ll_09.away_slot = '5A', '3A'
        ll_09.save(update_fields=['home_slot', 'away_slot'])

        changes = {
            'UB-01': (time(9), time(10, 5), 'Court 3', '3B'),
            'UB-02': (time(10, 5), time(11, 10), 'Court 3', '5A'),
            'UB-03': (time(14, 35), time(15, 40), 'Court 1', '4A'),
            'UB-04': (time(14, 35), time(15, 40), 'Court 2', '4B'),
        }
        for code, (start, end, court, referee) in changes.items():
            match = Match.objects.get(match_code=code)
            match.start_time = start
            match.court = court
            match.referee_slot = referee
            match.save(update_fields=['start_time', 'court', 'referee_slot'])
            ScheduleEvent.objects.filter(pk=match.schedule_event_id).update(
                start_time=start,
                end_time=end,
                court=court,
            )

        final_free = ScheduleEvent.objects.get(
            day=2,
            start_time=time(14, 35),
            court='Court 2',
            event_type=ScheduleEvent.EventType.FREE,
        )
        final_free.start_time = time(13, 35)
        final_free.end_time = time(14, 35)
        final_free.court = 'Court 3'
        final_free.save(update_fields=['start_time', 'end_time', 'court'])

    def run_sync(self):
        output = StringIO()
        call_command('sync_final_schedule', stdout=output)
        return output.getvalue()

    def test_updates_every_coded_match_to_the_final_source_definition(self):
        match_ids = dict(Match.objects.values_list('match_code', 'pk'))

        self.run_sync()

        for item in (item for item in SCHEDULE if item.is_match):
            with self.subTest(code=item.match_code):
                match = Match.objects.select_related('schedule_event').get(
                    match_code=item.match_code
                )
                self.assertEqual(match.pk, match_ids[item.match_code])
                self.assertEqual(
                    (match.day, match.start_time, match.court),
                    (item.day, item.start_time, item.court),
                )
                self.assertEqual(
                    (match.home_slot, match.away_slot, match.referee_slot),
                    (item.home_slot, item.away_slot, item.referee_slot),
                )
                self.assertEqual(
                    (
                        match.schedule_event.day,
                        match.schedule_event.start_time,
                        match.schedule_event.end_time,
                        match.schedule_event.court,
                        match.schedule_event.label,
                    ),
                    (item.day, item.start_time, item.end_time, item.court, item.label),
                )

    def test_preserves_results_and_swaps_them_with_reversed_participants(self):
        ll_03 = Match.objects.get(match_code='LL-03')
        original_id = ll_03.pk

        self.run_sync()
        ll_03.refresh_from_db()

        self.assertEqual(ll_03.pk, original_id)
        self.assertEqual(ll_03.status, Match.Status.FINISHED)
        self.assertEqual((ll_03.home_slot, ll_03.away_slot), ('3A', '4A'))
        self.assertEqual((ll_03.home_team, ll_03.away_team), (self.teams[2], self.teams[3]))
        self.assertEqual((ll_03.home_score, ll_03.away_score), (2, 6))

    def test_updates_saturday_referee_sources_without_deleting_results(self):
        group_match = Match.objects.get(match_code='GS-B-06')
        group_match.home_team = self.teams[6]
        group_match.away_team = self.teams[7]
        group_match.home_score = 7
        group_match.away_score = 5
        group_match.status = Match.Status.FINISHED
        group_match.save(
            update_fields=[
                'home_team',
                'away_team',
                'home_score',
                'away_score',
                'status',
            ]
        )

        self.run_sync()
        group_match.refresh_from_db()
        lower_match = Match.objects.get(match_code='LL-01')

        self.assertEqual(group_match.referee_slot, '1A')
        self.assertEqual(lower_match.referee_slot, '3A')
        self.assertEqual(
            (group_match.home_score, group_match.away_score, group_match.status),
            (7, 5, Match.Status.FINISHED),
        )

    def test_preserves_teams_users_group_assignments_and_manual_tiebreaks(self):
        team_ids = list(Team.objects.order_by('pk').values_list('pk', flat=True))
        assignments = dict(Team.objects.values_list('pk', 'group_slot'))

        self.run_sync()

        self.assertEqual(
            list(Team.objects.order_by('pk').values_list('pk', flat=True)),
            team_ids,
        )
        self.assertEqual(dict(Team.objects.values_list('pk', 'group_slot')), assignments)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertTrue(
            ManualTiebreakResolution.objects.filter(pk=self.manual_resolution.pk).exists()
        )

    def test_reconciles_nonmatch_events_without_deleting_unrelated_events(self):
        unrelated_id = self.unrelated_event.pk

        self.run_sync()

        self.assertTrue(
            ScheduleEvent.objects.filter(
                day=2,
                start_time=time(14, 35),
                end_time=time(15, 40),
                court='Court 2',
                event_type=ScheduleEvent.EventType.FREE,
                label='Free / Buffer',
            ).exists()
        )
        self.assertTrue(ScheduleEvent.objects.filter(pk=unrelated_id).exists())
        self.assertEqual(Match.objects.count(), 30)
        self.assertEqual(ScheduleEvent.objects.count(), 46)

    def test_is_idempotent(self):
        self.run_sync()

        second_output = self.run_sync()

        self.assertIn('Matches updated: 0', second_output)
        self.assertIn('Match ScheduleEvents updated/created: 0/0', second_output)
        self.assertIn('Non-match ScheduleEvents updated/created: 0/0', second_output)
