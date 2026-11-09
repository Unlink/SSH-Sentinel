# SSH Sentinel – first-version design

The subsequent user-requested runtime update uses Python 3.15.2 and additional security limits; see `docs/audit/SECURITY-AUDIT-2026-11-07.md`. The text below preserves the original approved design.

Localization and startup update: the current interface and documentation are in English. Compose can start without a `.env` file; `.env` is optional for configuration overrides. Historical runtime and approval details below remain unchanged.

Requirements source: the user-supplied v1.2 implementation plan. This document adds straightforward implementation decisions without changing its scope.

## Goal and scope

A standalone SSH honeypot for Linux ARM64 and AMD64 with a complete dashboard, deployable through Docker Compose. It records accepted TCP connections, including disconnects before authentication, SSH banners, login attempts, and commands in a simulated shell. Incomplete SYN scans, GeoIP, alerts, additional protocols, and malware downloads remain out of scope.

## Selected approach and alternatives

The recommended approach comes directly from the supplied plan: one Python codebase, two processes in separate containers, JSONL for event handoff, and SQLite only in the dashboard. No broker or external database is required. A single shared process would weaken the required separation of the sensor from the database; additional services would increase resource requirements and implementation time. The task already specifies the technologies and architecture; this is not a new alternative confirmed by the user.

## Sensor and simulated shell

- Python 3.13 and AsyncSSH. A stable host key in a separate sensor volume.
- Each accepted connection receives an ID; events have separate UUIDs, UTC timestamps, types, session IDs, and bounded data fields.
- A connection record is created before authentication. The SSH handshake is recorded separately from the TCP connection itself. Unauthenticated connections are labeled separately in the dashboard; they are not proof of an attack scan.
- Author's proposal: accept a nonempty username and any password into the simulation. On 2026-11-07, the user explicitly requested storing attacker passwords too; storage is enabled by default with an option to disable it. The dashboard password is separate.
- Support interactive shell and SSH exec through the same static simulator. The commands ls, pwd, whoami, id, uname, cat, ps, and exit return only virtual data. Other inputs receive a simulated error.
- Never use a system shell, subprocess, eval, or access to real files based on client input. Disable SFTP, SCP, forwarding, tunnels, and unsupported subsystems.
- Configurable limits on connections, authentication, session duration, line length, command count, and output volume. Bound untrusted inputs before storage.

## Events and storage

- The sensor writes rotated JSONL files to a shared volume; the dashboard mounts it read-only. SQLite and login credentials are in a separate dashboard volume.
- The importer uses event UUIDs with a unique index and persistent file positions. It processes an incomplete final line only after completion; a malformed line must not stop import.
- Individual event size and total spool size will be bounded. Default retention for JSONL and SQLite is 30 days. The sensor deletes spool data; the dashboard handles database retention.
- A full disk or a reached limit must not cause unbounded memory growth; the error is reported in the operational log and health status. Documentation will describe possible event loss when storage is insufficient.

## Dashboard

- FastAPI, server-side HTML templates with automatic escaping, CSS, HTMX, and Chart.js served locally without a CDN.
- Summaries of connections, unauthenticated connections, attempts, unique IPs, and shell sessions; time series for 24 hours, 7 days, and 30 days; top IPs, usernames, and commands.
- Filtered and paginated history, session details, and authenticated JSON/CSV export. CSV export neutralizes spreadsheet formulas.
- Author's proposal: a single administrator account created or changed through the in-container CLI; no default password. The dashboard remains inaccessible until an account is created.
- Store the password only as a securely salted hash. Login has attempt limits and session expiration. HttpOnly/SameSite cookies, protection for state-changing forms, security headers, and no insertion of inputs into HTML or JavaScript without the appropriate encoding.

## Deployment and security

- Two Dockerfiles with Python 3.13 on Debian 13 slim, precisely locked dependencies, and Compose with ports 2222 and 127.0.0.1:8080.
- Unprivileged users, read-only root filesystems, cap_drop ALL, no-new-privileges, CPU/RAM/PID limits, separate volumes, tmpfs where needed, healthchecks, and automatic restart.
- No Docker socket, privileged mode, or sensor access to the database or dashboard account.
- Separate service networks. The host firewall enforces a ban on sensor-initiated connections to LAN/internal ranges while preserving replies to existing incoming connections. README will provide a concrete procedure and verification before opening the router port. A Docker bridge alone does not guarantee isolation.
- README and SECURITY will cover installation, the account, ports, firewall, updates, backup/restore, retention, limits, and troubleshooting.

## Implementation and verification

A short implementation plan will divide the work into events/configuration, sensor/shell, importer/database, dashboard, and Docker/documentation. Tests will focus on risky behavior: actual SSH handshake and authentication, disconnects, channel prohibitions, non-execution of commands, limits, idempotency and retention, login, escaping, and exports.

Run available local tests, builds, and Compose checks as the environment permits; inspect dependencies for known vulnerabilities. Mark ARM64/AMD64 builds and actual network isolation as verified only after performing the relevant test. Locally, Python 3.14.6 and the Docker CLI are currently available; Docker daemon availability has not yet been verified. The target runtime remains Python 3.13.

## Approval

The user approved the design on 2026-11-07 with attacker password storage enabled by default. Product code and dependencies had not yet been created. Approval is followed by a detailed work plan and implementation without further routine approval steps.
