from django.contrib import admin

from .models import Group, Match, Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'group_slot')
    list_editable = ('group_slot',)


admin.site.register(Group)


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = (
        'day',
        'start_time',
        'court',
        'phase',
        'home_slot',
        'away_slot',
        'referee_slot',
        'home_team',
        'away_team',
        'referee_team',
        'status',
    )
