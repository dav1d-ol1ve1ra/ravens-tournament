# IV Ravens Tournament Web App

A Django website for the IV Ravens Tournament. It provides public schedule, standings, team information, and an Upper Bracket page, plus authenticated organiser result entry and group assignment. Production runs on PythonAnywhere with SQLite.

## Local development

Create and activate a virtual environment, then install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Apply migrations and, when setting up a development database, seed it:

```powershell
python manage.py migrate
python manage.py seed_tournament
```

Use this standard development workflow:

```powershell
python manage.py test
python manage.py check
python manage.py runserver
```

Create an organiser account when needed:

```powershell
python manage.py createsuperuser
```

`python manage.py seed_tournament --reset` is destructive and intended only for local development/testing. It must never be part of a normal production deployment.

## Safe production deployment

On PythonAnywhere, after the production environment variables have been configured in the private WSGI configuration:

```bash
cd ~/ravens-tournament
source .venv/bin/activate
git pull
python manage.py check
python manage.py migrate
python manage.py collectstatic --noinput
```

Then reload the PythonAnywhere web app from the **Web** tab. `migrate` is only relevant when migrations exist, but is safe to keep in the normal deployment sequence. Never run `seed_tournament --reset` during a normal deployment.

Production settings use `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, and `DJANGO_ALLOWED_HOSTS`. Keep real values out of Git. Map `/static/` to `staticfiles/` and `/media/` to the project `media/` directory in PythonAnywhere; uploaded team logos are media files and are not stored in Git.

## Database backup

Create a timestamped SQLite backup with:

```bash
python manage.py backup_database
```

Backups are written to `backups/`, which is ignored by Git. Back up before destructive operations, major tournament changes, and key tournament milestones. Never casually delete `db.sqlite3` in production. There is no automated restore command; database restoration should be handled deliberately outside normal tournament operation.

## Group assignment

1. Log in.
2. Open `/group-assignment/`.
3. Assign every team to `A1`–`A5` and `B1`–`B4`.
4. Select **Save Group Assignment**.

Saving resolves Group Stage match participants and referee assignments automatically. No management command is required. Group assignments lock as soon as any Group Stage result is finished.

## Result entry

1. Open `/results-admin/`.
2. Find the match.
3. Enter both non-negative scores.
4. Select **Save Result**.

Saving a valid result marks the match Finished, updates standings, resolves group ranking positions when possible, populates Lower League and Upper semifinal participants, and resolves Final/3rd Place participants after semifinals.

**No manual slot-resolution management command is required during normal tournament operation.**

## Manual tie-breaks

If **Manual tie-break required** appears:

1. Resolve the tie externally according to tournament rules.
2. Open `/manual-tiebreaks/` while logged in.
3. Enter every tied team once in the agreed final order.
4. Save the tie-break.
5. Verify the updated standings and progression.

Manual ordering is used only when a completed competition cannot be separated by the automatic criteria. Group ranking slots, Lower participants, and Upper semifinal participants update automatically after a Group Stage tie-break. A saved resolution is ignored if corrected results change or remove its exact tied-team set.

## Public pages

- `/` — tournament overview and next matches.
- `/schedule/` — public match and event schedule.
- `/standings/` — Group Stage and Lower League standings.
- `/upper/` — Upper Bracket matches and results.
- `/teams/` — team information and assigned group slots.

## Organiser pages

- `/results-admin/` — fast mobile result entry during the tournament.
- `/group-assignment/` — assign teams to Group A and Group B slots before results begin.
- `/manual-tiebreaks/` — record the final organiser-approved order for an unresolved tie.
- `/admin/` — Django administration for authorised organisers.

## Production safety

Do:

- Back up the database before destructive operations.
- Run tests and checks locally before deployment.
- Verify public pages after deployment.
- Use Result Entry for normal tournament results.

Do not:

- Delete `db.sqlite3`.
- Run `seed_tournament --reset` during normal deployment.
- Edit the database manually.
- Run legacy slot-resolution commands after every result.
- Make large code changes during the tournament.

## Tournament-day checklist

Before opening:

- Verify the site and organiser login load.
- Verify Schedule and Group Assignment.
- Create a database backup.

During the tournament:

- Enter results through Result Entry.
- Check standings periodically.
- Resolve any indicated manual ties through the Tie-breaks page.
- Do not use the terminal for normal progression.

Before Day 2:

- Verify Lower League participants.
- Verify UB-01 and UB-02 participants.
- Create a database backup.

After semifinals:

- Verify UB-03 and UB-04 participants.

After the tournament:

- Create a final database backup.

## Technical notes

Standings support arbitrary group sizes. Ranking slots use forms such as `1A` and `4B`; Upper matches can depend on winners or losers of earlier matches. The current schedule uses Group A (five teams), Group B (four teams), a Lower League, and an Upper Bracket.

`ScheduleEvent` stores the timetable, including ceremonies, breaks, and free/buffer periods. Matches retain their timing fields for compatibility and link to their schedule events.

## Reset tournament results

The preferred organiser workflow is the authenticated danger-zone page:

```text
/reset-results/
```

It requires typing `RESET`, creates a database backup, and returns to the page with confirmation. No terminal access is required.

As an emergency or terminal alternative, reset scores and derived progression state interactively with:

```bash
python manage.py reset_results
```

Type the exact confirmation `RESET` when prompted. For intentional non-interactive use:

```bash
python manage.py reset_results --yes
```

The web page and command use the same reset service. It creates a database backup first, clears Match scores and saved manual tie-break resolutions, returns Matches to Scheduled, restores direct Group Stage assignments, and clears derived Lower/Upper participants. It preserves teams, team metadata and logos, group assignments, Groups, Matches, ScheduleEvents, match slots/dependencies, and users.

This is different from `python manage.py seed_tournament --reset`, which rebuilds development tournament structure. Do not use either reset command casually in production.
