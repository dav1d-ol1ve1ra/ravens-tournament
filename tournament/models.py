from django.db import models


class Team(models.Model):
    name = models.CharField(max_length=100)
    short_name = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, blank=True)
    logo = models.FileField(upload_to='team_logos/', blank=True)
    group_slot = models.CharField(max_length=2, blank=True)

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


class Match(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        FINISHED = 'finished', 'Finished'

    day = models.PositiveSmallIntegerField()
    start_time = models.TimeField()
    court = models.CharField(max_length=100)
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
    away_team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        related_name='away_matches',
        null=True,
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
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.SCHEDULED)

    def __str__(self):
        home = self.home_team or self.home_slot or 'TBD'
        away = self.away_team or self.away_slot or 'TBD'
        return f'Day {self.day}: {home} vs {away}'
