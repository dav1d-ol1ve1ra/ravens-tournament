from dataclasses import dataclass, field

from tournament.models import Match, Team
from tournament.presentation import ordinal
from tournament.services.knockout_slots import resolve_match_outcome
from tournament.services.lower_standings import calculate_lower_standings


@dataclass
class FinalPlacement:
    position: int
    team: Team | None
    placeholder: str
    requires_manual_tiebreak: bool = False


@dataclass
class FinalRankingResult:
    placements: list[FinalPlacement] = field(default_factory=list)


UPPER_PLACEMENTS = (
    (1, 'UB-04', Match.ParticipantOutcome.WINNER, 'Winner UB-04'),
    (2, 'UB-04', Match.ParticipantOutcome.LOSER, 'Loser UB-04'),
    (3, 'UB-03', Match.ParticipantOutcome.WINNER, 'Winner UB-03'),
    (4, 'UB-03', Match.ParticipantOutcome.LOSER, 'Loser UB-03'),
)


def calculate_final_ranking():
    """Compose final placements from Upper outcomes and Lower standings."""
    upper_matches = {
        match.match_code: match
        for match in Match.objects.filter(
            match_code__in=('UB-03', 'UB-04')
        ).select_related('home_team', 'away_team')
    }
    placements = []

    for position, match_code, outcome, placeholder in UPPER_PLACEMENTS:
        team = None
        source = upper_matches.get(match_code)
        if source is not None:
            team, _ = resolve_match_outcome(source, outcome)
        placements.append(
            FinalPlacement(
                position=position,
                team=team,
                placeholder=placeholder,
            )
        )

    lower = calculate_lower_standings()
    for lower_position in range(1, 6):
        team = None
        requires_manual_tiebreak = False
        row = (
            lower.rows[lower_position - 1]
            if lower_position <= len(lower.rows)
            else None
        )
        if lower.competition_complete and row is not None:
            requires_manual_tiebreak = row.requires_manual_tiebreak
            if row.position == lower_position and not requires_manual_tiebreak:
                team = row.team
        placements.append(
            FinalPlacement(
                position=lower_position + 4,
                team=team,
                placeholder=f'{ordinal(lower_position)} Lower League',
                requires_manual_tiebreak=requires_manual_tiebreak,
            )
        )

    return FinalRankingResult(placements=placements)
