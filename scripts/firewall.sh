#!/bin/sh
# Run on the Linux Docker host as root, before publishing SSH to the internet.
# Works with Docker's iptables backend (iptables-legacy or iptables-nft).
set -eu
subnet="${1:-172.30.222.0/24}"
case "$subnet" in *[!0-9./]*|'') echo 'Expected an IPv4 CIDR' >&2; exit 1;; esac
iptables -nL DOCKER-USER >/dev/null 2>&1 || {
  echo 'DOCKER-USER missing. Use Docker iptables backend or equivalent audited nftables policy.' >&2
  exit 1
}
for chain in SSENTINEL_FWD SSENTINEL_HOST; do
  iptables -nL "$chain" >/dev/null 2>&1 || iptables -N "$chain"
  iptables -C "$chain" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN 2>/dev/null ||
    iptables -A "$chain" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
  iptables -C "$chain" -j DROP 2>/dev/null || iptables -A "$chain" -j DROP
done
iptables -C DOCKER-USER -s "$subnet" -j SSENTINEL_FWD 2>/dev/null ||
  iptables -I DOCKER-USER 1 -s "$subnet" -j SSENTINEL_FWD
iptables -C INPUT -s "$subnet" -j SSENTINEL_HOST 2>/dev/null ||
  iptables -I INPUT 1 -s "$subnet" -j SSENTINEL_HOST
echo "Blocked new sensor connections from $subnet to host, LAN, other containers and internet."
echo 'Persist rules using your distribution firewall manager; verify after every Docker/host restart.'
