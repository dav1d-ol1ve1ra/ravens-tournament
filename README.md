# IV Ravens Tournament Web App

Public schedule, standings, team information and organiser result entry for the IV Ravens Tournament.

## Tech

- Python
- Django
- SQLite

## Local setup

1. Create and activate a virtual environment.

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install the dependencies.

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Apply database migrations and seed the tournament.

   ```powershell
   python manage.py migrate
   python manage.py seed_tournament
   ```

4. Create an organiser account and start the development server.

   ```powershell
   python manage.py createsuperuser
   python manage.py runserver
   ```

## Useful URLs

- `/`
- `/schedule/`
- `/standings/`
- `/teams/`
- `/results-admin/`
- `/admin/`

## Useful management commands

- `python manage.py seed_tournament`
- `python manage.py resolve_slots`
- `python manage.py resolve_day2_slots`

The resolution commands are development and admin utilities. Normal tournament result entry automatically performs the required Day 2 slot resolution after a valid result is saved.
