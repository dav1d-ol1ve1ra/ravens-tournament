import re
from dataclasses import dataclass

from django.db import transaction

from tournament.models import Match, Team


KNOCKOUT_SLOT_PATTERN = re.compile(
    r'^(?P<outcome>[WL])-(?P<match_code>.+)$'
)
DEPENDENCY_FIELDS = (
    (
        'home_slot',
        'home_team',
        'home_source_match',
        'home_source_outcome',
    ),
    (
        'away_slot',
        'away_team',
        'away_source_match',
        'away_source_outcome',
    ),
    ('referee_slot', 'referee_team', None, None),
)


@dataclass
class KnockoutSlotResolutionResult:
    resolved_slots: dict[str, Team]
    unresolved_slots: dict[str, str]
    fields_updated: int = 0
    matches_updated: int = 0
    stale_fields_cleared: int = 0


def _dependency_key(match, slot, team_field):
    if slot and KNOCKOUT_SLOT_PATTERN.fullmatch(slot):
        return slot
    side = team_field.removesuffix('_team')
    match_label = match.match_code or f'match {match.pk}'
    return f'{match_label} {side}'


def _resolve_source_outcome(source, outcome):
    source_label = source.match_code or f'match {source.pk}'
    if source.status != Match.Status.FINISHED:
        return None, f'Source match {source_label} is not finished'
    if source.home_team_id is None or source.away_team_id is None:
        return None, (
            f'Source match {source_label} does not have both participants resolved'
        )
    if source.home_score is None or source.away_score is None:
        return None, f'Source match {source_label} does not have both scores'
    if source.home_score == source.away_score:
        return None, (
            f'Source match {source_label} has a tied Upper knockout result'
        )

    home_won = source.home_score > source.away_score
    winner = source.home_team if home_won else source.away_team
    loser = source.away_team if home_won else source.home_team
    if outcome == Match.ParticipantOutcome.WINNER:
        return winner, None
    if outcome == Match.ParticipantOutcome.LOSER:
        return loser, None
    return None, 'Participant dependency must specify winner or loser'


def _dependency(match, fields, matches_by_code):
    slot_field, team_field, source_field, outcome_field = fields
    slot = getattr(match, slot_field)
    key = _dependency_key(match, slot, team_field)

    if source_field is not None:
        source_id = getattr(match, f'{source_field}_id')
        outcome = getattr(match, outcome_field)
        if source_id is not None or outcome:
            source = getattr(match, source_field)
            if source is None:
                return key, None, None, 'Source match dependency is missing'
            if not outcome:
                return key, None, None, (
                    'Participant dependency must specify winner or loser'
                )
            return key, source, outcome, None

    reference = KNOCKOUT_SLOT_PATTERN.fullmatch(slot or '')
    if reference is None:
        return None
    source = matches_by_code.get(reference.group('match_code'))
    if source is None:
        return (
            key,
            None,
            None,
            f'Source match {reference.group("match_code")} does not exist',
        )
    outcome = (
        Match.ParticipantOutcome.WINNER
        if reference.group('outcome') == 'W'
        else Match.ParticipantOutcome.LOSER
    )
    return key, source, outcome, None


@transaction.atomic
def resolve_knockout_slots():
    """Resolve explicit or symbolic winner/loser match dependencies."""
    matches = list(
        Match.objects.select_related(
            'home_team',
            'away_team',
            'referee_team',
            'home_source_match__home_team',
            'home_source_match__away_team',
            'away_source_match__home_team',
            'away_source_match__away_team',
        ).all()
    )
    matches_by_code = {
        match.match_code: match for match in matches if match.match_code
    }
    resolved_slots = {}
    unresolved_slots = {}
    fields_updated = 0
    matches_updated = 0
    stale_fields_cleared = 0

    for match in matches:
        changed_fields = []
        for fields in DEPENDENCY_FIELDS:
            dependency = _dependency(match, fields, matches_by_code)
            if dependency is None:
                continue
            key, source, outcome, dependency_error = dependency
            if dependency_error:
                resolved_team = None
                unresolved_slots[key] = dependency_error
            else:
                resolved_team, resolution_error = _resolve_source_outcome(
                    source,
                    outcome,
                )
                if resolution_error:
                    unresolved_slots[key] = resolution_error
                else:
                    resolved_slots[key] = resolved_team

            team_field = fields[1]
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
