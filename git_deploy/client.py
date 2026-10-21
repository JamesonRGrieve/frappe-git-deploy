# SPDX-License-Identifier: AGPL-3.0-or-later
"""CI side: sign and send a deploy request, then wait for the host service to finish it.

    GIT_DEPLOY_SECRET=... python -m git_deploy.client <site-url> <app> <sha> <ref>

Standard library only, so a CI runner needs nothing installed. Exits 0 only when the site reports
the pushed commit as succeeded; a failure, a rollback or no answer within the wait fails the job."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from git_deploy import protocol, queue

logger = logging.getLogger("git_deploy.client")

REQUEST_TIMEOUT_S = 30
POLL_INTERVAL_S = 10
DEPLOY_WAIT_S = 1800
DEPLOY_METHOD = "/api/method/git_deploy.api.deploy"
STATUS_METHOD = "/api/method/git_deploy.api.status"
# Cloudflare's bot rules refuse urllib's default agent.
USER_AGENT = "Mozilla/5.0 (compatible; frappe-git-deploy)"


@dataclass(frozen=True)
class DeployClient:
	site_url: str
	secret: str

	def _open(self, req: urllib.request.Request) -> dict[str, object]:
		req.add_header("User-Agent", USER_AGENT)
		req.add_header("Accept", "application/json")
		with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as r:
			message = json.loads(r.read()).get("message", {})
		return message if isinstance(message, dict) else {}

	def request_deploy(self, request: protocol.DeployRequest) -> dict[str, object]:
		body = request.body()
		req = urllib.request.Request(self.site_url.rstrip("/") + DEPLOY_METHOD, data=body, method="POST")
		req.add_header("Content-Type", "application/json")
		req.add_header(protocol.SIGNATURE_HEADER, protocol.sign(body, self.secret))
		return self._open(req)

	def status(self, app: str) -> dict[str, object]:
		query = urllib.parse.urlencode({"app": app})
		return self._open(urllib.request.Request(f"{self.site_url.rstrip('/')}{STATUS_METHOD}?{query}"))

	def wait(self, app: str, sha: str, deadline: float) -> dict[str, object]:
		while time.monotonic() < deadline:
			try:
				current = self.status(app)
			except (urllib.error.URLError, TimeoutError, ValueError) as e:
				logger.warning("status poll failed: %s", e)
				current = {}
			if current.get("sha") == sha and current.get("state") in queue.FINAL_STATES:
				return current
			time.sleep(POLL_INTERVAL_S)
		return {"app": app, "sha": sha, "state": "timeout"}


def main(argv: list[str]) -> int:
	logging.basicConfig(level=logging.INFO, format="%(message)s")
	site_url, app, sha, ref = argv
	client = DeployClient(site_url=site_url, secret=os.environ["GIT_DEPLOY_SECRET"])
	request = protocol.DeployRequest(app=app, sha=sha, ref=ref, timestamp=int(time.time()))
	logger.info("queued: %s", client.request_deploy(request))
	result = client.wait(app, sha, time.monotonic() + DEPLOY_WAIT_S)
	logger.info("result: %s", result)
	return 0 if result.get("state") == queue.SUCCEEDED else 1


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
