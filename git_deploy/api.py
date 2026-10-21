# SPDX-License-Identifier: AGPL-3.0-or-later
"""Guest endpoints CI calls: ``deploy`` queues a signed request, ``status`` reports the host service's
progress. Neither runs anything: the root deploy service on the host does the work."""

from __future__ import annotations

import logging
import time

import frappe
from frappe.rate_limiter import rate_limit

from git_deploy import protocol, queue

logger = logging.getLogger(__name__)

SETTINGS = "Git Deploy Settings"
RATE_LIMIT_CALLS = 30
RATE_LIMIT_WINDOW_S = 60
REJECTED = "Deploy request rejected"


def _settings() -> tuple[str, frozenset[str], frozenset[str]]:
	settings = frappe.get_cached_doc(SETTINGS)
	if not settings.enabled:
		return "", frozenset(), frozenset()
	secret = settings.get_password("webhook_secret", raise_exception=False) or ""
	installed = set(frappe.get_installed_apps())
	apps = frozenset(a for a in settings.allowed_apps() if a in installed)
	return secret, apps, frozenset({f"refs/heads/{settings.branch or 'main'}"})


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=RATE_LIMIT_CALLS, seconds=RATE_LIMIT_WINDOW_S)
def deploy() -> dict[str, str]:
	secret, apps, refs = _settings()
	body = frappe.request.get_data(cache=True)
	try:
		request = protocol.verify(
			body, frappe.get_request_header(protocol.SIGNATURE_HEADER), secret, time.time(), apps, refs
		)
	except protocol.DeployRejected as e:
		logger.warning("git deploy rejected: %s", e)
		raise frappe.PermissionError(REJECTED) from e
	queue.write_request(request)
	logger.info("git deploy queued: %s @ %s", request.app, request.sha)
	frappe.local.response.http_status_code = 202
	return {"app": request.app, "sha": request.sha, "state": queue.QUEUED}


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=RATE_LIMIT_CALLS, seconds=RATE_LIMIT_WINDOW_S)
def status(app: str) -> dict[str, str | int]:
	_, apps, _ = _settings()
	if app not in apps:
		raise frappe.DoesNotExistError
	current = queue.read_status(app)
	return current.as_dict() if current else {"app": app, "state": ""}
