# Security model

SSH Sentinel deliberately accepts untrusted SSH connections. It is a honeypot, not an administrative shell. No input is executed as Python, a system command, or a path to a real file. Supported responses are static virtual data. SFTP, SCP, real TCP/Unix forwarding, X11, and agent forwarding are not supported. Direct TCP requests are captured by a local virtual handler only.

## Isolation boundaries

- The sensor and web application run as separate unprivileged containers with UID/GID 10001, read-only root filesystems, no capabilities, no-new-privileges, and CPU/RAM/PID limits.
- Only the JSONL spool is shared: read/write for the sensor, read-only for the dashboard. The database/account are only in the web volume; the SSH host key is only in the sensor volume.
- JSONL is treated as untrusted data: schema validation and limits on lines, UTC timestamps, UUIDs, and IPs; symbolic links are not followed.
- The dashboard uses escaped templates, local scripts, CSP, CSRF protection, and opaque session tokens stored only as SHA256 hashes. The account password uses scrypt N=32768, r=8, p=1 and a random 128-bit salt. Resetting the account invalidates all sessions.
- The host firewall must block new sensor connections to the LAN, host, and internet. The Docker network alone does not do this. The [native Linux guide](docs/firewall.md) covers host rules, boot ordering, and verification. The opt-in Windows profile uses the separate one-shot VM administration helper described below; no firewall is installed inside the running sensor or dashboard.

## Captured sensitive data

At the requester's explicit instruction, `LOG_PASSWORDS=true`. It stores SSH clients' passwords as plaintext in JSONL and SQLite. Authenticated operators can access them, including through JSON/CSV exports. Data also includes IPs, usernames, banners, and commands. Anonymize logs before publishing them; never send them anywhere automatically. Protect backups just as carefully as live volumes. A request to capture “everything” does not change size/retention limits: oversized input is truncated or the session is closed.

The dashboard is local-only by default. Prefer an administrative SSH tunnel for remote administration. For a LAN/HTTPS proxy, configure allowed hostnames and Secure cookies correctly. SameSite Strict cookies are sent only in same-site contexts; public HTTP access is unsuitable.

## Operational limitations

The opt-in [Windows public TCP 2222 profile](docs/windows-public.md) uses a temporary administrative helper with `NET_ADMIN` in the Docker Desktop VM to install rules only for the sensor subnet. The honeypot services remain unprivileged. Sensor `restart: "no"` requires rerunning the guarded helper after VM restarts; bypassing it can bypass prerequisite isolation. Windows inbound rules require administrator approval, and internet reachability needs an off-host test.

Lossless logging is not guaranteed with a full disk, overload, or a compromised sensor. A compromised sensor can forge/delete its own events. JSONL is not a cryptographically signed audit trail. A container does not replace a separate VM/host and network isolation. The host kernel and Docker daemon are outside the application's protection. Retention is not secure physical erasure. Do not expose the host's Docker socket.

SSH metadata requests have a separate limit of 128 per channel, and client environment variables are never retained. SQLite defaults to limits of 100,000 events, 64 MiB of conservatively accounted data, and a 256 MiB main file; WAL and backups are outside the last limit. Import processes at most 4096 directory entries and 8 MiB of content per pass, isolates individual unreadable files, and reports unhealthy status. Import stops below 64 MiB of free space.

SSH compression is disabled. The entire SSH transport, including global requests/pre-auth/IGNORE, has a 4 MiB input budget and is closed when write backpressure exceeds the 64 KiB high watermark. The input budget is enforced before packet decoding. An independent [Astra review](docs/audit/astra-review.md) found and locally confirmed two protocol availability bugs; targeted regression tests cover the subsequent fixes, including a client that does not read responses.

Python 3.15.2, current direct dependencies, and an updated Debian installation do not guarantee zero CVEs. Remaining Trivy findings are listed in the [audit](docs/audit/SECURITY-AUDIT-2026-11-07.md). Pip is a build/administration tool, not an internet service; findings in its vendored components are assessed according to that exposure. SSH client input is never passed to pip.

## Reporting vulnerabilities

Report issues privately to the administrator of the specific deployment. Include the version, configuration without secrets, and a minimal reproduction. Do not include real captured passwords or private SSH keys. This new project does not yet designate a public security email address.

The Windows source-IP proxy runs as a normal host user and adds mandatory PROXY v1 metadata to a localhost-only sensor backend. PROXY mode is opt-in and must never be publicly bound: local Windows processes and Docker administrators are trusted to access that backend. Public clients cannot choose the header generated by the proxy. Headers, concurrent connections and proxy lifetimes are bounded. Historical Docker gateway source IPs cannot be reconstructed.

## Virtual direct TCP forwarding

Direct-tcpip requests use a bounded local capture handler, never AsyncSSH's standard forwarding path. It performs no DNS resolution or outbound connect and sends no destination-service responses. Remote TCP listeners and Unix forwarding remain denied. Per transport: 2 concurrent virtual channels, 8 accepted lifetime channels and at most 32 admission requests including failures; exceeding a lifetime budget aborts the SSH connection. Each channel uses an 8 KiB receive window/4 KiB packet size, closes at 16 KiB input or 10 seconds, and persists at most the first 2 KiB (readable UTF-8 plus exact base64). A callback may include bytes beyond the input threshold up to the current receive window; no bytes beyond the preview cap are retained. The 4 MiB total SSH input budget, session deadline, storage quotas and VM firewall still apply. Client-claimed origin metadata is never used as the source IP. Payload previews are untrusted, escaped in HTML, and potentially sensitive; apply the same access and retention controls as passwords.
