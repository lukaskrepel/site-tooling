# site-tooling

Shared deployment tooling for static sites. It mirrors a build directory to an
FTP or SFTP host with `lftp`.

- `deploy.sh` — loads `.env`, validates credentials, normalises permissions and
  mirrors a build directory.
- `action.yml` — GitHub composite action that runs the same script in CI.

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

Add the credentials as repository secrets and call the vendored action:

```yaml
- uses: ./_shared
  with:
    source: dist
    protocol: ftp
    host: ${{ secrets.FTP_HOST }}
    user: ${{ secrets.FTP_USER }}
    password: ${{ secrets.FTP_PASS }}
    path: ${{ secrets.FTP_PATH }}
```

For SFTP, use the `SFTP_*` secrets and `protocol: sftp`. Optional inputs are
`port`, `lftp-options`, and `skip-if-unconfigured`.

## Vendoring

Keep this repository in each site repository as `_shared/` with `git subtree`.
Do not edit `_shared/` in a site repository; change this repository and pull the
update down.

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
