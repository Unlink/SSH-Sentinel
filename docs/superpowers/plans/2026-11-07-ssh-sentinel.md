# SSH Sentinel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver the approved honeypot and dashboard; capture attacker passwords by default as explicitly requested.
**Architecture:** Sensor writes bounded JSONL; dashboard imports it into its private SQLite. Two containers, no broker or external database.
**Tech Stack:** Python 3.13, AsyncSSH, FastAPI/Jinja2, SQLite, HTMX, Chart.js, Debian trixie slim.
**Spec:** `docs/superpowers/specs/2026-11-07-ssh-sentinel-design.md` (approved with password capture enabled).

Current localization and startup note: the interface and documentation are now in English. Compose can start without a `.env` file; `.env` is optional for configuration overrides. This plan preserves the original implementation history and runtime versions.

## Global Constraints

ARM64/AMD64, non-root read-only containers, dropped capabilities, no-new-privileges, 30-day retention, no real command execution, no forwarding/SFTP/SCP, localhost dashboard. Attacker passwords are captured; admin credentials are hashed.

## Review Focus

- Interrupted writes/rotation must preserve subsequent complete records (task 2).
- Replaced files/replay must not restore expired events (task 2).
- Multiple SSH channels/partial input must respect session limits (task 1).
- Hostile HTML and CSV formulas must remain inert (task 3).
- Expired cookies, revoked accounts and brute-force attempts must not grant access (task 3).

### Task 1: Sensor and shell

**Files:** `app/common/{config,schemas}.py`, `app/sensor/{events,authentication,fake_shell,server}.py`, `tests/test_{shell,events,sensor}.py`.
**Interfaces:** `Settings.from_env()`, `EventWriter.emit(kind, session_id, ip, **data)`, `FakeShell.execute(command) -> (output, exit)`, `start_sensor(settings)`.

- [x] Write failing tests for inert input, bounded events/retention, real SSH auth/password capture, early disconnect, forbidden channels and limits.
- [x] Run `.venv/Scripts/python -m pytest tests/test_shell.py tests/test_events.py tests/test_sensor.py -q`; observe RED.
- [x] Implement the interfaces, persist host key separately from events, enforce connection/session/input limits.
- [x] Repeat command; require GREEN.

### Task 2: Storage and analytics

**Files:** `app/web/{database,ingestion,analytics}.py`, `tests/test_ingestion.py`.
**Interfaces:** consume task 1 JSONL; `Database(path)`, `Importer(db, event_dir, retention_days).run() -> int`, `summary(db, days) -> dict`, `Database.events(...) -> list[dict]`.

- [x] Write failing tests asserting exactly one event after reimport/restart, partial-line recovery, malformed/oversized records, file replacement, retention and filtered aggregates.
- [x] Run `.venv/Scripts/python -m pytest tests/test_ingestion.py -q`; observe RED.
- [x] Implement validated bounded import with transactional positions, indexed SQLite and retention.
- [x] Repeat command and existing suite; require GREEN.

### Task 3: Dashboard and login

**Files:** `app/web/{main,routes,auth,cli}.py`, `app/web/templates/*`, `static/*`, `tests/test_web.py`.
**Interfaces:** consume task 2; `create_app(settings)`, `set_admin(db, username, password)`, CLI `python -m app.web.cli create-admin USERNAME`.

- [x] Write failing tests for setup/login, CSRF, cookie expiry/revocation, throttling, escaped inputs, CSV injection, protected APIs and filtered history.
- [x] Run `.venv/Scripts/python -m pytest tests/test_web.py -q`; observe RED.
- [x] Implement responsive HTML with HTMX refresh, local charts, session details, exports, secure sessions and CLI account creation.
- [x] Repeat command and full suite; require GREEN.

### Task 4: Delivery and documentation

**Files:** `docker/Dockerfile.{sensor,web}`, `docker-compose.yml`, `.env.example`, `requirements*.{in,lock}`, `.dockerignore`, `.gitignore`, `README.md`, `SECURITY.md`, `.github/workflows/ci.yml`.

- [x] Lock dependencies and vendor frontend assets/licenses.
- [x] Implement container hardening, volumes, healthchecks, limits and CI multiarch builds.
- [x] Document setup/account/firewall/router/updates/backup/restore/troubleshooting and sensitive password data (originally in Slovak; subsequently translated into English).
- [x] Run suite, compile, dependency audit and Compose validation; attempt builds and container smoke tests. Clearly distinguish unavailable host checks.
- [x] Fresh final code review, important regression fixes and green suite.

## Execution

Implement directly in this chat to match the request for speed and simplicity. Empty directory is not a Git checkout; use the provided workspace rather than creating another worktree. No routine approval gates between tasks. Keep progress in `docs/superpowers/plans/progress.md`.


