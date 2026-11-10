# Virtual forwarding implementation plan

**Goal:** Observe SSH forwarding probes without allowing real forwarding.
**Spec:** ../specs/2026-11-10-virtual-forwarding-design.md
**Architecture:** Bounded byte-mode SSHTCPSession sink generates forward_open/forward_close; schema/import/UI recognize it.

- [x] Add failing real-protocol tests and adjust the old direct-forward denial expectation.
- [x] Implement bounded virtual channel capture and lifetime/concurrency admission in sensor.
- [x] Add event kinds and grouped/session-detail UI with ingestion, filtering and escaping regression tests.
- [x] Update English security/user docs; run full suite and independent review; fix material findings.
- [x] Deploy through guarded Windows helper, validate capture/import/egress isolation and commit changes.

## Verification ledger

- RED: real SSH direct-tcpip channel was refused before implementation; separate GUI regression failed because forwarding summaries were absent.
- GREEN: full suite 67 passed, 1 Windows symlink privilege skip. Independent reviewer reran 36 forwarding/sensor/web tests; no material security or correctness findings.
- Proved the controlled target listener accepts a direct baseline connection; simulated forwarding to its address made no connection. Resolver spy ruled out DNS requests for a hostname target.
- Verified binary sample fidelity, fragmentation/truncation, input budget, deadline, disconnect cleanup, concurrent/lifetime/admission caps and origin-IP attribution.
- Browser preview with synthetic records verified grouped outcome and full escaped forwarding detail; screenshot stored outside the repository.
- Deployed through guarded Windows helper. Live SSH captured a 69-byte synthetic probe to an .invalid hostname; dashboard imported forward_open/forward_close and showed one tunnel. Claimed origin did not replace observed source IP.
- Control destinations were reachable from Windows but remained unreachable from the sensor after deployment. Sensor and dashboard report healthy.
- Ruling: no fabricated application-service responses in this first capture-only release, as selected in the proposal. A client requiring real HTTP/TLS/SMTP validation may disconnect.
