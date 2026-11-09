# Public TCP 2222 on Windows with Docker Desktop

This opt-in deployment runs a native Windows TCP proxy on `0.0.0.0:2222`, including the Windows host's public IPv4 address. It forwards to the Docker sensor on `127.0.0.1:2223`, adding a mandatory PROXY v1 header with the original client IP. Docker Desktop port forwarding alone replaces that IP with its gateway address. The dashboard remains at `127.0.0.1:8080`. Normal `docker compose up -d --build` keeps the project's safe localhost defaults and requires no `.env`.

Use Docker Desktop's Linux containers and the `desktop-linux` context. This setup was tested with Engine 29.7.2 and Compose 5.3.1. The override uses `!override`, requiring Compose 2.24.4 or newer. Do not stop a real administrative SSH server to free port 2222; use a different honeypot host instead.

## Guarded startup

Install Python 3.11 or newer on Windows and create a local environment if needed (`py -3 -m venv .venv`). The native proxy uses only the standard library; it does not need application dependencies installed on Windows.

From PowerShell in the repository root:

```powershell
./scripts/start-windows-public.ps1
```

The helper validates the Docker context, default sensor subnet, private dashboard binding, and port ownership. It builds `docker/Dockerfile.firewall`, stops only this project's sensor, and applies `scripts/firewall.sh` to `172.30.222.0/24` in the Docker Desktop VM host network namespace. The private sensor starts only after that command succeeds. The helper then starts `scripts/windows_proxy.py` with the local `.venv/Scripts/pythonw.exe`, hidden and without administrator rights. The public TCP 2222 listener belongs to this native process; Docker publishes only localhost TCP 2223. Repeating the helper reuses the verified proxy process.

The firewall helper is temporary, root-owned, read-only, and receives only `NET_ADMIN`, without a Docker socket or privileged mode. It changes only the project's `SSENTINEL_FWD`/`SSENTINEL_HOST` chains and subnet-specific jumps. The sensor and dashboard retain their non-root/read-only/no-capability restrictions. The administrative helper is built locally; GHCR publishes only the sensor and web application images.

**Run the helper again after every Docker Desktop/VM restart.** VM firewall rules may be lost when the VM is recreated. The public profile sets sensor `restart: "no"`, preventing automatic public startup before isolation is reapplied. Do not bypass this sequence with `docker start`, or by invoking the override directly after a VM restart. The dashboard may restart normally.

If `DOCKER-USER` is unavailable or the restricted helper cannot access it, startup fails with the sensor stopped. Do not remove this check. Docker Desktop internals may change; retest after upgrades. The native Linux systemd procedure in [firewall.md](firewall.md) does not configure Windows.

## Source IP trust boundary

`SENTINEL_PROXY_PROTOCOL=true` is enabled only by this Windows override. In that mode every backend connection requires a valid PROXY v1 TCP4/TCP6 header within five seconds; headers are capped at 108 bytes. The proxy constructs the header from its accepted Windows socket before forwarding any client bytes. Client-supplied PROXY text cannot replace it. Both the sensor adapter and proxy cap concurrent connections; the proxy limits session duration to 300 seconds and uses bounded reads with write backpressure.

PROXY v1 does not authenticate metadata. Windows local users/processes and Docker administrators are trusted: they can access the localhost backend and supply metadata themselves. Never expose TCP 2223, forward it through a router, or enable PROXY parsing on the plain public sensor. A deployment needing protection from untrusted local users needs an authenticated proxy channel instead. The native proxy is an additional host process to maintain; SSH parsing and all fake commands remain inside the isolated container. The listener is IPv4; the adapter also supports IPv6 metadata for other trusted deployments.

The proxy uses `.superpowers/windows-proxy.json` and credential-free diagnostic logs in `.superpowers/`. It is not installed as an automatic Windows service. After reboot or Docker Desktop restart, run the guarded startup again. If the backend is unavailable, connections fail closed.

## Windows inbound rule

In **PowerShell opened as Administrator**, run:

```powershell
./scripts/enable-windows-public.ps1
```

This creates or enables only `SSH-Sentinel-Honeypot-TCP2222`: inbound TCP 2222, remote addresses Any, all Windows profiles. It also disables the project's previous TCP 22 inbound rule if present. It does not open dashboard port 8080 or change unrelated firewall policy. UAC/administrator approval is required; canceling it leaves the rule unconfigured.

A local test to the host's own public IP is not proof of external reachability. Verify the current port from an independent internet connection after enabling the Windows inbound rule.

## Verify isolation and reachability

Use known listening destinations, first proving their availability before isolation. A closed/offline port does not prove blocking. See [the firewall testing procedure](firewall.md#5-verify-actual-blocking), adapting the addresses to Docker Desktop.

After guarded startup, from PowerShell:

```powershell
Get-Content scripts/check-egress.py -Raw | docker compose -f docker-compose.yml -f compose.windows-public.yml exec -T sensor python - VM_GATEWAY:LISTENING_PORT WINDOWS_HOST:LISTENING_PORT 1.1.1.1:443
docker compose -f docker-compose.yml -f compose.windows-public.yml ps
Get-NetTCPConnection -State Listen -LocalPort 2222,2223
Get-NetFirewallRule -Name SSH-Sentinel-Honeypot-TCP2222
```

Replace placeholders with proven listeners. All sensor probes should report `UNREACHABLE`, while the controlled listener remains reachable from an allowed network. Verify increasing `SSENTINEL_FWD` and `SSENTINEL_HOST` DROP counters in the VM.

Checks on this host confirmed a test VM listener, a listening Windows-host service, and internet TCP 443 were reachable before isolation and unreachable from the sensor afterward. The test listener remained reachable from the dashboard network; both DROP counters increased. Other containers were not stopped or reconfigured.

From another network, test:

```bash
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -p 2222 root@YOUR_PUBLIC_IPV4
```

Verify that new dashboard events show the external client address, rather than `172.30.222.1`. Historical events retain their recorded IP; the lost original address cannot be recovered. Use synthetic credentials and simulated commands such as `whoami`, then `exit`. Upstream ISP, campus/cloud, or router rules may still block ingress. If behind NAT, forward only TCP 2222 to this host, never the dashboard.

## Stop or return to localhost

Stop the native listener and this project's sensor:

```powershell
./scripts/start-windows-proxy.ps1 -Stop
docker compose -f docker-compose.yml -f compose.windows-public.yml stop sensor
```

Return to normal safe defaults:

```powershell
./scripts/start-windows-proxy.ps1 -Stop
docker compose -f docker-compose.yml up -d --force-recreate sensor
```

The sensor then binds to `127.0.0.1:2222`; review any shell overrides first. Remove the named Windows rule from Administrator PowerShell when public access is no longer needed:

```powershell
Remove-NetFirewallRule -Name SSH-Sentinel-Honeypot-TCP2222
```

After the sensor is stopped/private, remove VM rules using only the subnet-specific iptables rollback in [firewall.md](firewall.md#rollback). Do not flush all VM rules or restart the entire Docker daemon to stop this honeypot; other applications may depend on it. Application volumes are preserved.
