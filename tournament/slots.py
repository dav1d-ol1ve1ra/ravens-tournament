import re


DIRECT_GROUP_SLOT_PATTERN = re.compile(
    r'^(?P<group_code>[A-Za-z]+)(?P<position>[1-9]\d*)$'
)
LOWER_SLOT_PATTERN = re.compile(r'^L[1-9]\d*$')


def parse_direct_group_slot(slot, group_codes=None):
    """Parse a direct group slot, excluding ranking and reserved lower slots."""
    if not slot or LOWER_SLOT_PATTERN.fullmatch(slot):
        return None

    match = DIRECT_GROUP_SLOT_PATTERN.fullmatch(slot)
    if match is None:
        return None

    group_code = match.group('group_code')
    if group_codes is not None and group_code not in group_codes:
        return None

    return group_code, int(match.group('position'))
