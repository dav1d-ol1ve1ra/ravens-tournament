from django import forms

from .models import Match


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
