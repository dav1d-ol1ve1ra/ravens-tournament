import re

from django.db import migrations, models
import django.db.models.deletion


OUTCOME_SLOT_PATTERN = re.compile(r'^(?P<outcome>[WL])-(?P<match_code>.+)$')


def populate_participant_dependencies(apps, schema_editor):
    Match = apps.get_model('tournament', 'Match')
    matches_by_code = {
        match.match_code: match
        for match in Match.objects.exclude(match_code='')
    }
    for match in Match.objects.all():
        updates = {}
        for side in ('home', 'away'):
            reference = OUTCOME_SLOT_PATTERN.fullmatch(
                getattr(match, f'{side}_slot')
            )
            if reference is None:
                continue
            source = matches_by_code.get(reference.group('match_code'))
            if source is None:
                continue
            updates[f'{side}_source_match_id'] = source.id
            updates[f'{side}_source_outcome'] = (
                'winner' if reference.group('outcome') == 'W' else 'loser'
            )
        if updates:
            Match.objects.filter(pk=match.pk).update(**updates)


def clear_participant_dependencies(apps, schema_editor):
    Match = apps.get_model('tournament', 'Match')
    Match.objects.update(
        home_source_match=None,
        home_source_outcome='',
        away_source_match=None,
        away_source_outcome='',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('tournament', '0008_match_referee_locked'),
    ]

    operations = [
        migrations.AddField(
            model_name='match',
            name='away_source_match',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='away_dependents',
                to='tournament.match',
            ),
        ),
        migrations.AddField(
            model_name='match',
            name='away_source_outcome',
            field=models.CharField(
                blank=True,
                choices=[('winner', 'Winner'), ('loser', 'Loser')],
                max_length=6,
            ),
        ),
        migrations.AddField(
            model_name='match',
            name='home_source_match',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='home_dependents',
                to='tournament.match',
            ),
        ),
        migrations.AddField(
            model_name='match',
            name='home_source_outcome',
            field=models.CharField(
                blank=True,
                choices=[('winner', 'Winner'), ('loser', 'Loser')],
                max_length=6,
            ),
        ),
        migrations.RunPython(
            populate_participant_dependencies,
            clear_participant_dependencies,
        ),
    ]
