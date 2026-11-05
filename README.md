# signup

The office-hours sign-up sheet from *Building Software Systems with AI*, as it is at the end of chapter 11, *Adding Accounts and a Database*: accounts, the sheet, a SQLite database, and the Google Cloud setup script `gcp_setup.sh`. This is the starting point for chapter 12, *Deployment*.

To start chapter 12 from here: click *Use this template* on GitHub, name your repository `signup`, clone it into your home folder, then in `~/signup`:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app app run
```

## Configuration

The app reads its settings from environment variables, loaded from a `.env` file locally (`.env` is gitignored, so never commit it):

```
DATABASE_URL=postgresql://...      # Neon Postgres connection string
TEST_DATABASE_URL=postgresql://... # database for smoke_test.py (optional; falls back to DATABASE_URL)
SECRET_KEY=...                     # random value used to sign session cookies
SITE_NAME=Office Hours             # shown in the page title and on the home page
ADMIN_USERNAME=...                 # the user who can see who booked each slot
```

Generate a secret key with `python3 -c "import secrets; print(secrets.token_hex(32))"`. The tables are created automatically on startup. `python smoke_test.py` runs the tests in a temporary schema in the `TEST_DATABASE_URL` database (or `DATABASE_URL` if that's not set) and drops it afterwards.
