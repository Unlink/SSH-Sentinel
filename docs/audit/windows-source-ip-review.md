# Windows source IP implementation review — 2026-11-09

## Scope
Native Windows stdlib TCP proxy, mandatory opt-in PROXY v1 sensor adapter, localhost-only backend, process lifecycle, deployment documentation. Existing host/container audits remain separate historical reports.

## Verification
- Full Windows pytest suite: 54 passed, 1 skipped (symlink privileges).
- Real SSH tests: fragmented IPv4/IPv6 headers preserve the claimed trusted-proxy peer through authentication and command events; combined header/SSH bytes also work.
- Malformed, oversized, family-mismatched, out-of-range and missing headers reject without creating SSH events. Pending-header connection cap and five-second timeout tested.
- Native proxy always generates its own metadata before client data; forged client headers cannot overwrite recorded peer IP. Connection cap, cleanup and session lifetime tested.
- Live independent internet probes from two countries reached TCP 2222; sensor connection records matched both probe source IPs.
- Sensor egress to the Windows host and internet remained blocked. Docker sensor backend binds 127.0.0.1:2223, dashboard 127.0.0.1:8080; native listener binds 0.0.0.0:2222.
- PowerShell syntax, resolved Compose configuration, guarded restart and idempotent native startup checked. Stop succeeds with the venv launcher temporarily unavailable. Forced startup timeout cleans both verified child and launcher, with no remaining listener or identity file.

## Review findings resolved
An independent reviewer found that startup timeout originally killed only the Windows venv launcher and that stop unnecessarily depended on a usable Python environment. The helper now validates persisted actual process identity before dependency checks and cleans verified children on startup failure. No source IP spoofing gap was found within the documented local trust boundary.

## Boundaries
PROXY v1 is not authenticated. Windows local processes and Docker administrators remain trusted. Never expose the backend port. Proxy mode is disabled in normal Compose. The native proxy is a normal host process and requires a maintained Windows Python installation. It is not an automatically installed service; rerun guarded startup after Docker Desktop/host restart. Old gateway-IP events are retained unchanged and cannot be repaired retrospectively.
