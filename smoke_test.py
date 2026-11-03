import os
import sys
import tempfile
from pathlib import Path

os.chdir(Path(__file__).resolve().parent)
sys.path.insert(0, os.getcwd())

import app as appmod

# Use a throwaway DB so the smoke test doesn't touch signup.db.
tmp = Path(tempfile.mkdtemp()) / "test.db"
appmod.DATABASE = tmp
appmod.init_db()
appmod.app.config["TESTING"] = True
c = appmod.app.test_client()

def body(r):
    return r.get_data(as_text=True)

r = c.get("/")
assert r.status_code == 200 and "not logged in" in body(r), body(r)

r = c.post("/register", data={"username": "alice", "password": "pw"}, follow_redirects=True)
assert "Account created" in body(r), body(r)

r = c.post("/register", data={"username": "alice", "password": "pw"})
assert "already taken" in body(r), body(r)

r = c.post("/register", data={"username": "", "password": "pw"})
assert "Username is required" in body(r), body(r)

r = c.post("/login", data={"username": "alice", "password": "wrong"})
assert "Incorrect" in body(r), body(r)

r = c.post("/login", data={"username": "alice", "password": "pw"}, follow_redirects=True)
assert "logged in as <strong>alice</strong>" in body(r), body(r)

r = c.post("/logout", follow_redirects=True)
assert "logged out" in body(r) and "not logged in" in body(r), body(r)

r = c.post("/logout", follow_redirects=True)
assert "Please log in first" in body(r), body(r)

# Password must be hashed, not stored in plain text.
import sqlite3
row = sqlite3.connect(tmp).execute("SELECT password_hash FROM users").fetchone()
assert row[0] != "pw" and row[0].startswith(("scrypt:", "pbkdf2:")), row

# --- Sign-up sheet ---------------------------------------------------------

def login(username):
    c.post("/logout")
    r = c.post("/login", data={"username": username, "password": "pw"}, follow_redirects=True)
    assert f"Welcome, {username}" in body(r), body(r)

# The sheet needs a login.
r = c.get("/sheet", follow_redirects=True)
assert "Please log in first" in body(r), body(r)

c.post("/register", data={"username": "bob", "password": "pw"})

# alice registered first, so she is the administrator.
login("alice")
r = c.get("/sheet")
assert r.status_code == 200 and "You are the administrator" in body(r), body(r)
assert body(r).count("<th>") == 1 + 5 + 4, body(r)        # corner, 5 days, 4 time rows
assert body(r).count(">Book</button>") == 20, body(r)      # all 20 slots free
assert "2:00 pm" in body(r) and "4:00 pm" in body(r), body(r)

# bob is not the administrator; he books a slot.
login("bob")
r = c.get("/sheet")
assert "You are the administrator" not in body(r), body(r)
r = c.post("/book", data={"weekday": "2", "start": "14:30"}, follow_redirects=True)
assert "Booked Wednesday at 2:30 pm" in body(r), body(r)
assert "Yours" in body(r) and ">Cancel</button>" in body(r), body(r)
assert body(r).count(">Book</button>") == 19, body(r)

# Booking the same slot twice (or an invalid slot) fails.
r = c.post("/book", data={"weekday": "2", "start": "14:30"}, follow_redirects=True)
assert "already been taken" in body(r), body(r)
r = c.post("/book", data={"weekday": "5", "start": "14:30"}, follow_redirects=True)
assert "not a valid slot" in body(r), body(r)
r = c.post("/book", data={"weekday": "0", "start": "16:00"}, follow_redirects=True)
assert "not a valid slot" in body(r), body(r)

# A third user sees the slot as taken, without the name, and cannot book or cancel it.
c.post("/register", data={"username": "carol", "password": "pw"})
login("carol")
r = c.get("/sheet")
assert ">Taken</span>" in body(r) and "bob" not in body(r).split("<table")[1], body(r)
r = c.post("/book", data={"weekday": "2", "start": "14:30"}, follow_redirects=True)
assert "already been taken" in body(r), body(r)
r = c.post("/cancel", data={"weekday": "2", "start": "14:30"}, follow_redirects=True)
assert "no booking in that slot" in body(r) and ">Taken</span>" in body(r), body(r)

# The administrator sees who booked it.
login("alice")
r = c.get("/sheet")
assert "Taken by <strong>bob</strong>" in body(r), body(r)

# bob cancels his own booking and the slot is free again.
login("bob")
r = c.post("/cancel", data={"weekday": "2", "start": "14:30"}, follow_redirects=True)
assert "Cancelled Wednesday at 2:30 pm" in body(r), body(r)
assert body(r).count(">Book</button>") == 20, body(r)

print("ALL SMOKE TESTS PASSED")
