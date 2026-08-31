from dataclasses import dataclass, field

from tournament.models import Match, Team
from tournament.services.standings import (
    StandingRow,
    calculate_round_robin_completion,
    calculate_standings_rows,
)
from tournament.services.manual_tiebreaks import LOWER_SCOPE


LOWER_PHASE = 'lower_league'


@dataclass
class LowerStandingsResult:
    rows: list[StandingRow] = field(default_factory=list)
    unresolved_slots: tuple[str, ...] = ()
    competition_complete: bool = False

    @property
    def is_resolved(self):
        return not self.unresolved_slots

    @property
    def unresolved_message(self):
        if not self.unresolved_slots:
            return ''
        return 'Lower League teams will be determined after the Group Stage.'


def calculate_lower_standings(*, apply_manual_tiebreaks=True):
    """Calculate a Lower round robin from its resolved symbolic participants."""
    matches = list(
        Match.objects.filter(phase=LOWER_PHASE)
        .select_related('home_team', 'away_team')
        .order_by('day', 'start_time', 'court', 'pk')
    )
    participant_slots = {
        slot
        for match in matches
        for slot in (match.home_slot, match.away_slot)
        if slot
    }
    if len(participant_slots) < 2:
        return LowerStandingsResult(unresolved_slots=('participant slots',))

    teams_by_slot = {}
    inconsistent_slots = set()

    for match in matches:
        for side in ('home', 'away'):
            slot = getattr(match, f'{side}_slot')
            team = getattr(match, f'{side}_team')
            if slot not in participant_slots or team is None:
                continue
            existing_team = teams_by_slot.get(slot)
            if existing_team is not None and existing_team.id != team.id:
                inconsistent_slots.add(slot)
            else:
                teams_by_slot[slot] = team

    unresolved_slots = {
        slot for slot in participant_slots if slot not in teams_by_slot
    } | inconsistent_slots
    resolved_teams = [
        teams_by_slot[slot]
        for slot in sorted(participant_slots)
        if slot in teams_by_slot and slot not in inconsistent_slots
    ]
    if len({team.id for team in resolved_teams}) != len(participant_slots):
        unresolved_slots.update(participant_slots)

    if unresolved_slots:
        return LowerStandingsResult(
            unresolved_slots=tuple(sorted(unresolved_slots)),
        )

    finished_results = []
    for match in matches:
        if (
            match.status != Match.Status.FINISHED
            or match.home_score is None
            or match.away_score is None
        ):
            continue
        home_team = match.home_team or teams_by_slot.get(match.home_slot)
        away_team = match.away_team or teams_by_slot.get(match.away_slot)
        if home_team is None or away_team is None:
            continue
        finished_results.append(
            (home_team, away_team, match.home_score, match.away_score)
        )

    completion = calculate_round_robin_completion(participant_slots, matches)
    return LowerStandingsResult(
        rows=calculate_standings_rows(
            resolved_teams,
            finished_results,
            manual_tiebreaks_enabled=completion.is_complete,
            manual_tiebreak_scope=(LOWER_SCOPE if apply_manual_tiebreaks else None),
        ),
        competition_complete=completion.is_complete,
    )
