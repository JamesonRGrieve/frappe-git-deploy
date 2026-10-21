# SPDX-License-Identifier: AGPL-3.0-or-later
"""The signed deploy request: what CI sends and what the site accepts. Pure, no Frappe import.

The body is JSON {app, sha, ref, timestamp}; the signature header is ``sha256=<hex>``, the HMAC-SHA256
of the exact body bytes under the shared secret. A request is accepted only for an allowed app and
ref, with a full commit SHA, inside the clock-skew window (an old signed body can't roll a site back
later)."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass

SIGNATURE_HEADER = "X-Git-Deploy-Signature"
SIGNATURE_PREFIX = "sha256="
MAX_BODY_BYTES = 4096
MAX_CLOCK_SKEW_S = 300
APP_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


class DeployRejected(ValueError):
	"""The request is not acceptable. The message is for the server log, never the caller."""


@dataclass(frozen=True)
class DeployRequest:
	app: str
	sha: str
	ref: str
	timestamp: int

	def body(self) -> bytes:
		return json.dumps(
			{"app": self.app, "sha": self.sha, "ref": self.ref, "timestamp": self.timestamp},
			separators=(",", ":"),
			sort_keys=True,
		).encode()


def sign(body: bytes, secret: str) -> str:
	return SIGNATURE_PREFIX + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify(
	body: bytes,
	signature: str | None,
	secret: str,
	now: float,
	allowed_apps: frozenset[str],
	allowed_refs: frozenset[str],
) -> DeployRequest:
	if not secret:
		raise DeployRejected("no webhook secret is configured")
	if len(body) > MAX_BODY_BYTES:
		raise DeployRejected("body too large")
	if not signature or not hmac.compare_digest(sign(body, secret), signature):
		raise DeployRejected("bad signature")
	try:
		data = json.loads(body)
	except ValueError as e:
		raise DeployRejected("body is not JSON") from e
	if not isinstance(data, dict):
		raise DeployRejected("body is not an object")
	app, sha, ref, timestamp = data.get("app"), data.get("sha"), data.get("ref"), data.get("timestamp")
	if not isinstance(app, str) or not APP_NAME.match(app) or app not in allowed_apps:
		raise DeployRejected(f"app not allowed: {app!r}")
	if not isinstance(sha, str) or not FULL_SHA.match(sha):
		raise DeployRejected("sha is not a full commit SHA")
	if not isinstance(ref, str) or ref not in allowed_refs:
		raise DeployRejected(f"ref not allowed: {ref!r}")
	if (
		not isinstance(timestamp, int)
		or isinstance(timestamp, bool)
		or abs(now - timestamp) > MAX_CLOCK_SKEW_S
	):
		raise DeployRejected("timestamp outside the allowed window")
	return DeployRequest(app=app, sha=sha, ref=ref, timestamp=timestamp)
