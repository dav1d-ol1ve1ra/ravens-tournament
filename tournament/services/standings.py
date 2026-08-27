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


@dataclass(frozen=True)
class RoundRobinCompletion:
    expected_matches: int
    scheduled_matches: int
    finished_matches: int
    schedule_complete: bool

    @property
    def is_complete(self):
        return self.schedule_complete and self.finished_matches == self.expected_matches


def calculate_round_robin_completion(participant_slots, matches):
    """Determine round-robin completeness from its participants and match data."""
    participant_slots = set(participant_slots)
    expected_pairs = {
        frozenset((home_slot, away_slot))
        for home_slot in participant_slots
        for away_slot in participant_slots
        if home_slot < away_slot
    }
    matches = list(matches)
    scheduled_pairs = [
        frozenset((match.home_slot, match.away_slot))
        for match in matches
    ]
    schedule_complete = (
        len(participant_slots) >= 2
        and len(matches) == len(expected_pairs)
        and set(scheduled_pairs) == expected_pairs
    )
    finished_matches = sum(
        1
        for match in matches
        if match.status == Match.Status.FINISHED
        and match.home_score is not None
        and match.away_score is not None
    )
    return RoundRobinCompletion(
        expected_matches=len(expected_pairs),
        scheduled_matches=len(matches),
        finished_matches=finished_matches,
        schedule_complete=schedule_complete,
    )


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


def _order_rows(rows, results, manual_tiebreaks_enabled):
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
                if manual_tiebreaks_enabled:
                    for row in rows_with_same_key:
                        row.requires_manual_tiebreak = True
            else:
                rows_with_same_key[0].position = len(ordered_rows) + 1
            ordered_rows.extend(rows_with_same_key)

    return ordered_rows


def calculate_standings_rows(
    teams,
    results,
    *,
    manual_tiebreaks_enabled=True,
):
    """Calculate and order one standings table from teams and scored results."""
    rows_by_team = {team.id: StandingRow(team=team) for team in teams}
    valid_results = []

    for home_team, away_team, home_score, away_score in results:
        if home_team.id not in rows_by_team or away_team.id not in rows_by_team:
            continue
        _record_result(
            rows_by_team[home_team.id],
            rows_by_team[away_team.id],
            home_score,
            away_score,
        )
        valid_results.append(
            (home_team.id, away_team.id, home_score, away_score)
        )

    return _order_rows(
        list(rows_by_team.values()),
        valid_results,
        manual_tiebreaks_enabled,
    )


def _match_group_code(match):
    if match.group_id:
        return match.group.code
    home_slot = parse_direct_group_slot(match.home_slot)
    away_slot = parse_direct_group_slot(match.away_slot)
    if home_slot and away_slot and home_slot[0] == away_slot[0]:
        return home_slot[0]
    return None


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

    teams_by_group = {code: [] for code in group_codes}
    results_by_group = {code: [] for code in group_codes}
    for team in teams:
        group_code = team_group_codes.get(team.id)
        if group_code is not None:
            teams_by_group[group_code].append(team)

    matches = list(
        Match.objects.filter(phase='group_stage').select_related(
            'group',
            'home_team',
            'away_team',
        )
    )

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

        group_code = team_group_codes.get(home_team.id)
        if group_code != team_group_codes.get(away_team.id):
            continue
        if group_code not in results_by_group:
            continue
        results_by_group[group_code].append(
            (home_team, away_team, match.home_score, match.away_score)
        )

    standings = {}
    for code in group_codes:
        group_matches = [
            match for match in matches if _match_group_code(match) == code
        ]
        completion = calculate_round_robin_completion(
            (team.group_slot for team in teams_by_group[code]),
            group_matches,
        )
        standings[code] = calculate_standings_rows(
            teams_by_group[code],
            results_by_group[code],
            manual_tiebreaks_enabled=completion.is_complete,
        )
    return standings
