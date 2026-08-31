from django import forms

from .models import Match, Team


GROUP_ASSIGNMENT_SLOTS = (
    ('Group A', ('A1', 'A2', 'A3', 'A4', 'A5')),
    ('Group B', ('B1', 'B2', 'B3', 'B4')),
)
ALL_GROUP_ASSIGNMENT_SLOTS = tuple(
    slot for _, slots in GROUP_ASSIGNMENT_SLOTS for slot in slots
)


class GroupAssignmentForm(forms.Form):
    def __init__(self, *args, locked=False, **kwargs):
        super().__init__(*args, **kwargs)
        teams = Team.objects.order_by('name', 'pk')
        assigned_teams = {
            team.group_slot: team
            for team in teams
            if team.group_slot in ALL_GROUP_ASSIGNMENT_SLOTS
        }
        for slot in ALL_GROUP_ASSIGNMENT_SLOTS:
            self.fields[slot] = forms.ModelChoiceField(
                queryset=teams,
                label=slot,
                empty_label='Select a team',
                initial=assigned_teams.get(slot),
                disabled=locked,
                widget=forms.Select(attrs={'class': 'group-assignment-select'}),
            )

    def clean(self):
        cleaned_data = super().clean()
        if Team.objects.count() != len(ALL_GROUP_ASSIGNMENT_SLOTS):
            raise forms.ValidationError(
                'Exactly nine teams must be available before assignments can be saved.'
            )

        selected_teams = [
            cleaned_data.get(slot) for slot in ALL_GROUP_ASSIGNMENT_SLOTS
        ]
        if any(team is None for team in selected_teams):
            raise forms.ValidationError('All nine group slots must be assigned.')
        if len({team.pk for team in selected_teams}) != len(selected_teams):
            raise forms.ValidationError('Each team may be assigned to only one slot.')
        return cleaned_data

    def assignments(self):
        return {
            slot: self.cleaned_data[slot] for slot in ALL_GROUP_ASSIGNMENT_SLOTS
        }


class MatchResultForm(forms.ModelForm):
    class Meta:
        model = Match
        fields = ('home_score', 'away_score')
        widgets = {
            'home_score': forms.NumberInput(
                attrs={'min': 0, 'inputmode': 'numeric', 'aria-label': 'Home score'}
            ),
            'away_score': forms.NumberInput(
                attrs={'min': 0, 'inputmode': 'numeric', 'aria-label': 'Away score'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['home_score'].required = True
        self.fields['away_score'].required = True

    def clean(self):
        cleaned_data = super().clean()
        if self.instance.home_team_id is None or self.instance.away_team_id is None:
            raise forms.ValidationError('Participants not determined yet.')
        home_score = cleaned_data.get('home_score')
        away_score = cleaned_data.get('away_score')
        if home_score is not None and away_score is not None:
            self.instance.validate_result(
                status=Match.Status.FINISHED,
                home_score=home_score,
                away_score=away_score,
            )
        return cleaned_data
