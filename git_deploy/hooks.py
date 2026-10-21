# SPDX-License-Identifier: AGPL-3.0-or-later
from . import __version__ as _version

app_name = "git_deploy"
app_title = "Git Deploy"
app_publisher = "Zephyrex Technologies Limited"
app_description = "Deploy Frappe apps to a site when CI pushes to their branch: a signed webhook queues the deploy, a root service on the host runs it"
app_email = "jameson@zephyrex.ca"
app_license = "AGPL-3.0-or-later"
app_version = _version

required_apps = ["frappe"]
