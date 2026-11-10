# Session-first history

The user requested a clearer GUI showing sessions rather than individual events. Keep /history but render one row per sensor session_id, with source IP, first/last observed timestamps, latest recorded username, outcome, authentication/command/event counts and a link to the existing chronological detail. Raw event APIs and exports remain compatible. Keep UI/docs English.

## Approach
Aggregate existing SQLite events at query time: no migration or duplicate stored session state, including existing records and partially retained sessions. Group before pagination; filters match a session if any event contains each selected value, independently across events. Counts describe the full matching session. Order by last observed activity and session_id to break ties. No disconnect means "No disconnect recorded", not confirmed activity. Passwords appear only in detail/exports. Preserve escaping and authentication. Update navigation and dashboard links to Sessions.

## Verification
Test one row for many events, sessions spanning pagination, cross-event filters, full-session counts, deterministic ordering, missing start/disconnect, empty results, hostile text escaping, raw export compatibility and HTMX partial responses. Deploy only the web container so sensor/proxy/isolation stay running, then inspect the rendered UI.
