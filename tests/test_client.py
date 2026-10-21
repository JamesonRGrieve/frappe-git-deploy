# SPDX-License-Identifier: AGPL-3.0-or-later
"""The CI client against a real local HTTP server standing in for the site's two endpoints."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from git_deploy import client, protocol, queue

SECRET = "s3cret"
SHA = "c" * 40


class FakeSite(BaseHTTPRequestHandler):
	received: list[tuple[bytes, str | None]] = []
	statuses: list[dict[str, object]] = []

	def _reply(self, message):
		body = json.dumps({"message": message}).encode()
		self.send_response(200)
		self.send_header("Content-Type", "application/json")
		self.end_headers()
		self.wfile.write(body)

	def do_POST(self):
		body = self.rfile.read(int(self.headers["Content-Length"]))
		FakeSite.received.append((body, self.headers.get(protocol.SIGNATURE_HEADER)))
		self._reply({"state": queue.QUEUED})

	def do_GET(self):
		self._reply(FakeSite.statuses.pop(0) if len(FakeSite.statuses) > 1 else FakeSite.statuses[0])

	def log_message(self, *args):
		pass


@pytest.fixture
def site(monkeypatch):
	monkeypatch.setattr(client, "POLL_INTERVAL_S", 0)
	FakeSite.received = []
	server = ThreadingHTTPServer(("127.0.0.1", 0), FakeSite)
	thread = threading.Thread(target=server.serve_forever, daemon=True)
	thread.start()
	yield f"http://127.0.0.1:{server.server_address[1]}"
	server.shutdown()


def test_request_is_signed_so_the_site_accepts_it(site):
	FakeSite.statuses = [{"sha": SHA, "state": queue.SUCCEEDED}]
	request = protocol.DeployRequest(
		app="zephyrex_inventory", sha=SHA, ref="refs/heads/main", timestamp=int(time.time())
	)
	client.DeployClient(site, SECRET).request_deploy(request)
	body, signature = FakeSite.received[0]
	assert (
		protocol.verify(
			body,
			signature,
			SECRET,
			time.time(),
			frozenset({"zephyrex_inventory"}),
			frozenset({"refs/heads/main"}),
		)
		== request
	)


def test_wait_skips_the_previous_deploy_until_its_own_finishes(site):
	FakeSite.statuses = [
		{"sha": "0" * 40, "state": queue.SUCCEEDED},
		{"sha": SHA, "state": queue.RUNNING},
		{"sha": SHA, "state": queue.ROLLED_BACK},
	]
	result = client.DeployClient(site, SECRET).wait("zephyrex_inventory", SHA, time.monotonic() + 5)
	assert result["state"] == queue.ROLLED_BACK


def test_wait_times_out(site):
	FakeSite.statuses = [{"sha": "0" * 40, "state": queue.SUCCEEDED}]
	result = client.DeployClient(site, SECRET).wait("zephyrex_inventory", SHA, time.monotonic() + 0.2)
	assert result["state"] == "timeout"


def test_main_exit_code_follows_the_result(site, monkeypatch):
	monkeypatch.setenv("GIT_DEPLOY_SECRET", SECRET)
	FakeSite.statuses = [{"sha": SHA, "state": queue.SUCCEEDED}]
	assert client.main([site, "zephyrex_inventory", SHA, "refs/heads/main"]) == 0
	FakeSite.statuses = [{"sha": SHA, "state": queue.FAILED}]
	assert client.main([site, "zephyrex_inventory", SHA, "refs/heads/main"]) == 1
