# Vendored browser dependencies

- HTMX 2.0.11: https://github.com/bigskysoftware/htmx/tree/v2.0.11 (0BSD; HTMX-LICENSE).
- Chart.js 4.6.1: https://github.com/chartjs/Chart.js/tree/v4.6.1 (MIT; CHARTJS-LICENSE.md).

Files are served locally; no CDN/network access is required at runtime. `manifest.json` records registry tarball SHA512 integrity and file SHA256 hashes. Refresh with `python scripts/update_vendor.py` after deliberately changing its explicit version pins; repeat browser checks.
