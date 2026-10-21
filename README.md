<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# frappe-git-deploy

Deploys a Frappe app to a site whenever CI pushes to its branch, over the site's own public HTTPS. No
inbound SSH, and no runner on the site's network.

1. **CI** (`.github/workflows/deploy.yml`, reusable) signs `{app, sha, ref, timestamp}` with
   HMAC-SHA256 and posts it to `/api/method/git_deploy.api.deploy`.
2. **The site** (this app) checks the signature in constant time, plus the app, branch, full SHA and
   clock skew. It only writes a request file. It runs nothing and holds no privilege.
3. **The host's root service** is started by a systemd path unit and installed by the erpnext stack
   in [tofu-providers](https://github.com/JamesonRGrieve/tofu-providers). It keeps its own app
   allow-list and checks the commit is on the branch. It then backs up the site, moves the checkout,
   installs, builds, migrates and restarts, and checks the site answers. On any failure it restores
   the previous commit and the backup.
4. **CI** polls `/api/method/git_deploy.api.status?app=<app>` until the site reports its commit as
   `succeeded`. A failure, a rollback or a timeout fails the job.

## Using it from an app repo

```yaml
on:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps: [...]
  deploy:
    needs: test
    uses: JamesonRGrieve/frappe-git-deploy/.github/workflows/deploy.yml@main
    with:
      site_url: https://dev-erp.example
      app: my_app
    secrets:
      GIT_DEPLOY_SECRET: ${{ secrets.GIT_DEPLOY_SECRET }}
```

The site's **Git Deploy Settings** (written by the erpnext stack) hold the enabled flag, the branch,
the allowed apps and the webhook secret.

## Tests

`uv run --no-project --python 3.14 --with pytest python -I -m pytest`, plus
`uvx ruff format --check . && uvx ruff check .`.
