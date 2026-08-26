# IV Ravens Tournament Web App

Public schedule, standings, team information and organiser result entry for the IV Ravens Tournament.

## Tech

- Python
- Django
- SQLite

## Local setup

Local development uses `DEBUG=True`, local hosts, and a development-only secret by default. No environment variables are required locally.

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

## Tournament format note

Group-stage standings support arbitrary group sizes and derive membership from each team's group slot, using configured `Group` records where available. The seeded tournament remains the current three-groups-of-three format. Day 2 ranking-slot progression is still intentionally specific to that format; knockout and bracket logic has not been generalised.

## Database backups

Create a timestamped SQLite backup before the tournament, and before any significant administrative change:

```bash
python manage.py backup_database
```

Backups are written to `backups/` and are not stored in Git.

To restore a backup, stop or reload the application as appropriate, make a backup of the current database first, replace `db.sqlite3` with the selected backup, then reload the application. Do not restore a database casually during the tournament; it replaces live result and organiser data.

## PythonAnywhere deployment

These steps are for production deployment. Keep production secrets out of Git and do not reuse the development fallback secret.

1. Create a PythonAnywhere account, open a Bash console, and clone the repository.

   ```bash
   git clone <repository-url>
   cd <project-directory>
   ```

2. Create and activate a virtual environment using the same Python version selected for the PythonAnywhere web app, then install the project requirements.

   ```bash
   python3.13 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   ```

3. Generate a private production secret, then export the production settings in the Bash console. Replace the placeholders with private values and the actual PythonAnywhere hostname.

   ```bash
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   export DJANGO_SECRET_KEY='<generated-private-secret>'
   export DJANGO_DEBUG='False'
   export DJANGO_ALLOWED_HOSTS='<account-hostname>.pythonanywhere.com'
   ```

   `.env.example` lists the required variable names, but the project deliberately does not auto-load `.env` files or add another dependency. `.env` is ignored by Git.

4. Prepare the SQLite database, initial tournament data, organiser account, and static files.

   ```bash
   python manage.py migrate
   python manage.py seed_tournament
   python manage.py createsuperuser
   python manage.py collectstatic --noinput
   ```

   Before the tournament, with the production environment variables configured, organisers should run:

   ```bash
   python manage.py backup_database
   ```

5. In PythonAnywhere's **Web** tab, create a web app using **Manual Configuration**, select the same Python version, and configure its virtual environment and working directory.

6. Edit the PythonAnywhere WSGI file linked from the Web tab. Add the directory containing `manage.py` to `sys.path`, set the three private environment values before Django loads, and use `config.settings`:

   ```python
   import os
   import sys

   project_path = '/home/<account-name>/<project-directory>'
   if project_path not in sys.path:
       sys.path.insert(0, project_path)

   os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
   os.environ['DJANGO_SECRET_KEY'] = '<generated-private-secret>'
   os.environ['DJANGO_DEBUG'] = 'False'
   os.environ['DJANGO_ALLOWED_HOSTS'] = '<account-hostname>.pythonanywhere.com'

   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```

   Store real values only in the private PythonAnywhere WSGI configuration, never in committed files. Enable **Force HTTPS** in the Web tab.

7. In the Web tab's **Static files** section, map:

   - URL: `/static/`
   - Directory: `/home/<account-name>/<project-directory>/staticfiles`

   Uploaded team logos use media files, not static files. Add this second mapping:

   - URL: `/media/`
   - Directory: `/home/<USERNAME>/ravens-tournament/media`

   Static assets are served from `/static/`; uploaded media is served from `/media/`. The `media` directory is ignored by Git and must be retained separately on PythonAnywhere.

8. Reload the web app from the Web tab. After future deployments, activate the virtual environment, export the production variables, apply migrations, rerun `collectstatic`, and reload.

PythonAnywhere references: [deploying an existing Django project](https://help.pythonanywhere.com/pages/DeployExistingDjangoProject/) and [configuring Django static files](https://help.pythonanywhere.com/pages/DjangoStaticFiles/).
