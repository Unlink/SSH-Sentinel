# Runtime update and security audit implementation plan

> **For agentic workers:** Use superpowers:executing-plans, test-driven-development, systematic-debugging and verification-before-completion.

**Goal:** Update the project's Python/dependencies, prove compatibility and audit the whole solution.
**Architecture:** Preserve the existing two-service isolation and explicitly requested attacker-password capture. Change project runtime, not the host Windows Python installation.
**Tech Stack:** Latest verified stable CPython 3.15.2 Debian trixie slim; current PyPI/npm stable releases.
**Spec:** User request of 2026-11-07 and existing approved design; this maintenance request authorizes runtime updates and security fixes.

## Constraints / review focus

Preserve data and real admin accounts; no public port exposure, host firewall edits or privileged QEMU installation. Check protocol request floods, malformed spool records, CSRF/auth boundaries, image OS packages, browser dependencies and filesystem permissions. Plaintext attacker logging remains enabled.

### Task 1: Update runtime and dependencies

- [x] Establish existing suite baseline and query official PyPI/npm/Python/Docker sources.
- [x] Pin Python 3.15.2 multiarch digest, upgrade vendored HTMX/Chart.js with integrity/license provenance, re-resolve hashed locks on target Linux/Python.
- [x] Build both images; run full tests and pip check on target runtime, JavaScript browser checks and Compose smoke preserving existing accounts/data.

### Task 2: Full security audit and fixes

- [x] Independently review all code, templates, Docker, firewall, backup and CI boundaries.
- [x] Run dependency/OS/static scanners, inspect effective container configuration and reproduce actionable findings with failing regression tests.
- [x] Fix confirmed issues and rerun all tests, scans and final smoke.
- [x] Save audit findings, residual risks, precise versions/evidence and unperformed deployment checks; update current documentation/CI.

## Progress

Baseline Windows/Python3.14.6: 26 passed, 1 symlink test skipped for OS permissions. PyPI direct pins already latest stable. Official registry: HTMX2.0.11, Chart.js4.6.1. Official Python3.15.2 release and Docker AMD64/ARM64 index verified. Independent read-only reviewer dispatched.

Final: both project containers run Python3.15.2 and are healthy, localhost-bound. Runtime/dev locks regenerated under Linux3.15.2; current pip26.3, frontend assets and CI pins updated. Host Windows Python intentionally unchanged.

First independent review findings closed: discarded/capped SSH env metadata, bounded database event/storage capacity, bounded spool enumeration/error isolation. Additional real-browser login failure reproduced: no-referrer yielded Origin:null; same-origin referrer policy preserves Origin/CSRF protection and fixes login.

Explicit user steering: pip is not facing the internet; classify residual vendored setuptools findings as build/admin risk, not demonstrated remote app vulnerabilities. Capture attacker passwords remains enabled.

User additionally requested Astra. A fresh gpt-6-astra/high reviewer audited the updated source and confirmed two further availability bugs with bounded localhost experiments: compression expansion and global-reply output accumulation. Compression is now disabled; new bounded SSHServerConnection fails closed on write backpressure and caps total raw connection bytes. Negotiation, callback/input, and actual non-reading peer regressions are green. Actual peer test was also verified failing with the original no-op callback. No second independent Astra re-review was dispatched.

Final evidence: Linux/Python3.15.2 40/40 passed, pip check clean, runtime/bootstrap and dev pip-audit zero known findings, npm advisory zero. Windows final39passed/1OSsymlinkskip. One elevated Windows rerun hit pytest temp-directory ACL errors before test setup; rerun non-elevated with workspace basetemp passed. Both updated image builds and Compose login/SSH/import/restart/hardening smoke passed. Rebuilt running sensor independently negotiated no compression and returned a virtual whoami.

Headless Edge: HTMX2.0.11/Chart.js4.6.1 loaded, chart rendered, login/filter/logout/mobile and inert XSS checked, no console errors. Artifacts in docs/audit.

Trivy final both images: remaining OS47high/74medium/62low (83unique advisories; no available Debian fix reported) plus pip vendored setuptools1high/1medium/1low. No Critical. Bandit and config/secret findings manually triaged without suppression. Native Linux firewall and ARM64 runtime remain unverified deployment checks, explicitly recorded. Existing DB backed up privately in dashboard volume before new quotas; no real account overwritten.

All results, precise image identities and tool outputs: `docs/audit/SECURITY-AUDIT-2026-11-07.md` and `docs/audit/astra-review.md`.

