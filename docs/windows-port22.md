# Public TCP 22 on Windows with Docker Desktop

This opt-in deployment publishes the sensor on `0.0.0.0:22`, including the Windows host's public IPv4 address. The dashboard remains at `127.0.0.1:8080`. Normal `docker compose up -d --build` keeps the project's safe localhost defaults and requires no `.env`.

Use Docker Desktop's Linux containers and the `desktop-linux` context. This setup was tested with Engine 29.7.2 and Compose 5.3.1. The override uses `!override`, requiring Compose 2.24.4 or newer. Do not stop a real administrative SSH server to free port 22; use a different honeypot host instead.

## Guarded startup

From PowerShell in the repository root:

```powershell
./scripts/start-windows-port22.ps1
```

The helper validates the Docker context, default sensor subnet, private dashboard binding, and port ownership. It builds `docker/Dockerfile.firewall`, stops only this project's sensor, and applies `scripts/firewall.sh` to `172.30.222.0/24` in the Docker Desktop VM host network namespace. The sensor starts on public TCP 22 only after that command succeeds.

The firewall helper is temporary, root-owned, read-only, and receives only `NET_ADMIN`, without a Docker socket or privileged mode. It changes only the project's `SSENTINEL_FWD`/`SSENTINEL_HOST` chains and subnet-specific jumps. The sensor and dashboard retain their non-root/read-only/no-capability restrictions. The administrative helper is built locally; GHCR publishes only the sensor and web application images.

**Run the helper again after every Docker Desktop/VM restart.** VM firewall rules may be lost when the VM is recreated. The public profile sets sensor `restart: "no"`, preventing automatic public startup before isolation is reapplied. Do not bypass this sequence with `docker start`, or by invoking the override directly after a VM restart. The dashboard may restart normally.

If `DOCKER-USER` is unavailable or the restricted helper cannot access it, startup fails with the sensor stopped. Do not remove this check. Docker Desktop internals may change; retest after upgrades. The native Linux systemd procedure in [firewall.md](firewall.md) does not configure Windows.

## Windows inbound rule

In **PowerShell opened as Administrator**, run:

```powershell
./scripts/enable-windows-port22.ps1
```

This creates or enables only `SSH-Sentinel-Honeypot-TCP22`: inbound TCP 22, remote addresses Any, all Windows profiles. It does not open dashboard port 8080 or change other firewall policy. UAC/administrator approval is required; canceling it leaves the rule unconfigured.

During this deployment the sensor was bound to public TCP 22 and an SSH check through the host's public IPv4 passed. Windows UAC elevation for the named inbound rule was canceled. Installing that rule and checking reachability from an independent internet connection therefore remain administrator steps. A local test to the host's own public IP is not proof of external reachability.

## Verify isolation and reachability

Use known listening destinations, first proving their availability before isolation. A closed/offline port does not prove blocking. See [the firewall testing procedure](firewall.md#5-verify-actual-blocking), adapting the addresses to Docker Desktop.

After guarded startup, from PowerShell:

```powershell
Get-Content scripts/check-egress.py -Raw | docker compose -f docker-compose.yml -f compose.windows-port22.yml exec -T sensor python - VM_GATEWAY:LISTENING_PORT WINDOWS_HOST:LISTENING_PORT 1.1.1.1:443
docker compose -f docker-compose.yml -f compose.windows-port22.yml ps
Get-NetTCPConnection -State Listen -LocalPort 22
Get-NetFirewallRule -Name SSH-Sentinel-Honeypot-TCP22
```

Replace placeholders with proven listeners. All sensor probes should report `UNREACHABLE`, while the controlled listener remains reachable from an allowed network. Verify increasing `SSENTINEL_FWD` and `SSENTINEL_HOST` DROP counters in the VM.

Checks on this host confirmed a test VM listener, a listening Windows-host service, and internet TCP 443 were reachable before isolation and unreachable from the sensor afterward. The test listener remained reachable from the dashboard network; both DROP counters increased. Other containers were not stopped or reconfigured.

From another network, test:

```bash
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -p 22 root@YOUR_PUBLIC_IPV4
```

Use synthetic credentials and simulated commands such as `whoami`, then `exit`. Upstream ISP, campus/cloud, or router rules may still block ingress. If behind NAT, forward only TCP 22 to this host, never the dashboard.

## Stop or return to localhost

Stop only the public sensor:

```powershell
docker compose -f docker-compose.yml -f compose.windows-port22.yml stop sensor
```

Return to normal safe defaults:

```powershell
docker compose -f docker-compose.yml up -d --force-recreate sensor
```

The sensor then binds to `127.0.0.1:2222`; review any shell overrides first. Remove the named Windows rule from Administrator PowerShell when public access is no longer needed:

```powershell
Remove-NetFirewallRule -Name SSH-Sentinel-Honeypot-TCP22
```

After the sensor is stopped/private, remove VM rules using only the subnet-specific iptables rollback in [firewall.md](firewall.md#rollback). Do not flush all VM rules or restart the entire Docker daemon to stop this honeypot; other applications may depend on it. Application volumes are preserved.
