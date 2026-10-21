# frappe-git-deploy — Agent Operating Guide

AGPL-3.0-or-later Frappe v16 app: the site half of push-to-deploy. The host half (root deploy
service, path unit, directories, settings) lives in tofu-providers'
`opentofu/zephyrex/modules/services/stacks/erpnext/git_deploy.tf` and `files/frappe_git_deploy.py`.
Keep the two in step: the request and status paths in `queue.py` are hard-coded on both sides.

## Trust boundaries

- **The web process never runs a command and never gains privilege.** `api.deploy` verifies, then
  writes `/var/lib/frappe-git-deploy/requests/<app>.json`. Nothing else.
- **The root service trusts nothing the frappe user wrote.** It re-validates the app against its own
  allow-list (unit environment, from the stack), requires a full SHA reachable from the branch, and
  never follows a symlink. Status files are root-owned. Backups and bench commands run as frappe.
- **Signatures:** HMAC-SHA256 over the exact body, compared with `hmac.compare_digest`. A timestamp
  window (`MAX_CLOCK_SKEW_S`) stops an old signed body from rolling a site back later.

## Code

- `protocol.py`, `queue.py`, `client.py`: pure, no Frappe import, unit-tested in `tests/`. `client.py`
  is standard library only, so CI needs nothing installed.
- `api.py`: the two guest endpoints, rate-limited.
- `Git Deploy Settings` (Single): enabled, branch, apps, webhook_secret (Password).

## Testing

`uv run --no-project --python 3.14 --with pytest python -I -m pytest`;
lint `uvx ruff format --check . && uvx ruff check .`.
