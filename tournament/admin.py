from django.contrib import admin

from .models import Group, Match, ScheduleEvent, Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'group_slot')
    list_editable = ('group_slot',)


admin.site.register(Group)


@admin.register(ScheduleEvent)
class ScheduleEventAdmin(admin.ModelAdmin):
    list_display = (
        'day',
        'start_time',
        'end_time',
        'court',
        'event_type',
        'label',
    )
    list_filter = ('day', 'event_type', 'court')
    ordering = ('day', 'start_time', 'court')


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = (
        'day',
        'start_time',
        'court',
        'phase',
        'match_code',
        'home_slot',
        'away_slot',
        'referee_slot',
        'home_team',
        'away_team',
        'referee_team',
        'referee_assignment_source',
        'referee_locked',
        'status',
    )
    list_editable = ('referee_team', 'referee_locked')
    list_filter = ('day', 'phase', 'status', 'referee_locked', 'court')
    ordering = ('day', 'start_time', 'court')

    @admin.display(description='Referee source')
    def referee_assignment_source(self, obj):
        if obj.referee_locked:
            return 'Manual'
        if obj.referee_slot:
            return 'Symbolic slot'
        if obj.referee_team_id:
            return 'Automatic'
        return 'Unassigned'
