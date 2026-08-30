COUNTRY_FLAGS = {
    'Portugal': '🇵🇹',
    'United Kingdom': '🇬🇧',
    'Netherlands': '🇳🇱',
    'Hungary': '🇭🇺',
}


def participant_name(match, side):
    team = getattr(match, f'{side}_team')
    if team:
        return team.name
    slot = getattr(match, f'{side}_slot')
    if slot:
        return slot
    source = getattr(match, f'{side}_source_match', None)
    outcome = getattr(match, f'{side}_source_outcome', '')
    if source and outcome:
        source_label = source.match_code or f'Match {source.pk}'
        return f'{outcome.title()} {source_label}'
    return 'TBD'


def team_initials(team):
    return ''.join(word[0].upper() for word in team.name.split())
