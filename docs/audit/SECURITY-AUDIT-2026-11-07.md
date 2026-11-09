# SSH Sentinel runtime update and security audit

Date: **7 November 2026**. Scope: project runtime and dependencies, application code, actual SSH protocol boundaries, web/auth/CSRF/XSS/SQL/exports, database/spool/retention/quotas, containers, firewall and backup procedures, CI, and sensitive data. The audit included a separate read-only reviewer followed by an explicitly requested independent **gpt-6-astra** review. It was neither a penetration test of a third-party network nor a certification.

## Result

The updated project runs on Linux AMD64 with Python 3.15.2. **40/40 automated tests passed**, `pip check` found no inconsistent dependencies, and the end-to-end Compose smoke test passed, including restart and persistence. A real headless Edge browser verified login/logout, chart rendering, HTMX filtering, inert display of hostile HTML, and mobile width without console errors.

This audit fixed five availability/resource findings from two independent reviews and a browser login bug. **Astra found two of these security bugs.** Remaining risks include system CVEs in the Debian base, build-only vendored findings in pip, and unverified conditions of the target deployment. The result is therefore neither “zero CVEs” nor approval for immediate internet deployment without isolation.

Localization and startup update: the current interface and documentation are in English. Compose can start without a `.env` file; `.env` is optional for configuration overrides. This note does not change the historical audit evidence below.

## Verified updates

| Component | Before | After |
|---|---|---|
| Project Python | 3.13, floating Docker tag | **3.15.2**, official multiarch digest `sha256:e97b88e416c3c01eb427b21fd8cd3ebf006e6ee38afcfcc3cae1c54ee2ab0a75` |
| Pip in the runtime image | 26.2.2 from the base image | **26.3**, pinned SHA256 wheel/sdist hashes |
| HTMX | 2.0.8 | **2.0.11** |
| Chart.js | 4.5.1 | **4.6.1** |
| Debian packages | Base image state | Available updates from official repositories during the build |
| GitHub Actions | Major tags of older releases | Verified latest stable releases pinned to commit SHAs |

Direct Python dependencies were already current: AsyncSSH 2.24.1, FastAPI 0.162.2, Uvicorn 0.54.0, and Jinja2 3.1.6. pytest 9.2.0, pytest-asyncio 1.4.1.post1, httpx2 2.16.0, and pip-audit 2.10.1 also remained current. Runtime/dev locks were resolved again on Linux/Python 3.15.2 with hashes for every package. The host Windows Python installation was unchanged.

Browser assets were obtained from pinned npm archives, verifying SHA512 integrity and SHA256 hashes of the resulting files. The npm advisory check for HTMX 2.0.11, Chart.js 4.6.1, and the actually bundled `@kurkle/color` 0.3.2 returned an empty list of findings.

Python source verification: [official 3.15.2 release](https://www.python.org/downloads/release/python-3152/) and [Docker Official Image](https://hub.docker.com/_/python). CI versions and SHAs are in `ci-actions.json`; browser asset provenance is in `static/vendor/manifest.json`.

## Fixed security findings

| ID | Severity / prerequisite | Finding and fix | Evidence |
|---|---|---|---|
| S1 | High, public SSH client | AsyncSSH retained unlimited client `env` values outside the shell input budget. HoneypotChannel now rejects env without retaining it and counts all session metadata requests before processing; exceeding 128 requests disconnects the transport. | Actual env requests before and after shell startup; flood test. |
| S2 | Medium, sustained public load | SQLite had only time-based retention and could fill the disk. Added limits of 100 000 events, 64 MiB of conservatively accounted data, a 256 MiB main SQLite file, and a 64 MiB low-space guard; the oldest data is removed. Exporting in batches of 100 rows avoids a long-lived WAL snapshot. | Tests for event/payload quotas, SQLite FULL, preserving the newest events, and releasing WAL during export. |
| S3 | Medium, compromised sensor/spool | Unbounded filename sorting and a single file error could stop the importer. A 4096-entry limit, bounded enumeration, and streaming checkpoints were added; individual OSError failures are isolated and reported as a health error. | Tests for exceeding the file count, recovery, and an unreadable file preceding valid records. |
| A1 | High, SSH client; **Astra** | Compression expanded packets before application limits. SSH compression is disabled through `compression_algs=None`. | Astra: 8 168 B → 8 388 613 B without closure before the fix; the regression handshake after the fix negotiates only `none`. |
| A2 | Medium with OOM potential, non-reading SSH client; **Astra** | Global request replies bypassed the shell cap, and AsyncSSH ignored write backpressure. The new transport aborts the connection at a 64 KiB high watermark and limits all received transport bytes to 4 MiB, including pre-auth/IGNORE. | Astra: 5 004 544 B of pending output from 200 000 requests. A regression test with an actual non-reading client failed with the original no-op callback and passed after the fix. |

Previous fixes for Ctrl-C output, partial-write spool handling, and concurrent password reset remained covered by regression tests. Database file permissions are 0600, and data directory permissions are 0700.

Functional browser bug: `Referrer-Policy: no-referrer` caused Chromium forms to send `Origin: null`, which the security check correctly rejected. The policy is now `same-origin`; Origin and CSRF checks remain enabled. The real-browser test passed after the fix.

## Tool results and triage

### Python and JavaScript

- Pip-audit of the runtime, including bootstrap pip: **0 known findings** in the checked distributions.
- Pip-audit of the complete dev/test lock: **0 known findings**.
- `pip check`: no broken requirements.
- Npm bulk advisory API for the three browser packages above: **0 reports**.
- Archive SHA512 hashes and local JS file SHA256 hashes verified; libraries executed in a real browser.

### Trivy 0.76.2 – images

Both images have the same system base and dependency tree. Counts are **findings per CVE/package combination**, not the number of independent remote attacks:

| Layer, each image | Critical | High | Medium | Low | Unique advisories |
|---|---:|---:|---:|---:|---:|
| Debian OS packages | 0 | 47 | 74 | 62 | 83 |
| Vendored setuptools metadata/code in pip | 0 | 1 | 1 | 1 | 3 |

All available apt updates were applied. Zlib findings with an available Debian fix disappeared; upgrading pip removed reports for old msgpack/urllib3 versions. At scan time, Trivy reported no available fixed Debian version for the remaining OS items listed above. Their reachability from SSH/web inputs was neither generally proved nor disproved; they cannot all be ignored solely because the application does not use a shell. No Critical finding was identified.

Pip 26.3 still contains vendored `pkg_resources` from setuptools 70.3.0; the scanner reports CVE-2025-47273, CVE-2026-59890, and GHSA-xmj3-9gf7-h52w. Top-level setuptools is not installed in the runtime. Following the user's explicit clarification and the actual system boundary, these findings are classified as **build/admin risk**: pip is not a network service and does not receive attacker inputs. The findings were neither suppressed from raw reports nor labeled as a confirmed remote application exploit.

### Bandit 1.9.4

The raw report preserves heuristic findings without `nosec` suppression. Manual review identified no confirmed High vulnerability:

- B104: binding to `0.0.0.0` inside a container is intentional; host publishing is loopback, and the sensor should be exposed only after the firewall test.
- B608: constructed SQL uses only fixed names/columns and fixed aggregation expressions; all filter values are bound parameters. The SQL injection test passed.
- B404/B603/B607: the Docker subprocess in the local smoke helper uses an argument list without a shell; it is not an attacker-input handler.
- B101/B106: test assertions and a synthetic honeypot password in the smoke helper, not production authentication or a secret.
- B310: the updater uses the fixed official npm registry and verifies the integrity of downloaded archives; this is a build-time trust boundary, not an endpoint exposed to SSH clients. A compromised registry/publisher remains a supply-chain risk.

The Trivy misconfiguration/secret scan found no secrets. Two Low “No HEALTHCHECK defined” findings refer to the Dockerfiles themselves; in the supported Compose deployment, both services have defined healthchecks that actually passed.

## Operational boundaries and remaining risks

1. **The target firewall still requires live verification.** Windows/Docker Desktop did not establish the effectiveness of Linux DOCKER-USER/INPUT rules, blocking of LAN/host/internet access, or persistence after restart. Before public exposure, perform the README egress test against services confirmed to be listening. Both ports remain on 127.0.0.1.
2. **ARM64 execution is unverified.** An official multiarch manifest and CI build configuration exist. QEMU/binfmt is unavailable locally; privileged host configuration was unchanged. The GitHub workflow was not run in this new local project.
3. **Application limits are not filesystem quotas.** WAL, backups, spool metadata, Docker logs, and a potentially compromised sensor require monitoring/a dedicated disk or volume quotas. Migrating an older large SQLite database does not shrink the physical file immediately. Default quotas can remove older events before the TTL is reached.
4. **A public honeypot can lose availability.** CPU, connections, the kernel, and the Docker daemon are beyond the complete protection of application limits. Deploy on a separate VM/host/VLAN; home LAN services must not be reachable from the sensor.
5. **Web access beyond loopback:** requires HTTPS/an admin network, correct Host/Origin, and frontend header/body limits. Uvicorn keepalive is not a slow-request deadline. The default mode is loopback/an administrative SSH tunnel.
6. **Plaintext attacker passwords are authorized.** They remain in spool/SQLite/exports/backups; protect access and retention. Sensor events are not a cryptographically verified forensic audit trail.

## Evidence and reproducibility

- `python-dependencies.json`, `development-dependencies.json`, `browser-dependencies.json`.
- `sensor-image.json`, `web-image.json` contain exact image identities and complete CVEs; `sensor-image-initial.json` preserves the initial scan before apt/pip fixes.
- `bandit.json`, `config-secrets.json`, `scan-summary.json` preserve unabridged findings/the overview.
- `browser-check.json`, `dashboard-desktop.png`, `history-mobile.png` capture an isolated browser test with synthetic data.
- The [separate Astra report](astra-review.md) distinguishes the model's findings from the implementer's subsequent fixes; no second independent Astra re-audit was performed after the final fixes.

Before deploying the new version, a consistent private backup was saved in the web volume at `/data/pre-python315-audit.sqlite`. The existing account was not overwritten; the smoke helper created and then removed only its own temporary account. Exact user passwords and production events were not sent to auditing services. Trivy scanned locally exported images without a Docker socket, and tools retrieved only public advisory databases/metadata.

