# Implementation verification – 2026-11-07

## English interface and startup without .env

All maintained documentation and interface text is now in English, including setup, authentication errors, navigation, charts, history, session details, and browser test selectors. `.env.example` documents optional overrides only.

Verified `docker compose up -d --build --wait` with no project `.env`, dotenv loading explicitly disabled, and configuration overrides removed from the shell. Both services became healthy with their default loopback bindings. The end-to-end smoke test passed login, assets, SSH/password capture, import, restart persistence, and container hardening. Headless Edge passed English login/logout, charts, HTMX filters, inert hostile HTML, and mobile layout with no console errors.

The final Linux/Python 3.15.2 suite reported **41 passed, 1 skipped**: the isolated test image has no Docker CLI, so the Compose configuration test ran separately on the host. Windows reported **41 passed, 1 skipped** because its symlink test requires additional OS privileges; that test passed on Linux. Together these runs exercised all 42 tests. Python compilation also passed.

**Current update:** the runtime is now Python 3.15.2. Final verification: 40/40 tests on Linux, 39 passed/1 Windows symlink skip, a successful Compose smoke test, and an actual browser test. The full [security audit](audit/SECURITY-AUDIT-2026-11-07.md) also includes the [Astra review](audit/astra-review.md), fixes for its two findings, and remaining system risks. Below is the original record of the initial implementation on Python 3.13.

## Completed

- Linux AMD64 / Python 3.13: **27/27 tests passed** (project mounted read-only in a Docker container).
- Local Windows / Python 3.14.6: **26 tests passed**, with one symlink-creation test skipped because of OS permissions; it passed on Linux.
- Both AMD64 Docker images built from Python 3.13 / Debian trixie slim with exact dependency versions and SHA256 checksums.
- `docker compose config --quiet`, Python compileall, and dependency audit: no errors; the audit found no known vulnerabilities in the locked Python dependencies at the time of the check.
- End-to-end smoke test through an actual localhost port: temporary account creation, HTTP login, loading all frontend files, SSH password login, a simulated command, JSONL→SQLite import, and export including the password.
- Both services restarted: SQLite events and the web session preserved without duplicates.
- Container checks: UID 10001, zero effective capabilities, NoNewPrivs, read-only root filesystem, read-only event spool in the web container, no database or web source code in the sensor volume/root filesystem.
- An independent code review found three significant bugs. Regression tests first reproduced them and then passed after fixes: unlimited Ctrl-C output, a partial write corrupting the next event, and a race between password reset and session creation.

The temporary smoke-test account was removed. Local test events may remain in Docker volumes; they capture only synthetic local logins. The dashboard is ready for you to create your own account with the README's CLI command. Ports are bound only to 127.0.0.1.

## Not verified on this host

- Actual ARM64 execution: a local Buildx attempt failed with `exec format error` because QEMU/binfmt emulation was unavailable. No privileged host settings were changed. The repository includes an ARM64/AMD64 build workflow for CI that had not yet been run on GitHub at the time of this initial verification.
- Isolation from actual home-LAN/host services: this host uses Windows/Docker Desktop. A Linux firewall script and egress test are supplied, but their effectiveness must be verified on the target Linux host with genuinely reachable services before exposing the SSH port.
- Router forwarding, public internet deployment, and a physical Raspberry Pi were outside the scope of the local test.

These items are not considered completed production acceptance criteria solely on the basis of successful local tests.
