from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tournament.management.commands.seed_tournament import (
    SCHEDULE,
    validate_schedule_definition,
)
from tournament.models import Group, Match, ScheduleEvent


MATCH_EVENT_FIELDS = (
    'day',
    'start_time',
    'end_time',
    'court',
    'event_type',
    'label',
)


def _minutes(value):
    return value.hour * 60 + value.minute


def _update_fields(instance, values):
    changed = []
    for field, value in values.items():
        if getattr(instance, field) != value:
            setattr(instance, field, value)
            changed.append(field)
    if changed:
        instance.save(update_fields=changed)
    return bool(changed)


class Command(BaseCommand):
    help = (
        'Non-destructively synchronize existing matches and schedule events '
        'to the final confirmed schedule.'
    )

    @transaction.atomic
    def handle(self, *args, **options):
        validate_schedule_definition()
        match_items = [item for item in SCHEDULE if item.is_match]
        event_items = [item for item in SCHEDULE if not item.is_match]
        expected_codes = {item.match_code for item in match_items}
        matches_by_code = {
            match.match_code: match
            for match in Match.objects.filter(match_code__in=expected_codes)
            .select_related('schedule_event')
            .order_by('pk')
        }
        missing_codes = sorted(expected_codes - matches_by_code.keys())
        if missing_codes:
            raise CommandError(
                'Schedule sync aborted because existing matches are missing: '
                + ', '.join(missing_codes)
            )

        groups_by_code = {
            group.code: group for group in Group.objects.filter(code__in=('A', 'B'))
        }
        missing_groups = sorted(
            {item.group_code for item in match_items if item.group_code}
            - groups_by_code.keys()
        )
        if missing_groups:
            raise CommandError(
                'Schedule sync aborted because groups are missing: '
                + ', '.join(missing_groups)
            )

        for item in match_items:
            match = matches_by_code[item.match_code]
            if {match.home_slot, match.away_slot} != {
                item.home_slot,
                item.away_slot,
            }:
                raise CommandError(
                    f'Schedule sync aborted: {item.match_code} has unexpected '
                    'participants. Use the explicit development reset only after '
                    'reviewing this data.'
                )

        matches_updated = 0
        match_events_updated = 0
        match_events_created = 0
        for item in match_items:
            match = matches_by_code[item.match_code]
            changed_fields = []

            if (
                match.home_slot == item.away_slot
                and match.away_slot == item.home_slot
                and item.home_slot != item.away_slot
            ):
                match.home_team, match.away_team = match.away_team, match.home_team
                match.home_score, match.away_score = match.away_score, match.home_score
                changed_fields.extend(
                    ['home_team', 'away_team', 'home_score', 'away_score']
                )

            structural_values = {
                'day': item.day,
                'start_time': item.start_time,
                'court': item.court,
                'phase': item.phase,
                'home_slot': item.home_slot,
                'away_slot': item.away_slot,
                'referee_slot': item.referee_slot,
                'group': groups_by_code.get(item.group_code),
                'home_source_match': matches_by_code.get(item.home_source_code),
                'home_source_outcome': item.home_source_outcome,
                'away_source_match': matches_by_code.get(item.away_source_code),
                'away_source_outcome': item.away_source_outcome,
            }
            referee_source_changed = match.referee_slot != item.referee_slot
            for field, value in structural_values.items():
                if getattr(match, field) != value:
                    setattr(match, field, value)
                    changed_fields.append(field)
            if referee_source_changed and not match.referee_locked and match.referee_team_id:
                match.referee_team = None
                changed_fields.append('referee_team')

            event_values = {
                field: getattr(item, field) for field in MATCH_EVENT_FIELDS
            }
            schedule_event = match.schedule_event
            if schedule_event is None:
                schedule_event = ScheduleEvent.objects.create(**event_values)
                match.schedule_event = schedule_event
                changed_fields.append('schedule_event')
                match_events_created += 1
            elif _update_fields(schedule_event, event_values):
                match_events_updated += 1

            if changed_fields:
                match.save(update_fields=list(dict.fromkeys(changed_fields)))
                matches_updated += 1

        nonmatch_events_updated, nonmatch_events_created = self._sync_nonmatch_events(
            event_items
        )

        self.stdout.write(
            self.style.SUCCESS('Final schedule synchronized successfully.')
        )
        self.stdout.write(f'Matches updated: {matches_updated}')
        self.stdout.write(
            'Match ScheduleEvents updated/created: '
            f'{match_events_updated}/{match_events_created}'
        )
        self.stdout.write(
            'Non-match ScheduleEvents updated/created: '
            f'{nonmatch_events_updated}/{nonmatch_events_created}'
        )
        self.stdout.write('Scores, statuses, teams, users, and tie-breaks preserved.')

    def _sync_nonmatch_events(self, event_items):
        candidates = list(
            ScheduleEvent.objects.filter(match__isnull=True).order_by('pk')
        )
        claimed_ids = set()
        updated = 0
        created = 0

        for item in event_items:
            values = {field: getattr(item, field) for field in MATCH_EVENT_FIELDS}
            exact = next(
                (
                    event
                    for event in candidates
                    if event.pk not in claimed_ids
                    and all(getattr(event, field) == value for field, value in values.items())
                ),
                None,
            )
            if exact is not None:
                claimed_ids.add(exact.pk)
                continue

            compatible = [
                event
                for event in candidates
                if event.pk not in claimed_ids
                and event.event_type == item.event_type
                and event.label == item.label
            ]
            if compatible:
                schedule_event = min(
                    compatible,
                    key=lambda event: (
                        event.day != item.day,
                        abs(_minutes(event.start_time) - _minutes(item.start_time)),
                        event.court != item.court,
                        event.pk,
                    ),
                )
                claimed_ids.add(schedule_event.pk)
                updated += _update_fields(schedule_event, values)
            else:
                schedule_event = ScheduleEvent.objects.create(**values)
                candidates.append(schedule_event)
                claimed_ids.add(schedule_event.pk)
                created += 1

        return updated, created
