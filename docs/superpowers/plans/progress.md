# Progress — 2026-11-07-ssh-sentinel.md

Localization/startup follow-up: translated all maintained documentation and UI into English. Kept every Compose interpolation default; .env is optional. New integration coverage checks English auth/dashboard output and safe Compose configuration without dotenv or ambient overrides. Actual no-env Compose startup, full suites, browser checks, and restart/hardening smoke passed. Final Linux and Windows suites each report 41 passed/1 environment-dependent skip, jointly covering all 42 tests. Existing security behavior, password capture and localhost bindings are preserved.

Pre-flight: task 1 JSONL → task 2 importer; task 2 Database/summary → task 3 routes. Interfaces agree.

Ruling: implement natively in supplied empty workspace; no existing Git branch/worktree to isolate. This keeps the project at the requested location.

Ruling: explicit user amendment enables attacker password logging by default; admin password remains hashed.

Task 1: complete — 9 sensor/shell/spool tests passed on local Python 3.14.6. Real AsyncSSH integration included.

Task 2: complete — full suite 13 passed; partial writes, replay, malformed records, retention and aggregates covered.

Task 3: complete — 17 tests passed. Root cause of initial logout assertion: empty body had no Content-Type; empty forms now reach the CSRF guard and return 403.

Task 4 validation: AMD64 builds successful. Initial Linux/Python3.13 test run 18/18 passed. Dependency audit found no known vulnerabilities. Compose smoke passed login/assets/SSH password capture/import/restart persistence/non-root/read-only/capabilities checks.

Ruling: web uses an ordinary separate bridge because Docker internal networks suppressed published localhost ports in the observed runtime. Web remains localhost-bound; no sensor/web network is shared.

Ruling: initial SSH bind is localhost until firewall verification, then user changes SSH_BIND to 0.0.0.0. Cost: an extra deployment configuration step to protect initial setup.

Final review: three important findings, no material minors. All reproduced before fixes: unbounded SSH Ctrl-C output, a partial-write file poisoning subsequent events, and password reset racing session creation. All fixes pass locally.

Additional robustness: daily spool rotation bounds low-traffic retention granularity; scalar schema validation prevents poisoned import; nofollow/nonblock regular-file checks protect import; concurrent scrypt computations capped at two.

Ruling: ARM64 build hit exec format error because QEMU/binfmt is absent. Do not install privileged host emulation. Multiarch CI is provided; actual ARM64 execution remains unverified here.

Final review declined actual host firewall enforcement and ARM64 runtime; both are deployment-time checks, not asserted as verified. Plaintext attacker capture is user-approved.

Task 4: complete — final Linux/Python3.13 suite 27/27 green; Windows 26 passed/1 skipped; final AMD64 image builds, Compose end-to-end restart/hardening smoke and final dependency audit passed. `docs/verification.md` records precise evidence and deployment limitations. No Git repository existed, so no commits, merge, push or worktree cleanup was performed; all source files remain in the supplied project directory.
