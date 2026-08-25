from .models import Match, Team


GROUP_SLOTS = frozenset(
    f'{group}{position}' for group in 'ABC' for position in range(1, 4)
)


def resolve_group_stage_slots():
    """Assign teams to Day 1 group-stage match slots where teams are known."""
    matches = list(Match.objects.filter(day=1, phase='group_stage'))
    slots = {
        slot
        for match in matches
        for slot in (match.home_slot, match.away_slot, match.referee_slot)
        if slot in GROUP_SLOTS
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
            team = teams_by_slot.get(getattr(match, slot_field))
            if team and getattr(match, f'{team_field}_id') != team.id:
                setattr(match, team_field, team)
                changed_fields.append(team_field)

        if changed_fields:
            match.save(update_fields=changed_fields)
            fields_updated += len(changed_fields)
            matches_updated += 1

    return fields_updated, matches_updated
