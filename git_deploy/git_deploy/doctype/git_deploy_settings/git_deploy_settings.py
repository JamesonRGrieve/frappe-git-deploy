# SPDX-License-Identifier: AGPL-3.0-or-later
import frappe
from frappe import _
from frappe.model.document import Document

from git_deploy import protocol


class GitDeploySettings(Document):
	def validate(self):
		bad = [a for a in self.allowed_apps() if not protocol.APP_NAME.match(a)]
		if bad:
			frappe.throw(_("Not an app name: {0}").format(", ".join(bad)))

	def allowed_apps(self) -> tuple[str, ...]:
		return tuple(line.strip() for line in (self.apps or "").splitlines() if line.strip())
