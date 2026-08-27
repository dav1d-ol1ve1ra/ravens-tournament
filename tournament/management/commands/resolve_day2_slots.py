from tournament.management.commands.resolve_progression_slots import (
    Command as ProgressionCommand,
)


class Command(ProgressionCommand):
    help = 'Deprecated alias for resolve_progression_slots.'
