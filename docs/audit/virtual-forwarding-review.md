# Virtual forwarding review — 2026-11-10

## Scope
Custom local AsyncSSH direct-tcpip capture session; request/channel/lifetime limits; payload event schema/import; session overview/detail; English documentation. Previous dependency and platform audit reports remain historical.

## Results
- Full suite: 67 passed, 1 skipped (Windows symlink privileges).
- Independent code review: no material security or correctness defects. Reviewer independently reran 36 focused sensor/forwarding/web tests.
- A real controlled target accepted the baseline connection, then received no connection from a simulated tunnel. DNS lookup spy did not trigger for hostname destinations. The implementation returns a custom protocol handler and never AsyncSSH's real-forwarding boolean.
- Real SSH tests cover binary/fragmented capture, 2 KiB preview/base64 fidelity, 16 KiB input closure, 10-second channel timeout, 2 concurrent and 8 lifetime channels, 32-request admission budget including failures, invalid target rejection, disconnect cleanup, and continued fake-shell operation.
- Importer accepts both new event types; filtered grouped summaries count virtual tunnels. Payload HTML is escaped, remains absent from the overview, and round-trips through authenticated export. Browser verification used only synthetic records.
- Guarded live deployment captured a synthetic request and imported its destination, sample, count and close reason. Claimed origin did not override transport source IP. Post-deployment egress tests to proven Windows-host and internet listeners remained blocked; both application services were healthy.

## Boundaries
This is channel acceptance and observation, not a working proxy or a full service emulator. No DNS, outbound connections, destination-service replies or TLS impersonation occur. Targets and claimed origins are untrusted client-provided metadata. The event source IP remains the observed peer. Samples can contain sensitive client data and inherit the dashboard's authentication, retention and quota controls. Samples persist on channel completion. Historical denied forwarding events cannot reveal destinations which were not recorded at the time.
