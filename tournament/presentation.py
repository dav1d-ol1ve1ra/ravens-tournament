from tournament.slots import parse_ranking_slot


COUNTRY_FLAGS = {
    'Portugal': '🇵🇹',
    'United Kingdom': '🇬🇧',
    'England': '🏴',
    'Netherlands': '🇳🇱',
    'Hungary': '🇭🇺',
}


def ordinal(position):
    if 10 < position % 100 < 14:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(position % 10, 'th')
    return f'{position}{suffix}'


def participant_slot_label(slot):
    ranking_slot = parse_ranking_slot(slot)
    if ranking_slot:
        group_code, position = ranking_slot
        return f'{ordinal(position)} Group {group_code}'
    if slot.startswith('W-'):
        return f'Winner {slot[2:]}'
    if slot.startswith('L-'):
        return f'Loser {slot[2:]}'
    return slot


def participant_name(match, side):
    team = getattr(match, f'{side}_team')
    if team:
        return team.name
    slot = getattr(match, f'{side}_slot')
    if slot:
        return participant_slot_label(slot)
    source = getattr(match, f'{side}_source_match', None)
    outcome = getattr(match, f'{side}_source_outcome', '')
    if source and outcome:
        source_label = source.match_code or f'Match {source.pk}'
        return f'{outcome.title()} {source_label}'
    return 'TBD'


def team_initials(team):
    return ''.join(word[0].upper() for word in team.name.split())
