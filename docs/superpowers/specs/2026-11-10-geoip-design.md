# Local GeoIP and ASN enrichment

The user requested country flags next to source IPs and ASN information. Enrich public observed source IPs in the dashboard top-IP ranking, session list and session detail. Keep raw event schema, source IPs and exports unchanged; existing historical sessions get metadata on display.

## Architecture and choices
Use monthly DB-IP Lite country and ASN CSV snapshots, pinned by release, HTTPS URL and SHA256 in geoip-sources.json. A standard-library build helper validates and compiles them into a read-only SQLite range database in the web image. No dependency or API key, runtime download, external IP lookup, sensor change or Compose volume is required. API lookup services would expose observed IPs and add availability/rate-limit problems; licensed account-dependent downloads add setup work. Country/ASN queries use indexed range starts with end validation, IPv4/IPv6 family separation and IPv4-mapped normalization. Use bounded per-process caching and read-only per-call connections. Missing/corrupt data must degrade to unknown, not break login or history.

## UI and assets
Display a local SVG flag and country name/code plus AS number and organization. Vendor flag-icons 7.6.0 SVGs/country names with npm SHA512 verification and MIT attribution. Escape labels, accept only known ISO asset codes and do not turn dataset values into arbitrary asset paths. Private/reserved/multicast addresses are labelled Local/reserved; never geolocate them. Show country and ASN unknown independently. Add required DB-IP attribution, dataset release and an accuracy note; GeoIP is not attacker identity/location proof. All UI/docs stay English.

## Data lifecycle and limits
Rebuild/redeploy an image after explicitly refreshing manifest release/hashes to update datasets. No automatic runtime network activity. The builder streams bounded CSV rows and batches SQLite writes, limits compressed/uncompressed input and validates address family, order, overlap, codes and ASN range. The immutable compiled database stays separate from /data and event retention. Runtime cache has 4096 entries; database page cache stays bounded. Raw dataset files and generated database are not committed. Missing source hashes or validation errors fail image builds; local source checkouts without the compiled database remain usable with unknown metadata.

## Validation
Synthetic datasets test range boundaries/gaps, IPv4/IPv6/mapped IPs, private/reserved IPs, missing/partial/corrupt records, cache/escaping, and SHA/format validation. Web tests cover flags/ASN on overview, paginated and HTMX session lists and detail, with unchanged raw exports. Build actual datasets, verify live known-IP lookup without runtime network, run full tests and independent review, inspect rendered UI and deploy only web locally. Do not claim the user's remote RPi updated automatically.
