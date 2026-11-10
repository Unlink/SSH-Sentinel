# Country activity map review — 2026-11-10

## Scope
Offline weighted-country aggregation, existing dashboard time window, local SVG geometry, choropleth presentation, accessible text totals and HTMX refresh. No sensor, forwarding or captured-event schema change.

## Verification
- Full suite: 97 passed, 1 skipped for Windows symlink privileges.
- Independent review: no actionable issues; reviewer independently ran 41 focused GeoIP/map/web tests and verified asset SHA256 and ISO uniqueness.
- Tests cover more than ten source IPs, connection-only counts, shared time cutoff, IPv4/IPv6/mapped and nonpublic handling, one country-only lookup connection, unknown/unavailable metadata, small countries missing from geometry, intensity levels, local assets, empty states and HTMX refresh integration.
- Natural Earth 5.1.2 public-domain 1:110m data is SHA256-pinned, transformed into 177 local country paths, and documented with source/license/compiled checksum metadata. Source coordinate validation limits geometry to finite world bounds. Runtime uses no tile/map provider or added JavaScript library.
- Browser preview with synthetic session records verified visible country highlights, country list, unknown/local count and time-range selection. The map uses native country/count titles, focusable positive paths and a textual country list as an accessible alternative.
- One local development-host benchmark processed 10000 weighted IPs in 0.064 seconds; performance depends on deployment hardware and retained events.
- Network-disabled image test passed. Web-only deployment preserved sensor container identity and application health. Live country/unknown/not-drawn counts reconciled exactly with total connections.

## Interpretation and limitations
A connection event is not proof of malicious activity. GeoIP approximates source-IP location, not attacker nationality or identity. Low-resolution geometry omits some small countries; their counts remain visible in the country list and a separate not-drawn total. Unknown/local sources are never silently attributed to a country. Color intensity is relative and logarithmic, so exact counts should be read from the list/tooltips. Retention and the currently bundled GeoIP snapshot determine the available data. The remote deployment is not changed by a local web restart.
