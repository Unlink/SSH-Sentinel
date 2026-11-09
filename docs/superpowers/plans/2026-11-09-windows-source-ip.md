# Windows source IP implementation plan

> Execute inline with superpowers:executing-plans.

**Goal:** Preserve client source IP on Windows/Docker Desktop at public TCP 2222.
**Spec:** ../specs/2026-11-09-windows-source-ip-design.md
**Architecture:** Native stdlib asyncio proxy adds PROXY v1 before forwarding to localhost 2223. An opt-in bounded protocol adapter hands validated peer metadata and SSH bytes to the existing SSH transport.

- [x] Add failing real-socket sensor/proxy tests: IPv4/IPv6, fragmented headers, malformed and oversized input, absent headers, client spoofing, connection limits and timeout cleanup.
- [x] Implement adapter in app/sensor/proxy_protocol.py; select it only with Settings.proxy_protocol, preserving direct mode.
- [x] Implement native proxy in scripts/windows_proxy.py with bounded connections, lifetime, connect deadlines and backpressure; integrate safe background lifecycle in PowerShell.
- [x] Update Windows Compose to localhost 2223 plus mandatory PROXY; update startup checks and English docs, including trusted-local-user boundary and shutdown.
- [x] Run full pytest, parse PowerShell, resolve Compose, deploy through guarded helper, verify isolation and external probes recorded with real IP; inspect diff before committing.

## Execution ledger

- Real socket regression tests initially failed because proxy_protocol was not supported; implemented mandatory adapter and native proxy; complete suite: 54 passed, 1 Windows symlink privilege skip.
- Ruling: implement directly in the existing workspace because the current deployment and pending public-port migration belong to this task; moving them to another worktree would split the deployment state.
- Actual external probes from Sweden and Japan reached public TCP 2222. Recorded connection IPs matched their published node IPs (not the Docker gateway).
- Sensor egress probes to a known Windows listener and internet TCP 443 remained blocked; dashboard and backend bindings stayed localhost-only.
- Independent code review found two process lifecycle defects; fixed both. Verified stop without the venv launcher, repeat start, and forced startup timeout cleanup with no orphan child/listener or stale identity.
- Windows venv Python uses a child runtime process; store actual listener PID, executable path and process birth time to avoid confusing the launcher or reused PID.
