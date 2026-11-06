# site-tooling

Shared deployment tooling for static sites. It mirrors a build directory to an
FTP or SFTP host with `lftp`.

- `deploy.sh` — loads `.env`, validates credentials, normalises permissions and
  mirrors a build directory.
- `action.yml` — GitHub composite action that runs the same script in CI.
- `runs.sh` — prints recent Actions runs for a configured set of repositories.
- `sync.sh` — refreshes the vendored `_shared/` copies in local checkouts.
- `serve.sh` — serves a build directory for local preview.
- `appshots.py` — composites raw screenshots into a phone border and writes
  WebP files.

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

## Preview

`serve.sh` serves a build directory on `http://localhost:8000`:

```bash
_shared/serve.sh dist
_shared/serve.sh dist 8080
PORT=8080 _shared/serve.sh dist
```

## App screenshots

`appshots.py` composites raw screenshot captures into a phone-border image and
exports WebP files. Keep raw captures in `source/app-screenshots/<app>/` and
write the composited files into the published images folder, for example
`static/images/apps/<app>/` or `images/apps/<app>/`:

```bash
python3 -m pip install -r requirements.txt
python3 appshots.py \
  --border source/phone_border.png \
  --window 290,70,2386,1248 \
  --out static/images/apps/my-app \
  source/app-screenshots/my-app/*.png
```

`--window` is the screen rectangle inside the border (`x1,y1,x2,y2`). Files are
named after the input stems, so use meaningful names such as `insects.png`,
`bones.png`, and `menu.png`.

Use the same three-up fan everywhere:

```html
<div class="app-screenshots">
	<img
		src="images/apps/my-app/one.webp"
		alt=""
		class="app-shot"
		loading="lazy"
	/>
	<img
		src="images/apps/my-app/two.webp"
		alt=""
		class="app-shot"
		loading="lazy"
	/>
	<img
		src="images/apps/my-app/menu.webp"
		alt=""
		class="app-shot app-shot-wide"
		loading="lazy"
	/>
</div>
```

```css
.app-screenshots {
	position: relative;
	max-width: 500px;
	margin: 0 auto;
}
.app-shot {
	width: auto;
	max-width: 65%;
	height: auto;
	border-radius: 15px;
	position: relative;
	display: block;
}
.app-shot:first-child {
	z-index: 1;
}
.app-shot:nth-child(2) {
	max-width: 60%;
	margin-left: auto;
	margin-top: -120px;
	z-index: 2;
}
.app-shot-wide {
	max-width: 75%;
	margin: -80px auto 0;
	z-index: 3;
}
```

Adjust the negative margins for the site's breakpoints.

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
`apt-get install lftp` on Debian/Ubuntu. `appshots.py` also needs Pillow:
`python3 -m pip install -r requirements.txt`.

The password is passed to `lftp` through `LFTP_PASSWORD`, so it never appears in
the process list, on disk, or in a workflow log.
