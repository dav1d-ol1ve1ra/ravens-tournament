from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import GROUP_ASSIGNMENT_SLOTS, GroupAssignmentForm, MatchResultForm
from .models import Match, ScheduleEvent, Team
from .presentation import COUNTRY_FLAGS, participant_name, team_initials
from .services.knockout_slots import resolve_knockout_slots
from .services.lower_standings import calculate_lower_standings
from .services.progression_slots import resolve_progression_slots
from .services.standings import calculate_group_stage_standings
from .slot_resolution import resolve_group_stage_slots


SCHEDULE_PHASE_LABELS = {
    'group_stage': 'Group Stage',
    'final_1_3': '1st–3rd Place',
    'final_4_6': '4th–6th Place',
    'final_7_9': '7th–9th Place',
    'upper_semifinal': 'Upper Semifinal',
    'upper_third_place': '3rd Place Match',
    'upper_final': 'Final',
    'lower_league': 'Lower League',
    'lower_round_robin': 'Lower Round Robin',
}

UPPER_MATCH_SECTIONS = (
    ('Semifinals', ('UB-01', 'UB-02')),
    ('3rd Place', ('UB-03',)),
    ('Final', ('UB-04',)),
)

def home(request):
    next_matches = list(
        Match.objects.filter(status=Match.Status.SCHEDULED)
        .select_related('home_team', 'away_team')
        .order_by('day', 'start_time', 'court')[:4]
    )
    for match in next_matches:
        match.home_participant = participant_name(match, 'home')
        match.away_participant = participant_name(match, 'away')

    return render(request, 'tournament/home.html', {'next_matches': next_matches})


def teams(request):
    teams = list(Team.objects.order_by('name'))
    for team in teams:
        team.country_flag = COUNTRY_FLAGS.get(team.country, '🏳️')
        team.initials = team_initials(team)

    return render(request, 'tournament/teams.html', {'teams': teams})


SCHEDULE_PHASE_FILTERS = {
    'group_stage': ('group_stage',),
    'lower_league': ('lower_league', 'lower_round_robin'),
    'upper': ('upper_semifinal', 'upper_third_place', 'upper_final'),
}


def _schedule_url(view, day, phase, group, status):
    query = {}
    if view:
        query['view'] = view
    if day:
        query['day'] = day
    if phase:
        query['phase'] = phase
    if group:
        query['group'] = group
    if status:
        query['status'] = status
    return f'{reverse("schedule")}?{urlencode(query)}'


def _linked_match(event):
    try:
        return event.match
    except Match.DoesNotExist:
        return None


def _schedule_days(events, courts):
    days_by_number = {}
    for event in events:
        match = _linked_match(event)
        event.linked_match = match
        event.is_match = event.event_type == ScheduleEvent.EventType.MATCH
        event.kind_label = event.get_event_type_display()
        if match:
            match.phase_label = SCHEDULE_PHASE_LABELS.get(match.phase, match.phase)
            event.home_participant = participant_name(match, 'home')
            event.away_participant = participant_name(match, 'away')
            event.referee_participant = participant_name(match, 'referee')
        days_by_number.setdefault(event.day, []).append(event)

    days = []
    for day, day_events in days_by_number.items():
        grouped_events = {}
        for event in day_events:
            if event.is_match:
                continue
            key = (
                event.start_time,
                event.end_time,
                event.event_type,
                event.label,
            )
            grouped_events.setdefault(key, []).append(event)

        all_court_event_ids = {
            event.id
            for grouped in grouped_events.values()
            if len(grouped) == len(courts)
            and {event.court for event in grouped} == set(courts)
            for event in grouped
        }
        displayed_event_ids = set()
        displayed_events = []
        for event in day_events:
            if event.id in displayed_event_ids:
                continue
            if event.id in all_court_event_ids:
                key = (
                    event.start_time,
                    event.end_time,
                    event.event_type,
                    event.label,
                )
                event.is_all_court_event = True
                event.court_label = 'All Courts'
                displayed_event_ids.update(
                    grouped_event.id for grouped_event in grouped_events[key]
                )
            else:
                event.is_all_court_event = False
                event.court_label = event.court
                displayed_event_ids.add(event.id)
            displayed_events.append(event)
        days.append(
            {
                'number': day,
                'label': {1: 'Saturday', 2: 'Sunday'}.get(day, f'Day {day}'),
                'events': displayed_events,
            }
        )

    return days


def _court_days(events, courts):
    rows_by_day = {}
    for event in events:
        rows = rows_by_day.setdefault(event.day, {})
        row = rows.setdefault(
            (event.start_time, event.end_time),
            {
                'start_time': event.start_time,
                'end_time': event.end_time,
                'events_by_court': {},
            },
        )
        row['events_by_court'][event.court] = event

    for rows in rows_by_day.values():
        for row in rows.values():
            row_events = list(row['events_by_court'].values())
            if (
                len(row_events) == len(courts)
                and row_events
                and all(
                    event.event_type != ScheduleEvent.EventType.MATCH
                    for event in row_events
                )
                and len(
                    {
                        (event.event_type, event.label)
                        for event in row_events
                    }
                )
                == 1
            ):
                row['all_court_event'] = row_events[0]
            else:
                row['all_court_event'] = None

    return [
        {
            'number': day,
            'label': {1: 'Saturday', 2: 'Sunday'}.get(day, f'Day {day}'),
            'rows': [
                {
                    'start_time': row['start_time'],
                    'end_time': row['end_time'],
                    'all_court_event': row['all_court_event'],
                    'cells': [row['events_by_court'].get(court) for court in courts],
                }
                for _, row in sorted(rows.items())
            ],
        }
        for day, rows in rows_by_day.items()
    ]


def schedule(request):
    selected_view = request.GET.get('view', 'list')
    if selected_view not in {'list', 'courts'}:
        selected_view = 'list'

    selected_day = request.GET.get('day', '')
    if selected_day not in {'1', '2'}:
        selected_day = ''

    selected_phase = request.GET.get('phase', '')
    if selected_phase not in SCHEDULE_PHASE_FILTERS:
        selected_phase = ''

    selected_group = request.GET.get('group', '')
    if selected_group not in {'A', 'B'}:
        selected_group = ''

    selected_status = request.GET.get('status', '')
    if selected_status not in {Match.Status.SCHEDULED, Match.Status.FINISHED}:
        selected_status = ''

    events = ScheduleEvent.objects.select_related(
        'match',
        'match__home_team',
        'match__away_team',
        'match__referee_team',
    ).order_by('day', 'start_time', 'court')
    if selected_day:
        events = events.filter(day=selected_day)
    if selected_phase:
        events = events.filter(
            ~Q(event_type=ScheduleEvent.EventType.MATCH)
            | Q(match__phase__in=SCHEDULE_PHASE_FILTERS[selected_phase])
        )
    if selected_group:
        events = events.filter(
            ~Q(event_type=ScheduleEvent.EventType.MATCH)
            | Q(match__group__code=selected_group)
        )
    if selected_status:
        events = events.filter(
            ~Q(event_type=ScheduleEvent.EventType.MATCH)
            | Q(match__status=selected_status)
        )
    events = list(events)

    courts_queryset = ScheduleEvent.objects.exclude(court='')
    if selected_day:
        courts_queryset = courts_queryset.filter(day=selected_day)
    courts = list(
        courts_queryset.order_by('court').values_list('court', flat=True).distinct()
    )

    day_filters = [
        (
            label,
            value,
            _schedule_url(
                selected_view, value, selected_phase, selected_group, selected_status
            ),
        )
        for label, value in (('All', ''), ('Saturday', '1'), ('Sunday', '2'))
    ]
    phase_filters = [
        (
            label,
            value,
            _schedule_url(
                selected_view, selected_day, value, '', selected_status
            ),
        )
        for label, value in (
            ('All', ''),
            ('Group Stage', 'group_stage'),
            ('Lower League', 'lower_league'),
            ('Upper Bracket', 'upper'),
        )
    ]
    group_filters = [
        (
            label,
            value,
            _schedule_url(
                selected_view,
                selected_day,
                'group_stage',
                value,
                selected_status,
            ),
        )
        for label, value in (('All Groups', ''), ('Group A', 'A'), ('Group B', 'B'))
    ]
    status_filters = [
        (
            label,
            value,
            _schedule_url(
                selected_view, selected_day, selected_phase, selected_group, value
            ),
        )
        for label, value in (
            ('All', ''),
            ('Scheduled', Match.Status.SCHEDULED),
            ('Finished', Match.Status.FINISHED),
        )
    ]
    days = _schedule_days(events, courts)
    court_days = _court_days(events, courts)

    return render(
        request,
        'tournament/schedule.html',
        {
            'selected_view': selected_view,
            'selected_day': selected_day,
            'selected_status': selected_status,
            'list_view_url': _schedule_url(
                'list', selected_day, selected_phase, selected_group, selected_status
            ),
            'courts_view_url': _schedule_url(
                'courts', selected_day, selected_phase, selected_group, selected_status
            ),
            'day_filters': day_filters,
            'phase_filters': phase_filters,
            'group_filters': group_filters,
            'status_filters': status_filters,
            'selected_phase': selected_phase,
            'selected_group': selected_group,
            'days': days,
            'courts': courts,
            'court_days': court_days,
        },
    )


def standings(request):
    calculated_groups = calculate_group_stage_standings()

    return render(
        request,
        'tournament/standings.html',
        {
            'standings_by_group': {
                'A': calculated_groups.get('A', []),
                'B': calculated_groups.get('B', []),
            },
            'lower_standings': calculate_lower_standings(),
        },
    )


def upper(request):
    matches_by_code = {
        match.match_code: match
        for match in Match.objects.filter(
            match_code__in=('UB-01', 'UB-02', 'UB-03', 'UB-04')
        ).select_related(
            'schedule_event',
            'home_team',
            'away_team',
            'referee_team',
        )
    }
    sections = []
    for title, match_codes in UPPER_MATCH_SECTIONS:
        matches = []
        for match_code in match_codes:
            match = matches_by_code.get(match_code)
            if match is None:
                continue
            schedule_event = match.schedule_event
            match.phase_label = SCHEDULE_PHASE_LABELS.get(match.phase, match.phase)
            match.home_participant = participant_name(match, 'home')
            match.away_participant = participant_name(match, 'away')
            match.referee_participant = participant_name(match, 'referee')
            match.display_day = schedule_event.day if schedule_event else match.day
            match.display_time = (
                schedule_event.start_time if schedule_event else match.start_time
            )
            match.display_court = schedule_event.court if schedule_event else match.court
            matches.append(match)
        sections.append({'title': title, 'matches': matches, 'is_final': title == 'Final'})

    return render(request, 'tournament/upper.html', {'upper_sections': sections})


@login_required
def group_assignment(request):
    assignments_locked = Match.objects.filter(
        phase='group_stage',
        status=Match.Status.FINISHED,
    ).exists()

    if request.method == 'POST' and assignments_locked:
        messages.error(
            request,
            'Group assignments are locked because Group Stage results already exist.',
        )
        return redirect('group_assignment')

    form = GroupAssignmentForm(
        request.POST if request.method == 'POST' else None,
        locked=assignments_locked,
    )
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            Team.objects.exclude(group_slot='').update(group_slot='')
            assigned_teams = []
            for slot, team in form.assignments().items():
                team.group_slot = slot
                assigned_teams.append(team)
            Team.objects.bulk_update(assigned_teams, ['group_slot'])
            fields_updated, matches_updated = resolve_group_stage_slots()

        messages.success(
            request,
            'Group assignment saved successfully. '
            f'Resolved {fields_updated} match field(s) across '
            f'{matches_updated} match(es).',
        )
        return redirect('group_assignment')

    form_groups = [
        {
            'name': group_name,
            'fields': [form[slot] for slot in slots],
        }
        for group_name, slots in GROUP_ASSIGNMENT_SLOTS
    ]
    return render(
        request,
        'tournament/group_assignment.html',
        {
            'form': form,
            'form_groups': form_groups,
            'assignments_locked': assignments_locked,
        },
    )


def _result_filters(source):
    day = source.get('day', '')
    status = source.get('status', '')
    return (
        day if day in {'1', '2'} else '',
        status if status in {Match.Status.SCHEDULED, Match.Status.FINISHED} else '',
    )


@login_required
def results_admin(request):
    selected_day, selected_status = _result_filters(
        request.POST if request.method == 'POST' else request.GET
    )
    submitted_match = None
    submitted_form = None

    if request.method == 'POST':
        submitted_match = get_object_or_404(Match, pk=request.POST.get('match_id'))
        submitted_form = MatchResultForm(request.POST, instance=submitted_match)
        if submitted_form.is_valid():
            with transaction.atomic():
                match = submitted_form.save(commit=False)
                match.status = Match.Status.FINISHED
                match.save(update_fields=['home_score', 'away_score', 'status'])
                if match.phase == 'group_stage':
                    resolve_progression_slots()
                elif match.phase.startswith('upper_'):
                    resolve_knockout_slots()

            messages.success(request, 'Result saved successfully.')
            query = {
                key: value
                for key, value in (
                    ('day', selected_day),
                    ('status', selected_status),
                )
                if value
            }
            redirect_url = reverse('results_admin')
            if query:
                redirect_url = f'{redirect_url}?{urlencode(query)}'
            return redirect(redirect_url)

        messages.error(request, 'Please correct the score values and try again.')

    matches = Match.objects.select_related(
        'home_team', 'away_team', 'referee_team'
    ).order_by('day', 'start_time', 'court')
    if selected_day:
        matches = matches.filter(day=selected_day)
    if selected_status:
        matches = matches.filter(status=selected_status)

    matches = list(matches)
    for match in matches:
        if submitted_match and match.pk == submitted_match.pk:
            match.result_form = submitted_form
        else:
            match.result_form = MatchResultForm(instance=match)

    return render(
        request,
        'tournament/results_admin.html',
        {
            'matches': matches,
            'selected_day': selected_day,
            'selected_status': selected_status,
        },
    )
