# Windows source IP preservation

The user selected implementing the proposed native Windows proxy plus sensor PROXY protocol support. Preserve public IPv4 TCP 2222 and existing sensor egress isolation without moving to another machine.

## Approaches
A Linux VM or WSL mirrored networking changes the deployment platform. The selected native Windows Python TCP proxy retains Docker Desktop and the current application. It forwards to a localhost-only Docker binding on 2223 with mandatory PROXY v1 metadata. No new Python dependency is required.

## Trust and limits
Only the opt-in Windows profile enables PROXY parsing. Its backend must never be publicly bound. Local Windows processes and Docker administrators are trusted; PROXY v1 provides no authentication. The proxy always generates metadata from its accepted socket, never from client bytes. Strict bounded headers, five-second header/connect deadlines, connection caps, stream backpressure and session lifetime limits prevent unbounded queues. Standard Compose remains plain SSH. VM firewall rules stay in force. Do not use host networking or disable isolation.

## Acceptance
Real SSH through the native proxy records the original peer; forged client PROXY text cannot override it. Invalid/oversized/partial headers are rejected. Backend binds only 127.0.0.1:2223; dashboard stays 127.0.0.1:8080. Startup/stop instructions are English and reproducible; internet probes must appear under their real source IP.
