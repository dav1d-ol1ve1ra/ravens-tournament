"""Deprecated compatibility aliases for the confirmed progression service."""

from tournament.services.progression_slots import (
    ProgressionSlotResolutionResult as Day2SlotResolutionResult,
    resolve_progression_slots,
)


def resolve_day2_slots():
    return resolve_progression_slots()
