import re
from dataclasses import dataclass

from django.db import transaction

from tournament.models import Match, Team


KNOCKOUT_SLOT_PATTERN = re.compile(
    r'^(?P<outcome>[WL])-(?P<match_code>.+)$'
)
MATCH_SLOT_FIELDS = (
    ('home_slot', 'home_team'),
    ('away_slot', 'away_team'),
    ('referee_slot', 'referee_team'),
)


@dataclass
class KnockoutSlotResolutionResult:
    resolved_slots: dict[str, Team]
    unresolved_slots: dict[str, str]
    fields_updated: int = 0
    matches_updated: int = 0
    stale_fields_cleared: int = 0


def _referenced_knockout_slots(matches):
    return {
        slot
        for match in matches
        for slot_field, _ in MATCH_SLOT_FIELDS
        if (slot := getattr(match, slot_field))
        and KNOCKOUT_SLOT_PATTERN.fullmatch(slot)
    }


def _resolve_symbolic_slots(symbolic_slots, matches_by_code):
    resolved_slots = {}
    unresolved_slots = {}

    for slot in sorted(symbolic_slots):
        reference = KNOCKOUT_SLOT_PATTERN.fullmatch(slot)
        outcome = reference.group('outcome')
        match_code = reference.group('match_code')
        source = matches_by_code.get(match_code)

        if source is None:
            unresolved_slots[slot] = f'Source match {match_code} does not exist'
            continue
        if source.status != Match.Status.FINISHED:
            unresolved_slots[slot] = f'Source match {match_code} is not finished'
            continue
        if source.home_team_id is None or source.away_team_id is None:
            unresolved_slots[slot] = (
                f'Source match {match_code} does not have both participants resolved'
            )
            continue
        if source.home_score is None or source.away_score is None:
            unresolved_slots[slot] = f'Source match {match_code} does not have both scores'
            continue
        if source.home_score == source.away_score:
            unresolved_slots[slot] = (
                f'Source match {match_code} has a tied Upper knockout result'
            )
            continue

        home_won = source.home_score > source.away_score
        if outcome == 'W':
            resolved_slots[slot] = source.home_team if home_won else source.away_team
        else:
            resolved_slots[slot] = source.away_team if home_won else source.home_team

    return resolved_slots, unresolved_slots


@transaction.atomic
def resolve_knockout_slots():
    """Resolve W-/L- match references and clear invalid stale assignments."""
    matches = list(
        Match.objects.select_related(
            'home_team', 'away_team', 'referee_team'
        ).all()
    )
    symbolic_slots = _referenced_knockout_slots(matches)
    matches_by_code = {
        match.match_code: match for match in matches if match.match_code
    }
    resolved_slots, unresolved_slots = _resolve_symbolic_slots(
        symbolic_slots,
        matches_by_code,
    )

    fields_updated = 0
    matches_updated = 0
    stale_fields_cleared = 0

    for match in matches:
        changed_fields = []
        for slot_field, team_field in MATCH_SLOT_FIELDS:
            slot = getattr(match, slot_field)
            if slot not in symbolic_slots:
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

    return KnockoutSlotResolutionResult(
        resolved_slots=resolved_slots,
        unresolved_slots=unresolved_slots,
        fields_updated=fields_updated,
        matches_updated=matches_updated,
        stale_fields_cleared=stale_fields_cleared,
    )
