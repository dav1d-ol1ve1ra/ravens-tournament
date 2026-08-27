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

    def clean(self):
        cleaned_data = super().clean()
        home_score = cleaned_data.get('home_score')
        away_score = cleaned_data.get('away_score')
        if home_score is not None and away_score is not None:
            self.instance.validate_result(
                status=Match.Status.FINISHED,
                home_score=home_score,
                away_score=away_score,
            )
        return cleaned_data
