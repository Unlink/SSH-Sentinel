# SSH Sentinel

A simple SSH honeypot with its own dashboard. Two containers, local JSONL events, and SQLite. No external database or cloud services. Python 3.15.2 on Debian 13 slim; images target Linux AMD64 and ARM64. The multiarch base image is also pinned by its SHA256 digest.

The sensor records accepted TCP connections, SSH handshakes/banners, password authentication, commands, and session duration. It deliberately accepts any nonempty username and password into a **simulated** shell. It never executes commands or downloads files. It cannot see incomplete SYN scans; a disconnected connection is not automatically evidence of an attack.

**As explicitly requested, connecting clients' passwords are stored in plaintext**, displayed to authenticated operators, and included in exports. The administrator password is stored only as a salted scrypt hash. To disable password capture, set `LOG_PASSWORDS=false`; this does not remove existing records.

## Requirements

- Linux AMD64 or ARM64, for example a Raspberry Pi running 64-bit Raspberry Pi OS/Debian.
- Docker Engine with Compose v2. Start with 1 GB RAM and 1 GB free disk space; configured container memory limits are 192 + 256 MB.
- Root access to configure the target host's firewall. An isolated VM/VLAN or dedicated host is appropriate for an internet-facing honeypot.

If Docker is not installed, follow the official instructions for [Debian](https://docs.docker.com/engine/install/debian/) or [Ubuntu](https://docs.docker.com/engine/install/ubuntu/). For Raspberry Pi, use an ARM64 OS and the instructions for its base distribution. Check `docker version` and `docker compose version`. Membership in the `docker` group effectively grants root privileges.

## Quick start

From the project root, with no `.env` file required:

```bash
docker compose up -d --build
docker compose exec web python -m app.web.cli create-admin admin
```

Compose supplies all defaults automatically. You can add `--wait` to the first command to wait for healthy services. `.env.example` is an optional reference for configuration overrides; copying it is not a startup prerequisite.

Enter your own password with at least 12 characters. Open the [dashboard](http://127.0.0.1:8080). Before an account is created, only the setup page is shown; there are no default credentials. The same CLI command changes the account/password and invalidates all logins. An operator session lasts eight hours. Five failed attempts from one IP trigger a five-minute block.

On a remote server, use the existing **administrative SSH server** on a different port from the honeypot:

```bash
ssh -L 8080:127.0.0.1:8080 operator@server
```

The initial configuration binds **both ports to localhost only**. Test the honeypot:

```bash
ssh -p 2222 root@127.0.0.1
# Any password; then: whoami, uname -a, cat /etc/passwd, exit
```

If the client only tries keys, add `-o PreferredAuthentications=password -o PubkeyAuthentication=no`. Events appear in the dashboard within approximately five seconds. Statistics and charts refresh every ten seconds. Times are in UTC. The 24-hour range includes the current hour and 23 preceding hourly buckets; 7/30-day ranges use calendar days, including today.

## Public TCP 2222 on Windows

For an explicit public TCP 2222 deployment on Windows/Docker Desktop, follow [the Windows guide](docs/windows-public.md). Its guarded startup helper applies sensor-specific VM firewall rules and starts a native Windows Python proxy on `0.0.0.0:2222` to preserve real client IPs. The Docker backend binds only to `127.0.0.1:2223`, and the dashboard stays private. This profile needs a Windows Python environment and must be started again after Docker Desktop restarts. A separate administrator command enables the named Windows inbound rule. This profile also needs no `.env` file.

## Dashboard

- Counts of TCP connections, password attempts, unique IPs, and simulated shells.
- Separate count of connections closed without login; time ranges of 24 hours, 7 days, and 30 days.
- Top IPs, usernames, and commands; paginated session history with one row per SSH connection, outcome and activity counts. IP, username and event-type filters select whole sessions, even when matching values occur in different events.
- Open a session for its chronological events, including captured passwords, commands, limits, and disconnection. Counts cover retained events; a missing disconnect is shown explicitly. Raw event APIs and JSON/CSV exports remain available.
- JSON/CSV exports respect the selected filters, require authentication, and stream data. CSV neutralizes inputs that could be interpreted as formulas.
- All frontend libraries are local in `static/vendor`, with no CDN, third-party fonts, or telemetry.

## Configuration

No configuration file is required. Override defaults with shell environment variables (the examples below use Bash), an optional `.env` file based on `.env.example`, or an optional Compose override file. Recreate the affected containers to apply changes, for example:

```bash
LOG_PASSWORDS=false docker compose up -d --force-recreate sensor
```

A command-scoped shell override applies only to that invocation. Supply it again on future recreations or updates, export it in the shell used for Compose, or persist the setting in an optional `.env`/Compose override. An override file must configure the corresponding published port or container environment setting; `.env` uses the variable names below.

| Variable | Default | Meaning |
|---|---|---|
| `SSH_BIND` | `127.0.0.1` | Change to `0.0.0.0` for a public sensor only after verifying isolation |
| `SSH_PORT` | `2222` | Host honeypot port; must not conflict with server administration |
| `WEB_BIND` | `127.0.0.1` | Dashboard stays local |
| `WEB_PORT` | `8080` | Host HTTP port |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed HTTP hostnames/IPs without ports |
| `COOKIE_SECURE` | `false` | Set to `true` only when accessing through HTTPS |
| `LOG_PASSWORDS` | `true` | Capture SSH clients' passwords |
| `RETENTION_DAYS` | `30` | Retention for imported events and JSONL |
| `MAX_CONNECTIONS` | `64` | Maximum number of concurrently accepted SSH connections |
| `SESSION_SECONDS` | `300` | Absolute TCP/SSH session duration, including authentication |
| `MAX_COMMANDS` | `200` | Commands per connection |
| `SPOOL_BYTES` | `268435456` | Maximum JSONL spool size, 256 MiB by default |
| `MAX_DB_EVENTS` | `100000` | Maximum SQLite event count; older events are removed even before retention expires |
| `MAX_EVENT_STORAGE_BYTES` | `67108864` | Maximum sum of JSON data plus a conservative 1024-byte allowance per event |
| `MAX_DB_BYTES` | `268435456` | Safety limit for the main SQLite file; must be at least twice the event budget |
| `MAX_SPOOL_FILES` | `4096` | Maximum entries when scanning the spool directory; exceeding this pauses import |
| `SENSOR_SUBNET` | `172.30.222.0/24` | Dedicated IPv4 sensor network; must match the firewall |
| `WEB_SUBNET` | `172.30.223.0/24` | Separate dashboard bridge network |

Additional limits: 20 seconds for authentication, at most five rejected authentication attempts, one SSH session channel over the entire connection, 4096 characters per line, total input of 1 MiB and output of 64 KiB per session, 64 KiB per event, and file rotation at approximately 4 MiB or on a UTC date change. Longer fields are truncated. Public keys are rejected, but attempts/fingerprints are recorded. SCP, SFTP, and agent/X11/TCP/Unix forwarding are prohibited. Unknown commands return a simulated error. Operational Docker logs are limited to 2 × 5 MB per container.

The sensor does not accept client environment variables and allows at most 128 metadata requests per session channel. These requests bypass the regular SSH data window, so they have a separate limit. Exceeding it closes the connection.

SSH compression is completely disabled to prevent packet decompression from bypassing memory limits. The entire transport has a 4 MiB received-network-data limit, including the handshake, global requests, and IGNORE packets. A client that stops reading and fills the output transport buffer above its 64 KiB high watermark is disconnected. Kernel TCP buffers and one current packet add overhead; this watermark is not an absolute limit on all memory used by a connection.

For a LAN dashboard, set a specific address in `WEB_BIND` and `ALLOWED_HOSTS`. Authentication remains mandatory. Use a trusted management network or an HTTPS reverse proxy with `COOKIE_SECURE=true`. `X-Forwarded-*` headers are not trusted by default. The proxy must preserve Host/Origin; configure and test TLS termination and request schemes for your network. Configure HTTP header and request-body receive timeouts on the frontend; Uvicorn's keepalive timeout alone does not limit slow, incomplete requests. The default deployment is intended for loopback access/an administrative SSH tunnel.

## Required isolation before exposing the sensor

**Detailed instructions for the target Linux host:** [Step-by-step firewall setup](docs/firewall.md). Includes persistent rules loaded before Docker, host/LAN/internet tests, post-reboot checks, an iptables alternative, and safe rollback.

A Docker bridge **does not guarantee that LAN or host access is blocked**. The supplied script blocks new outbound IPv4 sensor connections to all destinations while allowing replies on existing inbound connections. Both forwarding rules and host INPUT rules are required. IPv6 is disabled in the Compose networks; sensor DNS points to an unused loopback address because the application does not need it.

On the **Linux Docker host**, while `SSH_BIND` is still local, run:

```bash
sudo sh scripts/firewall.sh 172.30.222.0/24
sudo iptables -nvL DOCKER-USER
sudo iptables -nvL SSENTINEL_FWD
sudo iptables -nvL SSENTINEL_HOST
```

If you change `SENSOR_SUBNET`, pass the same subnet to the script and remove old rules using your firewall manager. The script supports Docker's **iptables backend**, including iptables-nft compatibility; it fails with Docker's native nftables backend when `DOCKER-USER` is unavailable. In that case, create an equivalent policy in your firewall manager before opening the port. Do not run these rules inside the sensor or dashboard. The sensor has no `NET_ADMIN` capability.

Verify actual outbound connections. Replace the targets with **existing, listening** host and LAN services; first verify their availability directly from the host. A test against a closed port does not prove firewall isolation.

```bash
docker compose exec -T sensor python - 172.30.222.1:22 192.168.1.1:80 1.1.1.1:443 < scripts/check-egress.py
```

Every target must be unreachable. Also test the web container's IP and an available LAN service. Then expose the sensor only after isolation passes:

```bash
SSH_BIND=0.0.0.0 docker compose up -d --force-recreate sensor
```

Supply this override again on future container recreations, or persist it in an optional `.env`/Compose override. From another machine, verify that incoming SSH connections to the honeypot still work. Persist the rules using a verified boot/reload procedure (for example, the systemd setup loaded before Docker in the detailed firewall guide) and **repeat verification after host/Docker restarts and network changes**. With iptables-persistent or another firewall manager, also verify rule-loading order and behavior when Docker creates its chains. The application cannot confirm the correctness of another host's firewall.

For native Linux deployments, verify the host firewall on the target Linux machine. Docker Desktop has a separate VM and Windows firewall boundary; use the opt-in [Windows TCP 2222 procedure](docs/windows-public.md) and its live VM isolation checks instead of assuming native Linux systemd rules apply to Windows.

## Router and public port

Only after isolation has been successfully verified, forward your chosen router **TCP** port (for example, 22 or 2222) to the honeypot host's IP and `SSH_PORT=2222`. Do not forward dashboard port 8080. Check that the rule does not target the real administrative SSH server. Port forwarding may not work behind CGNAT. Address IPv6 exposure separately; this project provides an IPv4 sensor network.

## Storage, retention, and updates

Volumes `ssh-sentinel_events`, `ssh-sentinel_sensor-keys`, and `ssh-sentinel_dashboard-data` survive restarts. The dashboard has read-only access to event files. The sensor has neither a database mount nor dashboard credentials.

Import uses UUID deduplication and transactional file positions. Invalid lines are skipped; incomplete lines are completed on the next import. SQLite retention runs during import; JSONL retention runs on writes and every ten seconds. Entire JSONL files are deleted based on their last write; daily rotation limits the difference from the oldest event's age to at most one day. When the quota is reached, the oldest closed spool files are removed even if the dashboard has not imported them yet. A full disk can cause the sensor to drop events and report unhealthy status; this service is not a replacement for a lossless audit system.

SQLite has an event-count quota, a data budget, and a safety limit for the main file. The oldest events are deleted when the budget is exceeded. WAL, index overhead, and backups need additional space; the main-file limit is not a quota for the entire filesystem. Below 64 MiB free space, import pauses and health reports an error. Export reads 100 records at a time and releases its SQLite transaction between batches, so a slow HTTP client does not hold a long-lived WAL snapshot. Concurrent retention may cause an export to omit records deleted in the meantime. Retention does not guarantee forensic erasure from SSDs/backups. Older databases larger than a new limit do not immediately shrink physically; monitor their actual size and free space during recovery or migration.

Before updating, make a backup, obtain the new source version, and run:

```bash
docker compose build --pull
docker compose up -d --wait
docker compose ps
```

Supply any configuration overrides used for the deployment when updating. `docker compose down` preserves data. **`docker compose down -v` deletes data.** Never install damaged or untrusted source code as an update. Dependencies are pinned to exact versions and SHA256 checksums in `requirements.lock`.

## Backup and restore

These commands use Bash on the Linux host. Stopping both services ensures a consistent SQLite and spool backup. Archives contain captured passwords and the private SSH host key; store them with restricted permissions, preferably encrypted.

```bash
docker compose stop
mkdir -p backups
chmod 700 backups
for volume in events sensor-keys dashboard-data; do
  docker run --rm --network none --user 0 --entrypoint python \
    -v "ssh-sentinel_${volume}:/source:ro" -v "$PWD/backups:/backup" \
    ssh-sentinel-web:local -c \
    "import tarfile; t=tarfile.open('/backup/${volume}.tar.gz','w:gz'); t.add('/source',arcname='.'); t.close()"
done
chmod 600 backups/*.tar.gz
docker compose up -d --wait
```

Restore trusted backups of your own into empty volumes (do not merge them with older data):

```bash
docker compose stop
# On a new machine, first create volumes without starting services:
docker compose create
for volume in events sensor-keys dashboard-data; do
  docker run --rm --network none --user 0 --entrypoint python \
    -v "ssh-sentinel_${volume}:/target" -v "$PWD/backups:/backup:ro" \
    ssh-sentinel-web:local -c \
    "import os,tarfile; assert not os.listdir('/target'), 'Target must be empty'; t=tarfile.open('/backup/${volume}.tar.gz'); t.extractall('/target',filter='data'); t.close(); [os.chown(os.path.join(root,name),10001,10001,follow_symlinks=False) for root,dirs,files in os.walk('/target') for name in ['.']+dirs+files]"
done
docker compose up -d --wait
```

If the volumes are not empty, restore into a new project/new volumes or deliberately empty them after making a safe backup. Preserving the host key avoids an unexpected SSH fingerprint change. Include any deployment overrides when recreating services during backup or restore.

## Development and tests

```bash
python3.15 -m venv .venv
. .venv/bin/activate
pip install --require-hashes -r requirements-dev.lock
python -m pytest -q
python -m pip_audit -r requirements.lock -r requirements-bootstrap.lock --require-hashes --disable-pip
docker compose config --quiet
```

Tests create their own temporary directories and SSH ports; they never execute attacker commands. CI tests Python 3.14.10/3.15.2, dependencies, and ARM64/AMD64 builds. Actions are pinned to verified commit SHAs. For a manual ARM64 build: `docker buildx build --platform linux/arm64 -f docker/Dockerfile.sensor .`, and likewise for `Dockerfile.web`. Running ARM64 tests requires an ARM64 host or QEMU; a successful build alone does not prove network behavior.

Update the runtime by rebuilding containers; there is no need to change the host's system Python. `requirements-bootstrap.lock` pins the pip 26.3 installer; Python runtime/test dependencies have their own hash locks. HTMX 2.0.11 and Chart.js 4.6.1 are refreshed with `scripts/update_vendor.py`, which verifies the npm archive's SHA512 checksum and writes file SHA256 checksums to `static/vendor/manifest.json`.

The detailed security audit and unresolved system findings are in the [audit reports](docs/audit/SECURITY-AUDIT-2026-11-07.md). A successful pip audit does not establish the absence of CVEs in Debian packages or vendored build tools.

## GitHub Actions and container publishing

The **Checks and container images** workflow tests the application and dependencies before building both images for `linux/amd64` and `linux/arm64`.

Images are published to GitHub Container Registry:

- `ghcr.io/unlink/ssh-sentinel-sensor`
- `ghcr.io/unlink/ssh-sentinel-web`

Names are derived automatically from the GitHub repository and converted to registry-compatible lowercase names, so forks publish under their own namespace.

| Event | Build | Push to GHCR |
|---|---|---|
| Pull request | Both images after successful tests | Never |
| Push to the repository's default branch | Both images after successful tests | Yes; branch, commit SHA, and `latest` tags |
| Push of a tag starting with `v` | Both images after successful tests | Yes; Git tag and commit SHA; a valid semantic version also gets a version tag such as `1.2.3` |
| Push to another branch | Both images after successful tests | No |
| Manual workflow run | Both images after successful tests | Only when **publish** is checked |

For a manual release, open **Actions → Checks and container images → Run workflow**, select the branch, and check **publish**. Uncheck it for a build-only run. Authentication uses the automatically provided `GITHUB_TOKEN` with job-scoped `packages: write`; no personal access token, Docker Hub secret, or `.env` file is required. Repository/organization policies must permit package publishing.

For a versioned release, push a version tag such as `v1.2.3` after committing the desired source revision. The default-branch `latest` tag is updated only by builds of that branch; publishing an older release tag does not overwrite it. Immutable commit tags use the `sha-<full-commit-sha>` format. Pull requests do not log in to GHCR or push images, including fork PRs.

After a successful publish, the package appears in the repository owner's **Packages** area. New GHCR packages may be private; adjust package visibility if anonymous pulls are required. If a package already exists, grant this repository access in the package's **Manage Actions access** settings. Build output includes the image digest, source labels, provenance and SBOM. Shared build caches are scoped separately for the sensor and web.

Example pull after a default-branch publish (authenticate to GHCR first for private packages):

```bash
docker pull ghcr.io/unlink/ssh-sentinel-sensor:latest
docker pull ghcr.io/unlink/ssh-sentinel-web:latest
```

The default Compose configuration still builds local source. Publishing a package does not deploy or replace running containers automatically. Workflow validation can be run with [actionlint](https://github.com/rhysd/actionlint); actual publishing is verified only after a workflow completes on GitHub.

## AI-assisted development

SSH Sentinel was built with assistance from **ChatGPT AI**, including implementation, documentation, and automated testing. AI-assisted security reviews are recorded in `docs/audit`; they do not replace independent review or verification of the target deployment.

## Troubleshooting

| Problem | Check |
|---|---|
| Container is unhealthy | `docker compose ps`, `docker compose logs --tail=100`; free disk space, volume permissions, and import |
| Dashboard requires an account | Run the `create-admin` CLI; the password is not entered in `.env` |
| HTTP 400 Invalid host | Add the hostname/IP to `ALLOWED_HOSTS` and recreate the container |
| HTTP 403 after login | Refresh the login page, allow cookies, and use consistent hostname/Origin and HTTPS settings |
| HTTP 429 | Wait five minutes after failed attempts |
| SSH inaccessible externally | `SSH_BIND`, port, host firewall, router, CGNAT; verify an internal connection |
| SSH channel refused after the first command | Intentional one-channel-per-connection limit; open a new connection |
| Missing events | Import interval, filters, retention, spool quota, and full disk |
| Permission denied on a volume | New volumes use UID/GID 10001; preserve ownership and permissions on restore |
| Network overlaps VPN/LAN | Change both subnets and the corresponding firewall rules |

Security model and reporting: [SECURITY.md](SECURITY.md). Design and implementation plans are in `docs/superpowers/`.

