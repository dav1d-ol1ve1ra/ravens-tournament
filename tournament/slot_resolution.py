from django.db import transaction

from .models import Group, Match, Team
from .slots import parse_direct_group_slot


@transaction.atomic
def resolve_group_stage_slots():
    """Assign teams to Day 1 group-stage match slots where teams are known."""
    matches = list(Match.objects.filter(day=1, phase='group_stage'))
    group_codes = set(Group.objects.values_list('code', flat=True))
    slots = {
        slot
        for match in matches
        for slot in (match.home_slot, match.away_slot, match.referee_slot)
        if parse_direct_group_slot(slot, group_codes) is not None
    }
    teams_by_slot = {
        team.group_slot: team
        for team in Team.objects.filter(group_slot__in=slots)
    }

    fields_updated = 0
    matches_updated = 0
    for match in matches:
        changed_fields = []
        for slot_field, team_field in (
            ('home_slot', 'home_team'),
            ('away_slot', 'away_team'),
            ('referee_slot', 'referee_team'),
        ):
            slot = getattr(match, slot_field)
            if parse_direct_group_slot(slot, group_codes) is None:
                continue

            team = teams_by_slot.get(slot)
            team_id = team.id if team else None
            if getattr(match, f'{team_field}_id') != team_id:
                setattr(match, team_field, team)
                changed_fields.append(team_field)

        if changed_fields:
            match.save(update_fields=changed_fields)
            fields_updated += len(changed_fields)
            matches_updated += 1

    return fields_updated, matches_updated
