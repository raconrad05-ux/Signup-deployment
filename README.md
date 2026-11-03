# signup

The office-hours sign-up sheet from *Building Software Systems with AI*, as it is at the end of chapter 11, *Adding Accounts and a Database*: accounts, the sheet, a SQLite database, and the Google Cloud setup script `gcp_setup.sh`. This is the starting point for chapter 12, *Deployment*.

To start chapter 12 from here: click *Use this template* on GitHub, name your repository `signup`, clone it into your home folder, then in `~/signup`:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app app run
```
