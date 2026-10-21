# SPDX-License-Identifier: AGPL-3.0-or-later
import json

import pytest

from git_deploy import protocol

SECRET = "s3cret"
NOW = 1_800_000_000
SHA = "a" * 40
APPS = frozenset({"zephyrex_inventory"})
REFS = frozenset({"refs/heads/main"})


def _request(**overrides):
	fields = {"app": "zephyrex_inventory", "sha": SHA, "ref": "refs/heads/main", "timestamp": NOW} | overrides
	return protocol.DeployRequest(**fields)


def _verify(body, signature=None, secret=SECRET, now=NOW):
	sig = protocol.sign(body, SECRET) if signature is None else signature
	return protocol.verify(body, sig, secret, now, APPS, REFS)


def test_accepts_a_signed_request():
	request = _request()
	assert _verify(request.body()) == request


def test_body_is_canonical_json():
	assert json.loads(_request().body()) == {
		"app": "zephyrex_inventory",
		"ref": "refs/heads/main",
		"sha": SHA,
		"timestamp": NOW,
	}
	assert _request().body() == _request().body()


@pytest.mark.parametrize(
	("body", "signature", "secret", "now"),
	[
		(_request().body(), "sha256=" + "0" * 64, SECRET, NOW),  # wrong signature
		(_request().body(), "", SECRET, NOW),  # missing signature
		(_request().body(), None, "", NOW),  # no secret configured
		(_request().body(), None, SECRET, NOW + protocol.MAX_CLOCK_SKEW_S + 1),  # replayed later
		(_request().body(), None, SECRET, NOW - protocol.MAX_CLOCK_SKEW_S - 1),  # from the future
		(_request(app="frappe").body(), None, SECRET, NOW),  # app not allowed
		(_request(sha="abc123").body(), None, SECRET, NOW),  # short sha
		(_request(ref="refs/heads/dev").body(), None, SECRET, NOW),  # other branch
		(b"not json", None, SECRET, NOW),
		(b"[]", None, SECRET, NOW),
		(b"x" * (protocol.MAX_BODY_BYTES + 1), None, SECRET, NOW),
	],
)
def test_rejects(body, signature, secret, now):
	with pytest.raises(protocol.DeployRejected):
		_verify(body, signature, secret, now)


def test_rejects_a_body_changed_after_signing():
	signature = protocol.sign(_request().body(), SECRET)
	with pytest.raises(protocol.DeployRejected):
		_verify(_request(sha="b" * 40).body(), signature)


def test_rejects_a_boolean_timestamp():
	body = json.dumps(
		{"app": "zephyrex_inventory", "sha": SHA, "ref": "refs/heads/main", "timestamp": True}
	).encode()
	with pytest.raises(protocol.DeployRejected):
		protocol.verify(body, protocol.sign(body, SECRET), SECRET, 1, APPS, REFS)
