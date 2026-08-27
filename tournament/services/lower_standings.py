from dataclasses import dataclass, field

from tournament.models import Match, Team
from tournament.services.standings import (
    StandingRow,
    calculate_round_robin_completion,
    calculate_standings_rows,
)


LOWER_SLOTS = ('L1', 'L2', 'L3', 'L4', 'L5')


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
        return (
            'Lower League participants are not resolved yet '
            f'({", ".join(self.unresolved_slots)}).'
        )


def calculate_lower_standings():
    """Calculate the Lower round robin from resolved L1-L5 participants."""
    matches = list(
        Match.objects.filter(phase='lower_round_robin')
        .select_related('home_team', 'away_team')
        .order_by('day', 'start_time', 'court', 'pk')
    )
    teams_by_slot = {}
    inconsistent_slots = set()

    for match in matches:
        for side in ('home', 'away'):
            slot = getattr(match, f'{side}_slot')
            team = getattr(match, f'{side}_team')
            if slot not in LOWER_SLOTS or team is None:
                continue
            existing_team = teams_by_slot.get(slot)
            if existing_team is not None and existing_team.id != team.id:
                inconsistent_slots.add(slot)
            else:
                teams_by_slot[slot] = team

    unresolved_slots = {
        slot for slot in LOWER_SLOTS if slot not in teams_by_slot
    } | inconsistent_slots
    resolved_teams = [
        teams_by_slot[slot]
        for slot in LOWER_SLOTS
        if slot in teams_by_slot and slot not in inconsistent_slots
    ]
    if len({team.id for team in resolved_teams}) != len(LOWER_SLOTS):
        unresolved_slots.update(LOWER_SLOTS)

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

    completion = calculate_round_robin_completion(LOWER_SLOTS, matches)
    return LowerStandingsResult(
        rows=calculate_standings_rows(
            resolved_teams,
            finished_results,
            manual_tiebreaks_enabled=completion.is_complete,
        ),
        competition_complete=completion.is_complete,
    )
