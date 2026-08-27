from dataclasses import dataclass
from itertools import combinations

from django.db import transaction

from tournament.models import Group, Match, Team
from tournament.services.standings import calculate_group_stage_standings
from tournament.slots import parse_direct_group_slot


SLOT_DEFINITIONS = {
    '1A': ('A', 1),
    '2A': ('A', 2),
    'L1': ('A', 3),
    'L2': ('A', 4),
    'L3': ('A', 5),
    '1B': ('B', 1),
    '2B': ('B', 2),
    'L4': ('B', 3),
    'L5': ('B', 4),
}
MATCH_SLOT_FIELDS = (
    ('home_slot', 'home_team'),
    ('away_slot', 'away_team'),
    ('referee_slot', 'referee_team'),
)


@dataclass
class ProgressionSlotResolutionResult:
    resolved_slots: dict[str, Team]
    unresolved_slots: dict[str, str]
    fields_updated: int = 0
    matches_updated: int = 0
    stale_fields_cleared: int = 0


def _match_group_code(match):
    if match.group_id:
        return match.group.code

    home_slot = parse_direct_group_slot(match.home_slot)
    away_slot = parse_direct_group_slot(match.away_slot)
    if home_slot and away_slot and home_slot[0] == away_slot[0]:
        return home_slot[0]
    return None


def _group_incomplete_reason(group, rows, group_stage_matches):
    team_slots = {row.team.group_slot for row in rows}
    if len(team_slots) < 2:
        return f'{group.name} does not have enough assigned teams'

    expected_pairs = {
        frozenset(pair) for pair in combinations(sorted(team_slots), 2)
    }
    matches = [
        match
        for match in group_stage_matches
        if _match_group_code(match) == group.code
    ]
    scheduled_pairs = [
        frozenset((match.home_slot, match.away_slot)) for match in matches
    ]

    if len(matches) != len(expected_pairs) or set(scheduled_pairs) != expected_pairs:
        return (
            f'{group.name} schedule is incomplete; expected '
            f'{len(expected_pairs)} round-robin match(es), found {len(matches)}'
        )

    finished_matches = [
        match
        for match in matches
        if match.status == Match.Status.FINISHED
        and match.home_score is not None
        and match.away_score is not None
    ]
    if len(finished_matches) != len(matches):
        return (
            f'{group.name} is incomplete; {len(finished_matches)} of '
            f'{len(matches)} Group Stage match(es) are finished'
        )

    return None


def _calculate_slot_assignments():
    standings = calculate_group_stage_standings()
    groups = {
        group.code: group
        for group in Group.objects.filter(
            code__in={definition[0] for definition in SLOT_DEFINITIONS.values()}
        ).order_by('pk')
    }
    group_stage_matches = list(
        Match.objects.filter(phase='group_stage').select_related('group')
    )
    incomplete_reasons = {}

    for group_code in {definition[0] for definition in SLOT_DEFINITIONS.values()}:
        group = groups.get(group_code)
        if group is None:
            incomplete_reasons[group_code] = f'Group {group_code} does not exist'
            continue
        incomplete_reasons[group_code] = _group_incomplete_reason(
            group,
            standings.get(group_code, []),
            group_stage_matches,
        )

    resolved_slots = {}
    unresolved_slots = {}
    for slot, (group_code, position) in SLOT_DEFINITIONS.items():
        incomplete_reason = incomplete_reasons[group_code]
        if incomplete_reason:
            unresolved_slots[slot] = incomplete_reason
            continue

        rows = standings[group_code]
        row = next((row for row in rows if row.position == position), None)
        if row is not None and not row.requires_manual_tiebreak:
            resolved_slots[slot] = row.team
            continue

        if position <= len(rows) and rows[position - 1].requires_manual_tiebreak:
            unresolved_slots[slot] = (
                f'Group {group_code} position {position} requires a manual tie-break'
            )
        else:
            unresolved_slots[slot] = (
                f'Group {group_code} position {position} is unavailable; '
                'check team slot assignments'
            )

    return resolved_slots, unresolved_slots


@transaction.atomic
def resolve_progression_slots():
    """Resolve confirmed-format ranking/Lower slots and clear stale assignments."""
    resolved_slots, unresolved_slots = _calculate_slot_assignments()
    matches = list(Match.objects.all())
    fields_updated = 0
    matches_updated = 0
    stale_fields_cleared = 0

    for match in matches:
        changed_fields = []
        for slot_field, team_field in MATCH_SLOT_FIELDS:
            slot = getattr(match, slot_field)
            if slot not in SLOT_DEFINITIONS:
                continue

            resolved_team = resolved_slots.get(slot)
            current_team_id = getattr(match, f'{team_field}_id')
            resolved_team_id = resolved_team.id if resolved_team else None
            if current_team_id == resolved_team_id:
                continue

            if current_team_id is not None and resolved_team_id is None:
                stale_fields_cleared += 1
            setattr(match, team_field, resolved_team)
            changed_fields.append(team_field)

        if changed_fields:
            match.save(update_fields=changed_fields)
            fields_updated += len(changed_fields)
            matches_updated += 1

    return ProgressionSlotResolutionResult(
        resolved_slots=resolved_slots,
        unresolved_slots=unresolved_slots,
        fields_updated=fields_updated,
        matches_updated=matches_updated,
        stale_fields_cleared=stale_fields_cleared,
    )
