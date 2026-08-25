COUNTRY_FLAGS = {
    'Portugal': '🇵🇹',
    'United Kingdom': '🇬🇧',
    'Netherlands': '🇳🇱',
    'Hungary': '🇭🇺',
}


def participant_name(match, side):
    team = getattr(match, f'{side}_team')
    return team.name if team else getattr(match, f'{side}_slot') or 'TBD'


def team_initials(team):
    return ''.join(word[0].upper() for word in team.name.split())
