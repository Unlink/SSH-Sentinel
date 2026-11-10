# Offline GeoIP/ASN review — 2026-11-10

## Scope
SHA-pinned DB-IP Lite snapshot builder, local read-only range lookup, bounded cache, SVG flag supply chain, GUI integration and web-only Docker packaging. No changes to SSH parsing, real/virtual forwarding, captured event schema or export format.

## Verification
- Full suite: 90 passed, 1 skipped for Windows symlink privileges.
- Tiny local fixtures cover IPv4/IPv6 boundaries and gaps, mapped IPv4, nonpublic/reserved/multicast/site-local addresses, independently missing country/ASN, unknown asset codes, malformed/corrupt/missing databases, invalid/overlapping/oversized source rows, URL and checksum validation.
- HTML tests verify flags, country and ASN on overview/history/detail and HTMX responses; hostile organization labels are escaped. Raw exported events remain unchanged.
- Official November 2026 CSV snapshots compile into a 49.7 MiB SQLite database with 732796 country and 485292 ASN ranges. Source compressed archives are pinned by SHA256, and bounded streaming validates the decompressed input. Builds fail on checksum/validation errors.
- 249 ISO flag SVGs and country names are vendored from flag-icons 7.6.0 after npm SHA512 verification. The MIT license and per-file hashes are included. DB-IP CC-BY attribution, snapshot month and accuracy note are displayed/documented.
- Independent review found a reserved IPv6 classification gap and an uncaught malformed-schema path. Both were reproduced, fixed and regression-tested; focused re-review found no further material issues.
- Built Docker image performs successful GeoIP and ASN queries with --network none, a read-only filesystem, no capabilities and UID10001. Compiled asset mode is0444. Web-only deployment retained the sensor container and service health; all last 50 live session rows had country/ASN matches. GUI preview used synthetic session records.

## Limits
No runtime network lookups or automatic dataset refresh. Pull/redeploy an image built from an updated pinned snapshot to refresh metadata. No city coordinates or identity attribution are claimed. IP geolocation is approximate and affected by proxies/VPNs and provider coverage; ASN identifies a network organization. Historical events are enriched on display using the currently bundled snapshot. Private/reserved sources never receive a country flag. Local source checkouts without a compiled database show unavailable metadata while the rest of the app remains usable. Remote hosts are not automatically updated by a local deployment or Git push.
