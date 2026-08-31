from dataclasses import dataclass

from django.db import transaction

from tournament.models import Match
from tournament.services.database_backup import DatabaseBackup, create_database_backup
from tournament.services.knockout_slots import resolve_knockout_slots
from tournament.services.progression_slots import resolve_progression_slots
from tournament.slot_resolution import resolve_group_stage_slots


@dataclass(frozen=True)
class ResultResetResult:
    backup: DatabaseBackup
    matches_reset: int
    direct_fields_restored: int
    direct_matches_updated: int
    derived_fields_cleared: int


def reset_tournament_results():
    """Back up and reset result-derived state without rebuilding the tournament."""
    backup = create_database_backup(command_name='reset_results')

    with transaction.atomic():
        matches_reset = Match.objects.count()
        Match.objects.update(
            home_score=None,
            away_score=None,
            status=Match.Status.SCHEDULED,
        )
        progression_result = resolve_progression_slots()
        knockout_result = resolve_knockout_slots()
        direct_fields, direct_matches = resolve_group_stage_slots()

    return ResultResetResult(
        backup=backup,
        matches_reset=matches_reset,
        direct_fields_restored=direct_fields,
        direct_matches_updated=direct_matches,
        derived_fields_cleared=(
            progression_result.stale_fields_cleared
            + knockout_result.stale_fields_cleared
        ),
    )
