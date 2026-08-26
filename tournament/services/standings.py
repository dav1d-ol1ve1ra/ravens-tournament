from dataclasses import dataclass
from itertools import groupby

from tournament.models import Group, Match, Team
from tournament.slots import parse_direct_group_slot


@dataclass
class StandingRow:
    team: Team
    position: int | None = None
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    sets_for: int = 0
    sets_against: int = 0
    ranking_points: int = 0
    requires_manual_tiebreak: bool = False

    @property
    def set_difference(self):
        return self.sets_for - self.sets_against


def _award_ranking_points(home_score, away_score):
    if home_score > away_score:
        return 2, 0
    if home_score < away_score:
        return 0, 2
    return 1, 1


def _record_result(home_row, away_row, home_score, away_score):
    home_row.played += 1
    away_row.played += 1
    home_row.sets_for += home_score
    home_row.sets_against += away_score
    away_row.sets_for += away_score
    away_row.sets_against += home_score

    home_points, away_points = _award_ranking_points(home_score, away_score)
    home_row.ranking_points += home_points
    away_row.ranking_points += away_points

    if home_score > away_score:
        home_row.wins += 1
        away_row.losses += 1
    elif home_score < away_score:
        away_row.wins += 1
        home_row.losses += 1
    else:
        home_row.draws += 1
        away_row.draws += 1


def _tie_break_key(row, head_to_head_points):
    return (
        -head_to_head_points,
        -row.set_difference,
        -row.sets_for,
        row.sets_against,
    )


def _order_rows(rows, results):
    ordered_rows = []
    points_buckets = {}
    for row in rows:
        points_buckets.setdefault(row.ranking_points, []).append(row)

    for ranking_points in sorted(points_buckets, reverse=True):
        tied_rows = points_buckets[ranking_points]
        tied_team_ids = {row.team.id for row in tied_rows}
        head_to_head_points = {team_id: 0 for team_id in tied_team_ids}

        if len(tied_rows) > 1:
            for home_id, away_id, home_score, away_score in results:
                if home_id in tied_team_ids and away_id in tied_team_ids:
                    home_points, away_points = _award_ranking_points(
                        home_score, away_score
                    )
                    head_to_head_points[home_id] += home_points
                    head_to_head_points[away_id] += away_points

        tied_rows.sort(
            key=lambda row: _tie_break_key(
                row, head_to_head_points[row.team.id]
            )
        )

        tie_key = lambda row: _tie_break_key(
            row, head_to_head_points[row.team.id]
        )
        for _, rows_with_same_key in groupby(tied_rows, key=tie_key):
            rows_with_same_key = list(rows_with_same_key)
            if len(rows_with_same_key) > 1:
                for row in rows_with_same_key:
                    row.requires_manual_tiebreak = True
            else:
                rows_with_same_key[0].position = len(ordered_rows) + 1
            ordered_rows.extend(rows_with_same_key)

    return ordered_rows


def calculate_group_stage_standings():
    """Calculate standings for every configured or assigned tournament group."""
    configured_codes = list(
        Group.objects.order_by('code', 'pk').values_list('code', flat=True)
    )
    group_codes = list(dict.fromkeys(configured_codes))
    configured_code_set = set(group_codes) if group_codes else None
    teams = list(Team.objects.exclude(group_slot='').order_by('pk'))
    teams_by_slot = {team.group_slot: team for team in teams}
    team_group_codes = {}

    for team in teams:
        parsed_slot = parse_direct_group_slot(team.group_slot, configured_code_set)
        if parsed_slot is None:
            continue
        group_code, _ = parsed_slot
        team_group_codes[team.id] = group_code
        if group_code not in group_codes:
            group_codes.append(group_code)

    rows_by_group = {code: {} for code in group_codes}
    results_by_group = {code: [] for code in group_codes}
    for team in teams:
        group_code = team_group_codes.get(team.id)
        if group_code is not None:
            rows_by_group[group_code][team.id] = StandingRow(team=team)

    matches = Match.objects.filter(
        phase='group_stage',
        status=Match.Status.FINISHED,
        home_score__isnull=False,
        away_score__isnull=False,
    ).select_related('home_team', 'away_team')

    for match in matches:
        home_team = match.home_team or teams_by_slot.get(match.home_slot)
        away_team = match.away_team or teams_by_slot.get(match.away_slot)
        if home_team is None or away_team is None:
            continue

        group_code = team_group_codes.get(home_team.id)
        if group_code != team_group_codes.get(away_team.id):
            continue
        group_rows = rows_by_group.get(group_code, {})
        if home_team.id not in group_rows or away_team.id not in group_rows:
            continue

        _record_result(
            group_rows[home_team.id],
            group_rows[away_team.id],
            match.home_score,
            match.away_score,
        )
        results_by_group[group_code].append(
            (home_team.id, away_team.id, match.home_score, match.away_score)
        )

    return {
        code: _order_rows(list(rows_by_group[code].values()), results_by_group[code])
        for code in group_codes
    }
