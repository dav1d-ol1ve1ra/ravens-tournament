from collections import Counter
from dataclasses import dataclass, field

from django.db import transaction

from tournament.models import Match, ScheduleEvent, Team
from tournament.slots import parse_direct_group_slot


@dataclass(frozen=True)
class RefereeAssignment:
    match: Match
    team: Team
    source: str


@dataclass(frozen=True)
class UnresolvedRefereeAssignment:
    match: Match
    reason: str


@dataclass
class RefereeAssignmentResult:
    assignments: list[RefereeAssignment] = field(default_factory=list)
    unresolved: list[UnresolvedRefereeAssignment] = field(default_factory=list)
    team_counts: dict[Team, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    fields_updated: int = 0
    stale_assignments_cleared: int = 0


def _match_label(match):
    return match.match_code or str(match)


def _events_overlap(first, second):
    return (
        first.day == second.day
        and first.start_time < second.end_time
        and second.start_time < first.end_time
    )


def _participant_ids(match, teams_by_slot):
    participant_ids = set()

    for team_field, slot_field in (
        ('home_team_id', 'home_slot'),
        ('away_team_id', 'away_slot'),
    ):
        team_id = getattr(match, team_field)
        if team_id is not None:
            participant_ids.add(team_id)
            continue

        slot = getattr(match, slot_field)
        if parse_direct_group_slot(slot) is None:
            return participant_ids, False
        team_id = teams_by_slot.get(slot)
        if team_id is None:
            return participant_ids, False
        participant_ids.add(team_id)

    return participant_ids, True


def _adjacent_match_count(team_id, event, timed_matches, participants_by_match):
    count = 0
    for other in timed_matches:
        other_event = other.schedule_event
        if other_event.day != event.day:
            continue
        if team_id not in participants_by_match[other.id][0]:
            continue
        if (
            other_event.end_time == event.start_time
            or other_event.start_time == event.end_time
        ):
            count += 1
    return count


def _protected_assignment_warning(
    match,
    referee_team_id,
    timed_matches,
    participants_by_match,
    protected_referees,
):
    event = match.schedule_event
    participant_ids, participants_known = participants_by_match[match.id]
    if not participants_known:
        return 'cannot verify the locked/symbolic referee against unresolved participants'
    if referee_team_id in participant_ids:
        return 'referee team is also a participant in this match'

    for other in timed_matches:
        if other.id == match.id or not _events_overlap(event, other.schedule_event):
            continue
        other_participants, other_known = participants_by_match[other.id]
        if not other_known:
            return (
                f'cannot verify referee safety because {_match_label(other)} '
                'has unresolved participants'
            )
        if referee_team_id in other_participants:
            return f'referee team is playing in overlapping match {_match_label(other)}'
        if protected_referees.get(other.id) == referee_team_id:
            return (
                f'referee team is also assigned to overlapping match '
                f'{_match_label(other)}'
            )
    return None


@transaction.atomic
def assign_referees():
    """Rebuild safe automatic referee assignments from explicit event timings."""
    teams = list(Team.objects.order_by('name', 'pk'))
    teams_by_id = {team.id: team for team in teams}
    teams_by_slot = {
        team.group_slot: team.id
        for team in teams
        if team.group_slot and parse_direct_group_slot(team.group_slot)
    }
    matches = list(
        Match.objects.select_for_update()
        .select_related(
            'schedule_event',
            'home_team',
            'away_team',
            'referee_team',
        )
        .order_by(
            'schedule_event__day',
            'schedule_event__start_time',
            'schedule_event__end_time',
            'schedule_event__court',
            'pk',
        )
    )
    matches_by_id = {match.id: match for match in matches}

    result = RefereeAssignmentResult()
    timed_matches = []
    invalid_schedule_reasons = {}
    for match in matches:
        event = match.schedule_event
        if event is None:
            invalid_schedule_reasons[match.id] = 'match has no linked ScheduleEvent'
        elif event.event_type != ScheduleEvent.EventType.MATCH:
            invalid_schedule_reasons[match.id] = (
                'linked ScheduleEvent is not a match event'
            )
        elif event.end_time <= event.start_time:
            invalid_schedule_reasons[match.id] = (
                'ScheduleEvent end time must be later than its start time'
            )
        else:
            timed_matches.append(match)

    participants_by_match = {
        match.id: _participant_ids(match, teams_by_slot)
        for match in timed_matches
    }

    # Locked assignments and symbolic referee slots are outside automatic ownership.
    protected_matches = {
        match.id: match
        for match in matches
        if match.referee_locked or match.referee_slot
    }
    protected_referees = {
        match.id: match.referee_team_id
        for match in protected_matches.values()
        if match.referee_team_id is not None
    }
    desired_referees = dict(protected_referees)
    assignment_sources = {
        match.id: 'manual' if match.referee_locked else 'symbolic slot'
        for match in protected_matches.values()
        if match.referee_team_id is not None
    }
    assignment_counts = Counter(protected_referees.values())

    for match in protected_matches.values():
        if match.referee_team_id is None:
            source = 'manual lock' if match.referee_locked else 'symbolic referee slot'
            result.unresolved.append(
                UnresolvedRefereeAssignment(
                    match,
                    f'{source} has no resolved referee team',
                )
            )
            continue
        if match.id in invalid_schedule_reasons:
            result.warnings.append(
                f'{_match_label(match)}: {invalid_schedule_reasons[match.id]}; '
                'preserved its protected referee assignment'
            )
            continue
        warning = _protected_assignment_warning(
            match,
            match.referee_team_id,
            timed_matches,
            participants_by_match,
            protected_referees,
        )
        if warning:
            result.warnings.append(
                f'{_match_label(match)}: {warning}; preserved its protected assignment'
            )

    automatic_matches = [
        match for match in matches if match.id not in protected_matches
    ]
    for match in automatic_matches:
        event = match.schedule_event
        invalid_reason = invalid_schedule_reasons.get(match.id)
        if invalid_reason:
            result.unresolved.append(
                UnresolvedRefereeAssignment(match, invalid_reason)
            )
            continue

        overlapping_matches = [
            other
            for other in timed_matches
            if _events_overlap(event, other.schedule_event)
        ]
        unresolved_participants = [
            other
            for other in overlapping_matches
            if not participants_by_match[other.id][1]
        ]
        if unresolved_participants:
            labels = ', '.join(
                _match_label(other) for other in unresolved_participants
            )
            result.unresolved.append(
                UnresolvedRefereeAssignment(
                    match,
                    f'cannot safely allocate while participant slots are unresolved: {labels}',
                )
            )
            continue

        playing_team_ids = set()
        for other in overlapping_matches:
            playing_team_ids.update(participants_by_match[other.id][0])

        busy_referee_ids = {
            team_id
            for other_id, team_id in desired_referees.items()
            if other_id != match.id
            and other_id in participants_by_match
            and _events_overlap(
                event,
                matches_by_id[other_id].schedule_event,
            )
        }
        eligible_teams = [
            team
            for team in teams
            if team.id not in playing_team_ids
            and team.id not in busy_referee_ids
        ]
        if not eligible_teams:
            result.unresolved.append(
                UnresolvedRefereeAssignment(
                    match,
                    'no eligible team is free from playing and referee conflicts',
                )
            )
            continue

        referee = min(
            eligible_teams,
            key=lambda team: (
                assignment_counts[team.id],
                _adjacent_match_count(
                    team.id,
                    event,
                    timed_matches,
                    participants_by_match,
                ),
                team.name.casefold(),
                team.id,
            ),
        )
        desired_referees[match.id] = referee.id
        assignment_sources[match.id] = 'automatic'
        assignment_counts[referee.id] += 1

    for match in automatic_matches:
        desired_team_id = desired_referees.get(match.id)
        if match.referee_team_id == desired_team_id:
            continue
        if match.referee_team_id is not None and desired_team_id is None:
            result.stale_assignments_cleared += 1
        match.referee_team = teams_by_id.get(desired_team_id)
        match.save(update_fields=['referee_team'])
        result.fields_updated += 1

    for match in matches:
        team_id = desired_referees.get(match.id)
        if team_id is None:
            continue
        result.assignments.append(
            RefereeAssignment(
                match=match,
                team=teams_by_id[team_id],
                source=assignment_sources[match.id],
            )
        )

    result.team_counts = {
        team: assignment_counts[team.id]
        for team in teams
    }
    return result
