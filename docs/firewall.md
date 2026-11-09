# Firewall on the target Linux host

Instructions for Debian 13, Debian-based 64-bit Raspberry Pi OS, and Ubuntu with systemd and standard Docker Engine. Run these steps on the **host**, not inside a container. Windows/Docker Desktop is not the target of this guide.

Goal: the sensor accepts incoming SSH connections but must not initiate connections to the host, dashboard, LAN, or internet. Replies to incoming connections remain allowed. The dashboard is available only at `127.0.0.1:8080`.

The recommended setup below uses a small, dedicated nftables table. It does not require changing Docker's firewall backend and does not use or modify Docker's tables. It can coexist with Docker's iptables backend or its native nftables backend. Docker's native nftables backend has no `DOCKER-USER`; custom rules go in a separate table with appropriate hooks. [Docker documentation](https://docs.docker.com/engine/network/firewall-nftables/)

## 1. Start without a public port

No `.env` file is required. Compose automatically applies these defaults:

```dotenv
SSH_BIND=127.0.0.1
SSH_PORT=2222
WEB_BIND=127.0.0.1
WEB_PORT=8080
SENSOR_SUBNET=172.30.222.0/24
WEB_SUBNET=172.30.223.0/24
```

If you already use shell environment variables, an optional `.env`, or a Compose override, check that they retain these local bindings. From the project root:

```bash
docker compose up -d --build --wait
docker compose ps
docker network inspect ssh-sentinel_sensor-net --format '{{json .IPAM.Config}} IPv6={{.EnableIPv6}}'
```

Verify subnet `172.30.222.0/24` and `IPv6=false`. A different Compose project name also changes the network name. If the subnet overlaps your LAN/VPN, first change `SENSOR_SUBNET` and the corresponding value in the rules below. Bash shell overrides or optional persistent `.env`/Compose overrides can supply configuration changes; `.env.example` is only an optional reference. Do not forward the router port yet. Keep an existing administrative SSH connection to the host open; the honeypot uses a different port from real server administration.

## 2. Identify the existing firewall

```bash
sudo iptables --version
sudo iptables -S DOCKER-USER
sudo nft list ruleset
systemctl is-active nftables ufw firewalld
```

An error for `DOCKER-USER` may indicate Docker's native nftables backend; it does not establish the backend by itself. Also check your Docker configuration in `/etc/docker/daemon.json` and the options shown by `systemctl cat docker.service`.

`iptables ... (nf_tables)` is the compatible iptables frontend over nftables, not automatically Docker's native nftables backend. Leave Docker's automatic rules enabled. A UFW rule for port 2222 alone does not guarantee protection of a published container, because Docker can redirect traffic before UFW INPUT rules. [Docker: packet filtering](https://docs.docker.com/engine/network/packet-filtering-firewalls/)

If you use a centrally managed firewall, integrate the following table into its configuration and reload procedure. Do not use a global `flush ruleset`, `iptables -F`, or a global INPUT/FORWARD policy change as part of this guide; these could remove existing rules or disrupt server administration.

## 3. Prepare a dedicated nftables table

If `nft` is missing, install it on Debian/Ubuntu:

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends nftables
```

Do not blindly enable the distribution's `nftables.service` with its default file, which may contain `flush ruleset`. The following steps use a separate file and service. If UFW/firewalld/nftables.service already manages your firewall, preserve its rules and check behavior after it reloads.

```bash
sudo install -d -m 0755 /etc/ssh-sentinel
sudo tee /etc/ssh-sentinel/firewall.nft >/dev/null <<'EOF'
define sensor_subnet = 172.30.222.0/24

# add is idempotent; flush touches only this project's own table.
# nft -f submits the following update as one transaction.
add table inet ssh_sentinel
flush table inet ssh_sentinel

table inet ssh_sentinel {
    chain forward_guard {
        type filter hook forward priority -10; policy accept;
        ip saddr $sensor_subnet ct state established,related counter accept
        ip saddr $sensor_subnet counter drop
    }

    chain host_guard {
        type filter hook input priority -10; policy accept;
        ip saddr $sensor_subnet ct state established,related counter accept
        ip saddr $sensor_subnet counter drop
    }
}
EOF

sudo nft --check --file /etc/ssh-sentinel/firewall.nft
sudo nft --file /etc/ssh-sentinel/firewall.nft
sudo nft -a list table inet ssh_sentinel
```

`forward_guard` blocks new sensor connections through the host, including to the LAN, internet, and other containers. `host_guard` blocks connections directly to the host. The source-subnet check runs before outbound SNAT. An incoming client has its own source IP, so these rules do not block its SSH request. The sensor's reply belongs to an established connection.

An `accept` in one nftables base chain does not bypass possible later rules in another firewall; this guide therefore does not loosen its existing restrictions. A `drop` stops the matching packet. Syntax and check mode are described in the [official nft manual](https://netfilter.org/projects/nftables/manpage.html).

The rules also allow already established connections; apply them while the sensor is still local or stopped, before untrusted traffic arrives. When changing the policy of an already running public sensor, stop it first and also check remaining conntrack states.

## 4. Load rules before Docker and after reboot

Check the path with `command -v nft`; this example assumes `/usr/sbin/nft`.

```bash
sudo tee /etc/systemd/system/ssh-sentinel-firewall.service >/dev/null <<'EOF'
[Unit]
Description=SSH Sentinel host and egress isolation
After=local-fs.target nftables.service ufw.service firewalld.service
Before=docker.service

[Service]
Type=oneshot
ExecStart=/usr/sbin/nft -f /etc/ssh-sentinel/firewall.nft
ExecReload=/usr/sbin/nft -f /etc/ssh-sentinel/firewall.nft
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

sudo install -d -m 0755 /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/ssh-sentinel-firewall.conf >/dev/null <<'EOF'
[Unit]
Requires=ssh-sentinel-firewall.service
After=ssh-sentinel-firewall.service

[Service]
ExecStartPre=/usr/sbin/nft -f /etc/ssh-sentinel/firewall.nft
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now ssh-sentinel-firewall.service
sudo systemctl status ssh-sentinel-firewall.service --no-pager
sudo systemctl show docker.service -p Requires -p After
```

This dependency applies to the **entire Docker daemon on the host**: if the firewall service fails to start or rule loading in `ExecStartPre` fails, Docker will not start. `ExecStartPre` restores the rules on every daemon start even when the firewall service is already marked active. On a shared host, coordinate this change with its administrator. This is intentional for a controlled deployment on a dedicated honeypot host. Using only Docker's `ExecStartPost` would leave a window in which an automatically restarted public container could start before the rules.

The dedicated table survives a normal Docker restart. Another firewall's reload can remove it if that firewall's configuration clears the entire ruleset. In that case, its persistent configuration must include this file, or the file must be loaded again and isolation verified after each reload. `RemainAfterExit=yes` alone does not prove that nobody subsequently deleted the rules.

After editing your rule file, run `nft --check` first, then:

```bash
sudo systemctl reload ssh-sentinel-firewall.service
sudo nft -a list table inet ssh_sentinel
```

## 5. Verify actual blocking

Testing closed ports is insufficient. Prepare genuinely listening targets and first reach them from the host.

For a host-service test, find the sensor network's gateway (default `172.30.222.1`). In a second host terminal, start a temporary server in an empty directory:

```bash
SENTINEL_FW_TEST_DIR=$(mktemp -d)
python3 -m http.server 18081 --bind 172.30.222.1 --directory "$SENTINEL_FW_TEST_DIR"
```

From the first terminal, the host should receive an HTTP response:

```bash
curl --max-time 3 http://172.30.222.1:18081/
```

Also choose a known listening LAN service and an internet target reachable from the host, for example:

```bash
curl --max-time 3 http://192.168.1.10:18081/
curl --connect-timeout 3 --max-time 5 https://1.1.1.1/
```

Replace the LAN address and port with your own test server; the address shown is only an example. If the host cannot reach a target, do not use it as evidence of isolation. Then run the test **inside the sensor** from the project root:

```bash
docker compose exec -T sensor python - \
  172.30.222.1:18081 192.168.1.10:18081 1.1.1.1:443 \
  < scripts/check-egress.py
sudo nft list table inet ssh_sentinel
```

Expected result: every target reports `UNREACHABLE`, the test exits with code 0, and the DROP-rule counters increase. `FAIL: sensor reached ...` means the port must not yet be exposed to the internet. `UNREACHABLE` without a demonstrably reachable target and corresponding counters is not sufficient evidence that the firewall is correct.

Stop the temporary HTTP server with Ctrl+C in its terminal. Also verify separation from the dashboard network and current bindings with `docker compose ps`. This guide covers IPv4; leave IPv6 disabled in the project's networks. Enabling it or changing the networking mode requires corresponding IPv6 rules and live tests.

## 6. Expose only the honeypot and repeat tests after reboot

Only after the egress test passes, set `SSH_BIND=0.0.0.0` while keeping `WEB_BIND=127.0.0.1`. In Bash, no `.env` file is needed:

```bash
SSH_BIND=0.0.0.0 docker compose up -d --force-recreate sensor
docker compose ps
```

This shell override applies only to that command. Supply `SSH_BIND=0.0.0.0` again on future recreations or updates, or persist the setting in an optional `.env` or Compose override file. A Compose override must configure the corresponding published sensor port; `.env` uses `SSH_BIND`. Keep the dashboard bound to loopback in either case.

From another LAN computer, test `ssh -p 2222 root@HOST_IP` and leave the simulated shell with `exit`. If a separate host/firewall or cloud security-group rule is required, allow the incoming TCP honeypot port according to local policy; do not change the real administrative SSH server's port. Dashboard port 8080 must remain unreachable externally.

During a maintenance window, restart the host; after logging in, repeat:

```bash
sudo systemctl status ssh-sentinel-firewall.service --no-pager
sudo nft list table inet ssh_sentinel
docker compose ps
docker compose exec -T sensor python - \
  172.30.222.1:18081 192.168.1.10:18081 1.1.1.1:443 \
  < scripts/check-egress.py
```

Before the post-reboot egress test, restart the temporary host HTTP server and verify all targets are reachable from the host. Repeat these checks after Docker restarts or another firewall reloads. Only then forward your chosen router **TCP** port to the host's IP and port 2222. Never forward the dashboard. Verify internet access from another network, for example mobile data, rather than relying only on your home router's hairpin NAT.

## Alternative: existing iptables script

With Docker's iptables backend, you can use the existing script instead of the nft table for manual verification:

```bash
sudo sh scripts/firewall.sh 172.30.222.0/24
sudo iptables -nvL SSENTINEL_FWD
sudo iptables -nvL SSENTINEL_HOST
```

It uses `DOCKER-USER` and `INPUT`; [Docker recommends DOCKER-USER for rules before its own forwarding](https://docs.docker.com/engine/network/firewall-iptables/). Docker's native nftables backend does not create this chain, so the script fails. The script itself does not configure persistence. Do not treat it as a complete unattended internet deployment without your own verified boot/reload procedure; use the persistent nft table above or an equivalent managed-firewall setup for that purpose. You do not need both approaches at once.

## Rollback

First remove router port forwarding and stop the sensor:

```bash
docker compose stop sensor
```

For the dedicated nft-table setup, remove only your Docker systemd dependency and your own rules:

```bash
sudo rm /etc/systemd/system/docker.service.d/ssh-sentinel-firewall.conf
sudo systemctl daemon-reload
sudo systemctl disable --now ssh-sentinel-firewall.service
sudo nft delete table inet ssh_sentinel
```

For the manual iptables setup, remove only jumps for the subnet used and the project's chains:

```bash
sudo iptables -D DOCKER-USER -s 172.30.222.0/24 -j SSENTINEL_FWD
sudo iptables -D INPUT -s 172.30.222.0/24 -j SSENTINEL_HOST
sudo iptables -F SSENTINEL_FWD
sudo iptables -X SSENTINEL_FWD
sudo iptables -F SSENTINEL_HOST
sudo iptables -X SSENTINEL_HOST
```

Roll back only the approach you deployed; adjust the subnet and first check `iptables -S` if any chain is also used elsewhere. Do not delete other system or Docker rules. Before restarting without isolation, restore `SSH_BIND=127.0.0.1` in any persistent overrides and recreate the sensor with the loopback binding, for example `SSH_BIND=127.0.0.1 docker compose up -d --force-recreate sensor` in Bash. This procedure does not delete database volumes.

## Guide verification status

The rules and procedure are prepared for the target Linux host and checked against official Docker/nft documentation. This project change involved documentation only; these rules were neither applied on the development Windows host nor claimed to provide live-tested network isolation there. The listed tests on the actual target host are decisive.
