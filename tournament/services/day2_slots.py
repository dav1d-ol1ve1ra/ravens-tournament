from dataclasses import dataclass

from django.db import transaction

from tournament.models import Group, Match, Team
from tournament.services.standings import calculate_group_stage_standings


# Day 2 still deliberately represents the currently seeded 3x3 format.
GROUP_CODES = ('A', 'B', 'C')
GROUP_SLOTS = {
    code: tuple(f'{code}{position}' for position in range(1, 4))
    for code in GROUP_CODES
}
RANKING_SLOTS = frozenset(
    f'{position}{group}' for group in GROUP_CODES for position in range(1, 4)
)
MATCH_SLOT_FIELDS = (
    ('home_slot', 'home_team'),
    ('away_slot', 'away_team'),
    ('referee_slot', 'referee_team'),
)


def _uses_legacy_three_by_three_format():
    configured_codes = set(Group.objects.values_list('code', flat=True))
    if configured_codes and configured_codes != set(GROUP_CODES):
        return False

    legacy_slots = {slot for slots in GROUP_SLOTS.values() for slot in slots}
    assigned_slots = set(
        Team.objects.exclude(group_slot='').values_list('group_slot', flat=True)
    )
    return not any(slot not in legacy_slots for slot in assigned_slots)


@dataclass
class Day2SlotResolutionResult:
    resolved_slots: dict[str, Team]
    unresolved_slots: dict[str, str]
    fields_updated: int = 0
    matches_updated: int = 0
    stale_fields_cleared: int = 0


def _required_pairs(group_code):
    first, second, third = GROUP_SLOTS[group_code]
    return (
        frozenset((first, second)),
        frozenset((second, third)),
        frozenset((first, third)),
    )


def _missing_group_stage_pairs():
    finished_pairs = {code: set() for code in GROUP_CODES}
    finished_matches = Match.objects.filter(
        day=1,
        phase='group_stage',
        status=Match.Status.FINISHED,
        home_score__isnull=False,
        away_score__isnull=False,
    ).values_list('home_slot', 'away_slot')

    for home_slot, away_slot in finished_matches:
        for group_code in GROUP_CODES:
            group_slots = GROUP_SLOTS[group_code]
            if home_slot in group_slots and away_slot in group_slots:
                finished_pairs[group_code].add(frozenset((home_slot, away_slot)))
                break

    return {
        code: [
            ' vs '.join(sorted(pair))
            for pair in _required_pairs(code)
            if pair not in finished_pairs[code]
        ]
        for code in GROUP_CODES
    }


def _requested_ranking_slots(matches):
    return {
        getattr(match, slot_field)
        for match in matches
        for slot_field, _ in MATCH_SLOT_FIELDS
        if getattr(match, slot_field) in RANKING_SLOTS
    }


def _resolve_ranking_slots(requested_slots):
    if not _uses_legacy_three_by_three_format():
        return {}, {
            slot: (
                'Automatic ranking-slot resolution is disabled for the current '
                'tournament format'
            )
            for slot in requested_slots
        }

    standings = calculate_group_stage_standings()
    missing_pairs = _missing_group_stage_pairs()
    resolved_slots = {}
    unresolved_slots = {}

    for slot in sorted(requested_slots, key=lambda value: (value[1], value[0])):
        position = int(slot[0])
        group_code = slot[1]

        if missing_pairs[group_code]:
            missing = ', '.join(missing_pairs[group_code])
            unresolved_slots[slot] = (
                f'Group {group_code} is incomplete; missing finished result(s): {missing}'
            )
            continue

        rows = standings[group_code]
        row = next((item for item in rows if item.position == position), None)
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
def resolve_day2_slots():
    """Resolve Day 2 ranking slots and clear assignments that became stale."""
    matches = list(Match.objects.filter(day=2))
    requested_slots = _requested_ranking_slots(matches)
    resolved_slots, unresolved_slots = _resolve_ranking_slots(requested_slots)

    fields_updated = 0
    matches_updated = 0
    stale_fields_cleared = 0

    for match in matches:
        changed_fields = []
        for slot_field, team_field in MATCH_SLOT_FIELDS:
            slot = getattr(match, slot_field)
            if slot not in RANKING_SLOTS:
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

    return Day2SlotResolutionResult(
        resolved_slots=resolved_slots,
        unresolved_slots=unresolved_slots,
        fields_updated=fields_updated,
        matches_updated=matches_updated,
        stale_fields_cleared=stale_fields_cleared,
    )
