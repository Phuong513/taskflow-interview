# TaskFlow

A task management REST API built with **FastAPI**, **SQLAlchemy**, and **SQLite**.
---

## Project Structure

```
taskflow/
├── app/
│   ├── config.py          # App configuration
│   ├── database.py        # SQLAlchemy engine & session
│   ├── main.py            # FastAPI app & router registration
│   ├── models.py          # ORM models (User, Task, Comment)
│   ├── schemas.py         # Pydantic request/response schemas
│   ├── routers/
│   │   ├── auth.py        # Registration, login, JWT
│   │   ├── tasks.py       # Task CRUD + comments
│   │   └── users.py       # User management
│   └── utils/
│       └── helpers.py     # Shared utility functions
├── tests/
│   ├── conftest.py        # Pytest fixtures
│   ├── test_auth.py
│   ├── test_tasks.py
│   └── test_users.py
├── scripts/
│   └── seed_data.py       # Seed DB with sample data
├── TASKS.md               # Candidate use cases
├── EVALUATOR_GUIDE.md     # Interviewer reference (do not share with candidates)
├── requirements.txt
├── .env.example
└── run.py
```

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy .env.example to .env and set a generated SECRET_KEY
# PowerShell: Copy-Item .env.example .env
# macOS/Linux: cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
# Paste the generated value after SECRET_KEY= in .env

# 3. Seed the development database (clears existing data)
python scripts/seed_data.py

# 4. Start the server
python run.py
```

- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- OpenAPI schema: http://localhost:8000/openapi.json

---

## Password Storage

New registrations, password changes, and seed accounts use salted bcrypt at cost
12 through Passlib. Reinstall `requirements.txt` after updating: bcrypt is pinned
to 4.0.1 for compatibility with the existing Passlib 1.7.4 dependency.

Existing MD5 accounts upgrade to bcrypt after their next successful login.
Failed logins do not migrate credentials. No reseed is needed; accounts that
never log in retain their old hash until a password change or login.

Passwords over 72 UTF-8 bytes or containing a NUL use Passlib's
[bcrypt/SHA-256 variant](https://passlib.readthedocs.io/en/stable/lib/passlib.hash.bcrypt_sha256.html)
so every character contributes to verification. Registration and password changes
accept at most 4096 characters, matching Passlib's input limit. Stored bcrypt
hashes reject overlong inputs rather than silently accepting a truncated match.
Legacy passwords longer than 4096 characters require an administrator-assisted
password reset; they cannot migrate through login under this input policy.
Passwords and hashes are excluded from user-facing responses.

## Configuration and Permissions

Run commands from the repository root. Pydantic Settings loads `.env`; environment
variables take precedence. `SECRET_KEY` and `DATABASE_URL` are required, with no
built-in secret or database fallback. Use a randomly generated key of at least
32 characters. Missing or invalid settings stop startup with the affected field
names, without displaying credential values. Optional defaults are listed in
`.env.example`; `.env` is excluded from Git. SQLite is configured for development;
other SQLAlchemy databases require their corresponding driver to be installed.
The debug flag uses `TASKFLOW_DEBUG` to avoid collisions with other programs'
generic `DEBUG` environment variable.

Members may update or delete their own tasks and profiles. Administrators may
act on any task or profile; authorization uses the current database role, and
`X-Admin-Override` grants no privileges. Task reading and comments remain shared
team features. User deletion retains tasks and comments with nullable owner and
author IDs; only administrators may modify unowned tasks.
Tokens bind to the user ID and a keyed credential version, so username reuse
cannot transfer access, and password changes revoke existing tokens. Tokens
issued by the original application are incompatible; sign in again after upgrade.

## Running Tests

From the repository root, after installing `requirements.txt`:

```bash
python -m pytest -v
```

Every test creates and drops its own in-memory SQLite tables. Both application
startup and API requests use that database; tests do not read or modify
`taskflow.db` or `test.db`, and no seed step or running server is required.
User and task fixtures create independent records, so individual tests can also
run on their own:

```bash
python -m pytest tests/test_tasks.py::test_update_task -v
```

Coverage includes registration, login, invalid tokens, required fields, task CRUD,
authentication, search, status filters, comments, task summaries, and user tasks.
It also covers ownership/admin permissions, deleted-owner records, dotenv and
environment configuration, startup failures, and credential redaction.

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Web framework | FastAPI 0.110 |
| ORM | SQLAlchemy 2.0 |
| Database | SQLite (dev) |
| Auth | python-jose (JWT) + passlib |
| Validation | Pydantic v2 |
| Testing | pytest + httpx TestClient |
