import os
from functools import wraps

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

# Settings come from environment variables; locally they are read from .env.
load_dotenv()


def require_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Environment variable {name} is not set (see .env).")
    return value


DATABASE_URL = require_env("DATABASE_URL")
SITE_NAME = os.environ.get("SITE_NAME", "Office Hours").strip()
ADMIN_USERNAME = require_env("ADMIN_USERNAME")

app = Flask(__name__)
app.config["SECRET_KEY"] = require_env("SECRET_KEY")
# Cloud Run sets K_SERVICE and serves over HTTPS, so only send the session
# cookie over HTTPS there; on a laptop the app runs over plain http://.
app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("K_SERVICE"))


@app.context_processor
def inject_site_name():
    return {"site_name": SITE_NAME}


# --- Database helpers -------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with psycopg.connect(DATABASE_URL) as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                weekday INTEGER NOT NULL,
                start TEXT NOT NULL,
                user_id INTEGER NOT NULL REFERENCES users(id),
                UNIQUE (weekday, start)
            )
            """
        )


# --- Sign-up sheet ----------------------------------------------------------

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
# Half-hour slots from 2:00 pm to 4:00 pm, stored as 24-hour "HH:MM" strings.
SLOT_TIMES = ["14:00", "14:30", "15:00", "15:30"]


def format_time(hhmm):
    hour, minute = (int(p) for p in hhmm.split(":"))
    suffix = "pm" if hour >= 12 else "am"
    return f"{(hour - 1) % 12 + 1}:{minute:02d} {suffix}"


app.jinja_env.filters["ampm"] = format_time


def slot_end(hhmm):
    hour, minute = (int(p) for p in hhmm.split(":"))
    minute += 30
    if minute >= 60:
        hour, minute = hour + 1, minute - 60
    return f"{hour:02d}:{minute:02d}"


def parse_slot(form):
    """Return (weekday, start) from a form, or None if it isn't a real slot."""
    try:
        weekday = int(form.get("weekday", ""))
    except ValueError:
        return None
    start = form.get("start", "")
    if not (0 <= weekday < len(DAYS)) or start not in SLOT_TIMES:
        return None
    return weekday, start


def is_admin(user):
    """The administrator is the user named by ADMIN_USERNAME."""
    return user is not None and user["username"] == ADMIN_USERNAME


# --- Auth helpers -----------------------------------------------------------

@app.before_request
def load_current_user():
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        g.user = get_db().execute(
            "SELECT id, username FROM users WHERE id = %s", (user_id,)
        ).fetchone()
        if g.user is None:
            session.clear()
    g.is_admin = is_admin(g.user)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please log in first.")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


# --- Routes -----------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username:
            flash("Username is required.")
        elif not password:
            flash("Password is required.")
        else:
            db = get_db()
            try:
                db.execute(
                    "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                    (username, generate_password_hash(password)),
                )
                db.commit()
            except psycopg.errors.UniqueViolation:
                flash(f"Username '{username}' is already taken.")
            else:
                flash("Account created. You can log in now.")
                return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = get_db().execute(
            "SELECT * FROM users WHERE username = %s", (username,)
        ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Incorrect username or password.")
        else:
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Welcome, {user['username']}!")
            return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("index"))


@app.route("/sheet")
@login_required
def sheet():
    rows = get_db().execute(
        """
        SELECT b.weekday, b.start, b.user_id, u.username
        FROM bookings b JOIN users u ON u.id = b.user_id
        """
    ).fetchall()
    bookings = {(r["weekday"], r["start"]): r for r in rows}

    # One cell per (time, day); each cell says whether it is free, yours, or taken.
    grid = []
    for start in SLOT_TIMES:
        cells = []
        for weekday in range(len(DAYS)):
            booking = bookings.get((weekday, start))
            if booking is None:
                status = "free"
            elif booking["user_id"] == g.user["id"]:
                status = "mine"
            else:
                status = "taken"
            cells.append(
                {
                    "weekday": weekday,
                    "start": start,
                    "status": status,
                    "username": booking["username"] if booking else None,
                }
            )
        grid.append({"start": start, "end": slot_end(start), "cells": cells})

    return render_template("sheet.html", days=DAYS, grid=grid)


@app.route("/book", methods=["POST"])
@login_required
def book():
    slot = parse_slot(request.form)
    if slot is None:
        flash("That is not a valid slot.")
        return redirect(url_for("sheet"))
    weekday, start = slot

    db = get_db()
    try:
        db.execute(
            "INSERT INTO bookings (weekday, start, user_id) VALUES (%s, %s, %s)",
            (weekday, start, g.user["id"]),
        )
        db.commit()
    except psycopg.errors.UniqueViolation:
        flash("Sorry, that slot has already been taken.")
    else:
        flash(f"Booked {DAYS[weekday]} at {format_time(start)}.")
    return redirect(url_for("sheet"))


@app.route("/cancel", methods=["POST"])
@login_required
def cancel():
    slot = parse_slot(request.form)
    if slot is None:
        flash("That is not a valid slot.")
        return redirect(url_for("sheet"))
    weekday, start = slot

    db = get_db()
    # Only the person who booked a slot may cancel it.
    deleted = db.execute(
        "DELETE FROM bookings WHERE weekday = %s AND start = %s AND user_id = %s",
        (weekday, start, g.user["id"]),
    ).rowcount
    db.commit()
    if deleted:
        flash(f"Cancelled {DAYS[weekday]} at {format_time(start)}.")
    else:
        flash("You have no booking in that slot.")
    return redirect(url_for("sheet"))


init_db()

if __name__ == "__main__":
    app.run(debug=True)
