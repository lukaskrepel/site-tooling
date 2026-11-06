# site-tooling

Shared deployment tooling for static sites. It mirrors a build directory to an
FTP or SFTP host with `lftp`.

- `deploy.sh` — loads `.env`, validates credentials, normalises permissions and
  mirrors a build directory.
- `action.yml` — GitHub composite action that runs the same script in CI.
- `runs.sh` — prints recent Actions runs for a configured set of repositories.
- `sync.sh` — refreshes the vendored `_shared/` copies in local checkouts.

## Configuration

Credentials are read from the environment or from `.env` in the current working
directory.

FTP:

```dotenv
FTP_HOST=ftp.example.com
FTP_USER=deploy
FTP_PASS=secret
FTP_PATH=/public_html
```

SFTP (port defaults to 22):

```dotenv
SFTP_HOST=sftp.example.com
SFTP_USER=deploy
SFTP_PASS=secret
SFTP_PATH=/var/www/example
```

Protocol is inferred from which variables are set: `SFTP_HOST` selects SFTP and
`FTP_HOST` selects FTP. Set `DEPLOY_PROTOCOL` or pass `--protocol` to override.

## Local usage

```bash
_shared/deploy.sh dist
_shared/deploy.sh public --protocol ftp
_shared/deploy.sh dist --lftp-option 'set net:timeout 30'
_shared/deploy.sh dist --dry-run
```

Start with `--dry-run` to print the resolved configuration and the `lftp`
commands without uploading anything.

## CI usage

Add the credentials as repository secrets and call this repository directly.
Using `@main` means every deployment runs the latest tooling, with no vendored
copy to keep in sync:

```yaml
- uses: your-account/site-tooling@main
  with:
    source: dist
    protocol: ftp
    host: ${{ secrets.FTP_HOST }}
    user: ${{ secrets.FTP_USER }}
    password: ${{ secrets.FTP_PASS }}
    path: ${{ secrets.FTP_PATH }}
```

Pin a tag or commit SHA instead of `main` if you prefer updates to be explicit.
For SFTP, use the `SFTP_*` secrets and `protocol: sftp`. Optional inputs are
`port`, `lftp-options`, and `skip-if-unconfigured`.

## Run feed

`runs.sh` prints recent GitHub Actions runs across several repositories.

```bash
cp .runs.env.example .runs.env   # .runs.env is gitignored
# edit GH_OWNER and REPOS
./runs.sh
./runs.sh -n 10
./runs.sh example.com example.org
```

`.runs.env` is read from the current directory or from next to `runs.sh`. It
holds your account and repository list, so it never enters this public
repository:

```dotenv
GH_OWNER=your-account
REPOS="example.com example.org"
```

Entries in `REPOS` may be bare repository names or full `owner/repo` slugs.
Requires `gh` with `gh auth login`.

## Updating local copies

CI runs this repository directly, so deployments never depend on a vendored
copy. The `_shared/` directory is only for local `./deploy.sh` runs. Refresh the
local copies with:

```bash
cp .sync.env.example .sync.env   # .sync.env is gitignored
# edit TOOLING_REPO and SITE_DIRS
./sync.sh
```

`sync.sh` runs `git subtree pull` in each configured checkout. It never pushes;
review and push the resulting commits when you are ready.

## Vendoring

`_shared/` is the local copy used by `./deploy.sh`; CI does not need it. Keep it
tracked with `git subtree` and do not edit it inside a site repository.

First time:

```bash
git subtree add --prefix _shared <tooling-repo-url> main --squash
```

Update:

```bash
git subtree pull --prefix _shared <tooling-repo-url> main --squash
```

If `_shared/` already exists as plain files, remove it first:

```bash
rm -rf _shared
git commit -m "Remove vendored deploy files"
git subtree add --prefix _shared <tooling-repo-url> main --squash
```

## Requirements

`bash` and `lftp`. Install `lftp` with `brew install lftp` on macOS or
`apt-get install lftp` on Debian/Ubuntu.

The password is passed to `lftp` through `LFTP_PASSWORD`, so it never appears in
the process list, on disk, or in a workflow log.
