# Dashboard country activity map

The user requested a world map highlighting countries from which honeypot traffic arrives. Use observed accepted SSH connection events, not inferred maliciousness or per-packet/event totals. Existing GeoIP remains the sole offline country source; no IPs, tiles or metadata are sent to map services.

## Approach
Render a responsive inline SVG choropleth on the server inside the existing ten-second HTMX overview refresh. It shares the selected 1/7/30-day window with the metrics. Precompute country paths from a SHA256-pinned Natural Earth 5.1.2 1:110m GeoJSON snapshot, preserving public-domain attribution/source manifest. Equirectangular projection avoids adding a JavaScript mapping library or runtime dependency. Local vector rendering is simpler and preserves privacy; online tile maps add network exposure and configuration without helping country-level counts.

## Counts and limits
Group all retained in-window connection events by IP in SQLite; do not use the top-ten-IP ranking. GeoIP aggregates weighted IPs using one read-only lookup connection and only the country table, avoiding per-IP file opens and unnecessary ASN queries. Range lookup and nonpublic classification match existing behavior. Known country counts, unavailable/unknown/local counts, total connections and small-territory counts remain explicit. Low-resolution shapes may omit small territories; their counts remain in the country list and are identified as not drawn. Counts cover accepted connections, not proven attacks or a person's physical location.

## Presentation
Neutral countries have zero observed connections; five positive intensity levels use log-scaled counts. Native SVG titles and accessible labels provide country and count; positive paths can receive keyboard focus. A textual country ranking provides an accessible alternative, including countries without geometry. Include the provider/snapshot attribution, map source, approximate-country caveat and empty/unavailable states. Keep all UI English and CSP-safe (classes, no inline scripts/styles or external resources).

## Verification
Synthetic country/weighted-IP datasets test complete aggregation, more than ten source IPs, connection-only and time-range filtering, IPv4/IPv6 normalization and nonpublic addresses, unavailable GeoIP, mapping/missing-territory totals, intensity levels, escaping and HTMX refresh. Validate generated geometry and source checksum. Run full tests and independent review, inspect rendered map, deploy web only and verify sensor unchanged. Preserve the user's exclusion of compose.rpi.yml from commits/pushes.
