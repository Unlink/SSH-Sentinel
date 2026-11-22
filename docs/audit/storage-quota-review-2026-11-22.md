# Four-GiB event budget review — 2026-11-22

## Change

The supported event-data budget increases from 1 GiB to 4 GiB. The main SQLite
file ceiling increases from 4 GiB to 8 GiB, preserving the required two-times
headroom. The supported event-count ceiling increases to 4,194,304, matching the
four-GiB budget divided by the minimum 1024-byte accounting charge per event.
Defaults, retention, capacity enforcement, sensor spool settings and container
resource limits remain unchanged.

## Verification

- New tests reproduced rejection of the requested configuration before the fix.
- Seven configuration/storage tests cover environment parsing, inclusive maxima,
  rejection above maxima, required SQLite headroom, unchanged defaults and a real
  SQLite connection with an 8 GiB page ceiling and a file smaller than 1 MiB.
- Existing capacity/import tests still confirm oldest-event pruning and that
  processed spool data is not automatically replayed after pruning.
- Full suite: 104 passed, 1 skipped for Windows symlink privileges.
- The first full run exposed an existing password-capture test assumption: the
  local SSH agent offered a public key before password authentication. The test
  now selects the password event explicitly; production authentication is unchanged.
- Independent review found no actionable issue and independently passed all seven
  new tests. The password-event test clarification was also reviewed.

## Operational scope

These are opt-in limits, not a four-GiB cap on the entire installation. WAL, JSONL,
temporary files and backups require additional disk space. Smaller event-count
limits and age retention can still prune earlier. Raising limits does not recover
previously pruned data or guarantee a particular retention duration/performance.
Deploy an updated image before applying the expanded environment values.
