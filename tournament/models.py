from django.core.exceptions import ValidationError
from django.db import models


class Team(models.Model):
    name = models.CharField(max_length=100)
    short_name = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, blank=True)
    logo = models.FileField(upload_to='team_logos/', blank=True)
    group_slot = models.CharField(max_length=20, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['group_slot'],
                condition=~models.Q(group_slot=''),
                name='unique_nonempty_team_group_slot',
            )
        ]

    def __str__(self):
        return self.short_name or self.name


class Group(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=1)

    def __str__(self):
        return self.name


class ScheduleEvent(models.Model):
    class EventType(models.TextChoices):
        MATCH = 'match', 'Match'
        OPENING_CEREMONY = 'opening_ceremony', 'Opening Ceremony'
        LUNCH = 'lunch', 'Lunch'
        CLOSING_CEREMONY = 'closing_ceremony', 'Closing Ceremony'
        FREE = 'free', 'Free'

    day = models.PositiveSmallIntegerField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    court = models.CharField(max_length=100, blank=True)
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    label = models.CharField(max_length=200)

    class Meta:
        ordering = ('day', 'start_time', 'court')

    def __str__(self):
        return f'Day {self.day} {self.start_time:%H:%M} - {self.label}'


class Match(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        FINISHED = 'finished', 'Finished'

    class ParticipantOutcome(models.TextChoices):
        WINNER = 'winner', 'Winner'
        LOSER = 'loser', 'Loser'

    day = models.PositiveSmallIntegerField()
    start_time = models.TimeField()
    court = models.CharField(max_length=100)
    schedule_event = models.OneToOneField(
        ScheduleEvent,
        on_delete=models.SET_NULL,
        related_name='match',
        null=True,
        blank=True,
    )
    match_code = models.CharField(max_length=20, blank=True)
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True)
    phase = models.CharField(max_length=50, blank=True)
    home_slot = models.CharField(max_length=20, blank=True)
    away_slot = models.CharField(max_length=20, blank=True)
    home_team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        related_name='home_matches',
        null=True,
        blank=True,
    )
    home_source_match = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        related_name='home_dependents',
        null=True,
        blank=True,
    )
    home_source_outcome = models.CharField(
        max_length=6,
        choices=ParticipantOutcome.choices,
        blank=True,
    )
    away_team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        related_name='away_matches',
        null=True,
        blank=True,
    )
    away_source_match = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        related_name='away_dependents',
        null=True,
        blank=True,
    )
    away_source_outcome = models.CharField(
        max_length=6,
        choices=ParticipantOutcome.choices,
        blank=True,
    )
    home_score = models.PositiveSmallIntegerField(null=True, blank=True)
    away_score = models.PositiveSmallIntegerField(null=True, blank=True)
    referee_slot = models.CharField(max_length=30, blank=True)
    referee_team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        related_name='refereed_matches',
        null=True,
        blank=True,
    )
    referee_locked = models.BooleanField(
        default=False,
        help_text='Preserve this referee team when automatic assignments are recalculated.',
    )
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.SCHEDULED)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['match_code'],
                condition=~models.Q(match_code=''),
                name='unique_nonempty_match_code',
            )
        ]

    def validate_result(
        self,
        *,
        status=None,
        home_score=None,
        away_score=None,
    ):
        status = self.status if status is None else status
        home_score = self.home_score if home_score is None else home_score
        away_score = self.away_score if away_score is None else away_score
        if (
            self.phase.startswith('upper_')
            and status == self.Status.FINISHED
            and home_score is not None
            and away_score is not None
            and home_score == away_score
        ):
            raise ValidationError('Upper knockout matches cannot finish in a draw.')

    def clean(self):
        super().clean()
        self.validate_result()
        errors = {}
        for side in ('home', 'away'):
            source_id = getattr(self, f'{side}_source_match_id')
            outcome = getattr(self, f'{side}_source_outcome')
            if bool(source_id) != bool(outcome):
                errors[f'{side}_source_outcome'] = (
                    'A source match and winner/loser outcome must be set together.'
                )
            elif self.pk and source_id == self.pk:
                errors[f'{side}_source_match'] = (
                    'A match cannot depend on its own result.'
                )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        home = self.home_team or self.home_slot or 'TBD'
        away = self.away_team or self.away_slot or 'TBD'
        return f'Day {self.day}: {home} vs {away}'
