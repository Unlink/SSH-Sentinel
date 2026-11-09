# Security model

SSH Sentinel deliberately accepts untrusted SSH connections. It is a honeypot, not an administrative shell. No input is executed as Python, a system command, or a path to a real file. Supported responses are static virtual data. SFTP, SCP, forwarding, X11, and agent forwarding are not supported.

## Isolation boundaries

- The sensor and web application run as separate unprivileged containers with UID/GID 10001, read-only root filesystems, no capabilities, no-new-privileges, and CPU/RAM/PID limits.
- Only the JSONL spool is shared: read/write for the sensor, read-only for the dashboard. The database/account are only in the web volume; the SSH host key is only in the sensor volume.
- JSONL is treated as untrusted data: schema validation and limits on lines, UTC timestamps, UUIDs, and IPs; symbolic links are not followed.
- The dashboard uses escaped templates, local scripts, CSP, CSRF protection, and opaque session tokens stored only as SHA256 hashes. The account password uses scrypt N=32768, r=8, p=1 and a random 128-bit salt. Resetting the account invalidates all sessions.
- The host firewall must block new sensor connections to the LAN, host, and internet. The Docker network alone does not do this. The [detailed guide](docs/firewall.md) covers rules, persistence before Docker starts, and required verification. Do not automatically install a firewall inside a container.

## Captured sensitive data

At the requester's explicit instruction, `LOG_PASSWORDS=true`. It stores SSH clients' passwords as plaintext in JSONL and SQLite. Authenticated operators can access them, including through JSON/CSV exports. Data also includes IPs, usernames, banners, and commands. Anonymize logs before publishing them; never send them anywhere automatically. Protect backups just as carefully as live volumes. A request to capture “everything” does not change size/retention limits: oversized input is truncated or the session is closed.

The dashboard is local-only by default. Prefer an administrative SSH tunnel for remote administration. For a LAN/HTTPS proxy, configure allowed hostnames and Secure cookies correctly. SameSite Strict cookies are sent only in same-site contexts; public HTTP access is unsuitable.

## Operational limitations

Lossless logging is not guaranteed with a full disk, overload, or a compromised sensor. A compromised sensor can forge/delete its own events. JSONL is not a cryptographically signed audit trail. A container does not replace a separate VM/host and network isolation. The host kernel and Docker daemon are outside the application's protection. Retention is not secure physical erasure. Do not expose the host's Docker socket.

SSH metadata requests have a separate limit of 128 per channel, and client environment variables are never retained. SQLite defaults to limits of 100,000 events, 64 MiB of conservatively accounted data, and a 256 MiB main file; WAL and backups are outside the last limit. Import processes at most 4096 directory entries and 8 MiB of content per pass, isolates individual unreadable files, and reports unhealthy status. Import stops below 64 MiB of free space.

SSH compression is disabled. The entire SSH transport, including global requests/pre-auth/IGNORE, has a 4 MiB input budget and is closed when write backpressure exceeds the 64 KiB high watermark. The input budget is enforced before packet decoding. An independent [Astra review](docs/audit/astra-review.md) found and locally confirmed two protocol availability bugs; targeted regression tests cover the subsequent fixes, including a client that does not read responses.

Python 3.15.2, current direct dependencies, and an updated Debian installation do not guarantee zero CVEs. Remaining Trivy findings are listed in the [audit](docs/audit/SECURITY-AUDIT-2026-11-07.md). Pip is a build/administration tool, not an internet service; findings in its vendored components are assessed according to that exposure. SSH client input is never passed to pip.

## Reporting vulnerabilities

Report issues privately to the administrator of the specific deployment. Include the version, configuration without secrets, and a minimal reproduction. Do not include real captured passwords or private SSH keys. This new project does not yet designate a public security email address.
