# SPDX-License-Identifier: AGPL-3.0-or-later
import json

from git_deploy import protocol, queue


def _request(sha):
	return protocol.DeployRequest(app="zephyrex_inventory", sha=sha, ref="refs/heads/main", timestamp=1)


def test_write_request_replaces_the_pending_one(tmp_path):
	queue.write_request(_request("a" * 40), tmp_path)
	path = queue.write_request(_request("b" * 40), tmp_path)
	assert path == tmp_path / "zephyrex_inventory.json"
	assert json.loads(path.read_text()) == {"sha": "b" * 40, "ref": "refs/heads/main", "requested_at": 1}
	assert [p.name for p in tmp_path.iterdir()] == ["zephyrex_inventory.json"]


def test_read_status(tmp_path):
	assert queue.read_status("zephyrex_inventory", tmp_path) is None
	(tmp_path / "zephyrex_inventory.json").write_text(
		json.dumps({"sha": "a" * 40, "state": queue.SUCCEEDED, "detail": "", "updated_at": 5})
	)
	status = queue.read_status("zephyrex_inventory", tmp_path)
	assert status == queue.DeployStatus("zephyrex_inventory", "a" * 40, queue.SUCCEEDED, "", 5)
	assert status.as_dict()["state"] == queue.SUCCEEDED
