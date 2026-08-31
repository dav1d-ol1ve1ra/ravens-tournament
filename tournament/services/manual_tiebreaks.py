from dataclasses import dataclass

from django.db import transaction

from tournament.models import ManualTiebreakResolution, Team


LOWER_SCOPE = 'lower_league'


def group_scope(group_code):
    return f'group:{group_code}'


def team_set_signature(team_ids):
    return ','.join(str(team_id) for team_id in sorted(set(team_ids)))


def get_manual_team_order(scope, team_ids):
    """Return a valid stored order only when its team set matches exactly."""
    team_ids = [int(team_id) for team_id in team_ids]
    signature = team_set_signature(team_ids)
    resolution = ManualTiebreakResolution.objects.filter(
        scope=scope,
        team_set_signature=signature,
    ).first()
    if resolution is None:
        return None

    try:
        ordered_ids = [int(team_id) for team_id in resolution.team_order]
    except (TypeError, ValueError):
        return None
    if len(ordered_ids) != len(team_ids) or set(ordered_ids) != set(team_ids):
        return None
    return ordered_ids


@transaction.atomic
def save_manual_team_order(scope, tied_team_ids, ordered_team_ids):
    tied_team_ids = [int(team_id) for team_id in tied_team_ids]
    ordered_team_ids = [int(team_id) for team_id in ordered_team_ids]
    if (
        len(ordered_team_ids) != len(tied_team_ids)
        or set(ordered_team_ids) != set(tied_team_ids)
    ):
        raise ValueError('The manual order must contain every tied team exactly once.')

    signature = team_set_signature(tied_team_ids)
    resolution, _ = ManualTiebreakResolution.objects.update_or_create(
        scope=scope,
        team_set_signature=signature,
        defaults={'team_order': ordered_team_ids},
    )
    return resolution


@dataclass(frozen=True)
class ManualTiebreakRequirement:
    scope: str
    competition_label: str
    signature: str
    teams: tuple[Team, ...]
    current_order: tuple[Team, ...] = ()


def _requirements_from_rows(scope, competition_label, rows):
    tied_rows = {}
    for row in rows:
        if row.requires_manual_tiebreak and row.manual_tiebreak_signature:
            tied_rows.setdefault(row.manual_tiebreak_signature, []).append(row)
    return [
        ManualTiebreakRequirement(
            scope=scope,
            competition_label=competition_label,
            signature=signature,
            teams=tuple(row.team for row in grouped_rows),
        )
        for signature, grouped_rows in tied_rows.items()
    ]


def get_manual_tiebreak_state():
    """Return unresolved and active resolutions from automatic standings ties."""
    # Local imports avoid a module cycle: standings uses the persistence helpers above.
    from tournament.services.lower_standings import calculate_lower_standings
    from tournament.services.standings import calculate_group_stage_standings

    automatic_requirements = []
    for code, rows in calculate_group_stage_standings(
        apply_manual_tiebreaks=False
    ).items():
        automatic_requirements.extend(
            _requirements_from_rows(group_scope(code), f'Group {code}', rows)
        )

    lower = calculate_lower_standings(apply_manual_tiebreaks=False)
    if lower.is_resolved:
        automatic_requirements.extend(
            _requirements_from_rows(LOWER_SCOPE, 'Lower League', lower.rows)
        )

    unresolved = []
    resolved = []
    for requirement in automatic_requirements:
        order_ids = get_manual_team_order(
            requirement.scope,
            (team.pk for team in requirement.teams),
        )
        if order_ids is None:
            unresolved.append(requirement)
            continue
        teams_by_id = {team.pk: team for team in requirement.teams}
        resolved.append(
            ManualTiebreakRequirement(
                scope=requirement.scope,
                competition_label=requirement.competition_label,
                signature=requirement.signature,
                teams=requirement.teams,
                current_order=tuple(teams_by_id[team_id] for team_id in order_ids),
            )
        )
    return unresolved, resolved


def get_manual_tiebreak_requirements():
    """Return genuine automatic ties that do not yet have a valid manual order."""
    unresolved, _ = get_manual_tiebreak_state()
    return unresolved
