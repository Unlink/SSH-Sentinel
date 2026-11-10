# Session-first history implementation plan

**Goal:** Replace the event list with a paginated session overview.
**Spec:** ../specs/2026-11-10-session-history-design.md
**Architecture:** Bounded SQLite aggregate summaries feed the existing history route; event detail/API/export remain available.

- [x] Write failing regression tests for grouping, full-session counts and cross-event filters, session pagination, partial sessions and hostile text.
- [x] Add Database.session_summaries and route history through it.
- [x] Replace history rows with session summaries, update labels/navigation and English README.
- [x] Run full tests, inspect UI, review diff and deploy web only. Verify sensor and proxy remain intact.

## Verification ledger

- Regression reproduced: six events generated six overview links to the same session before the change; expected one.
- Full suite: 57 passed, 1 skipped (Windows symlink privileges).
- Independent review found no actionable issue. Removed overview event-export links because event filters differ from whole-session filters; session-specific exports remain in detail.
- Browser preview with synthetic data confirmed grouped rows, correct outcomes/counts, cross-event username/type filters, and full timeline navigation. Screenshot saved outside the repository.
- Deployed only web with --no-deps; sensor container ID unchanged and both services healthy. Live first page: 50 distinct session rows representing 115 retained events.
- Ruling: keep the existing /history URL and raw API/export semantics for compatibility; aggregate existing events on read, without migration or stored duplicate session state.
