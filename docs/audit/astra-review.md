# Independent Astra audit – 2026-11-07

Model: **gpt-6-astra**, a separate agent with a clean context and read-only access. The audit was performed at the user's explicit request after the Python update and initial security fixes. The auditor did not modify project files. Two experiments ran only on loopback with temporary data; no actual OOM attack was performed.

## Astra findings

### A1 – High: SSH compression bypasses application limits

The original configuration allowed `zlib@openssh.com`. AsyncSSH decompressed packets before application limits and without bounding the decompressed output. Astra locally confirmed expansion of 8 168 bytes into 8 388 613 bytes through SSH IGNORE while the connection remained open.

**Implementer's fix during the audit:** `compression_algs=None` in `app/sensor/server.py`. The regression test `test_transport_compression_cannot_bypass_input_limits` first confirmed negotiated zlib compression; after the fix it requires `none` in both directions.

### A2 – Medium: a non-reading client accumulates global SSH replies

Session channel limits did not cover global requests. The default AsyncSSH `pause_writing()` does nothing. Astra locally confirmed 5 004 544 bytes of pending transport output after 200 000 keepalive requests from an authenticated client that stopped reading. No shell channel was required.

**Implementer's fix after the finding:** `BoundedSSHConnection` in `app/sensor/transport.py` sets a write-buffer high watermark of 64 KiB, closes the connection on backpressure, and caps total network input at 4 MiB, including pre-auth/global/IGNORE packets. The listener creates this version-pinned AsyncSSH class through an asyncio protocol factory; it does not change global library methods.

Regression tests cover the callback, total input, and an actual non-reading client making global keepalive requests. The last test failed when the original no-op callback was restored and passed with the fix. Kernel TCP buffers and one packet being processed add a small overhead above the watermark; this is not an absolute quota on total RAM.

## Conclusion and audit boundaries

Astra found no other confirmed vulnerability enabling command execution, forwarding, SQL injection, stored XSS, authentication/CSRF bypass, or sensor access to the web volume. It verified browser asset hash consistency. It reviewed the app, library SSH code, ingest/schema/DB, templates/JS/exports, containers, firewall, backups, scripts, CI, and available scan reports.

Astra's original disposition was to close both SSH availability findings with targeted protocol tests and new images. The implementer performed the fixes and checks described above; no second independent Astra reassessment followed. Exact final results are in the main [audit report](SECURITY-AUDIT-2026-11-07.md).

Remaining conditions: verification of the firewall on the target Linux host and ARM64 execution; application limits do not replace filesystem quotas; exposing the web service beyond loopback requires HTTPS and HTTP header/body timeouts at the administrative proxy; CPU/connection DoS against a public honeypot cannot be eliminated completely.

Pip is not an internet service and receives no client inputs. In accordance with the user's clarification, its vendored setuptools CVEs are assessed as build/admin risk, not a confirmed remote application exploit. Storing plaintext attacker passwords remains an explicitly authorized feature.
