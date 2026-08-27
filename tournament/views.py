from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import MatchResultForm
from .models import Match, Team
from .presentation import COUNTRY_FLAGS, participant_name, team_initials
from .services.knockout_slots import resolve_knockout_slots
from .services.progression_slots import resolve_progression_slots
from .services.standings import calculate_group_stage_standings


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


def schedule(request):
    phase_labels = {
        'group_stage': 'Group Stage',
        'final_1_3': '1st–3rd Place',
        'final_4_6': '4th–6th Place',
        'final_7_9': '7th–9th Place',
    }
    phase_labels.update(
        {
            'final_1_3': '1st\u20133rd Place',
            'final_4_6': '4th\u20136th Place',
            'final_7_9': '7th\u20139th Place',
            'upper_semifinal': 'Upper Semifinal',
            'upper_third_place': 'Upper Third Place',
            'upper_final': 'Upper Final',
            'lower_round_robin': 'Lower Round Robin',
        }
    )
    matches = Match.objects.select_related(
        'home_team', 'away_team', 'referee_team'
    ).order_by('day', 'start_time', 'court')

    days = []
    current_day = None
    for match in matches:
        match.phase_label = phase_labels.get(match.phase, match.phase)
        if match.day != current_day:
            current_day = match.day
            days.append({'number': current_day, 'matches': []})
        days[-1]['matches'].append(match)

    return render(request, 'tournament/schedule.html', {'days': days})


def standings(request):
    return render(
        request,
        'tournament/standings.html',
        {'standings_by_group': calculate_group_stage_standings()},
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
