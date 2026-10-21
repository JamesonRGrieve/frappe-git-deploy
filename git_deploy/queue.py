# SPDX-License-Identifier: AGPL-3.0-or-later
"""The hand-off between the site and the host's deploy service. Pure filesystem, no Frappe import.

The site (as the frappe user) writes one request file per app, ``<REQUEST_DIR>/<app>.json``; a systemd
path unit sees it and the root deploy service consumes it. The service reports back through
``<STATUS_DIR>/<app>.json``, which only root can write. Both directories are created on the host by
the erpnext stack, which hard-codes the same paths."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from git_deploy.protocol import DeployRequest

REQUEST_DIR = Path("/var/lib/frappe-git-deploy/requests")
STATUS_DIR = Path("/var/lib/frappe-git-deploy/status")
MAX_STATUS_BYTES = 8192

# Deploy states written by the host service, in order; the last three are final.
QUEUED, RUNNING, SUCCEEDED, FAILED, ROLLED_BACK = "queued", "running", "succeeded", "failed", "rolled_back"
FINAL_STATES = frozenset({SUCCEEDED, FAILED, ROLLED_BACK})


@dataclass(frozen=True)
class DeployStatus:
	app: str
	sha: str
	state: str
	detail: str
	updated_at: int

	def as_dict(self) -> dict[str, str | int]:
		return {
			"app": self.app,
			"sha": self.sha,
			"state": self.state,
			"detail": self.detail,
			"updated_at": self.updated_at,
		}


def write_request(request: DeployRequest, request_dir: Path = REQUEST_DIR) -> Path:
	"""Atomically replace the app's pending request, so the service never reads a half-written file and a
	newer push supersedes one not yet started."""
	target = request_dir / f"{request.app}.json"
	payload = json.dumps({"sha": request.sha, "ref": request.ref, "requested_at": request.timestamp})
	fd, tmp = tempfile.mkstemp(dir=request_dir, prefix=f".{request.app}.", suffix=".tmp")
	try:
		with os.fdopen(fd, "w") as f:
			f.write(payload)
		os.replace(tmp, target)
	except BaseException:
		Path(tmp).unlink(missing_ok=True)
		raise
	return target


def read_status(app: str, status_dir: Path = STATUS_DIR) -> DeployStatus | None:
	path = status_dir / f"{app}.json"
	try:
		raw = path.read_bytes()[:MAX_STATUS_BYTES]
	except FileNotFoundError:
		return None
	data = json.loads(raw)
	return DeployStatus(
		app=app,
		sha=str(data.get("sha", "")),
		state=str(data.get("state", "")),
		detail=str(data.get("detail", "")),
		updated_at=int(data.get("updated_at", 0)),
	)
