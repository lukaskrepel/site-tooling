# site-tooling

Shared deployment tooling for static sites. It mirrors a build directory to an
FTP or SFTP host with `lftp`.

- `deploy.sh` — loads `.env`, validates credentials, normalises permissions and
  mirrors a build directory.
- `action.yml` — GitHub composite action that runs the same script in CI.
- `runs.sh` — prints recent Actions runs for a configured set of repositories.
- `sync.sh` — refreshes the vendored `_shared/` copies in local checkouts.
- `serve.sh` — serves a build directory for local preview.
- `cache-bust.py` — appends content hashes to local asset URLs in a build directory.
- `imgopt.py` — generates resized WebP/JPEG derivatives from JPG/PNG sources.
- `appshots.py` — composites raw screenshots into the shared phone border
  (`phone-border.png`) and writes
  WebP files.
- `favicons.py` — generates a favicon and app-icon set from one source image.
- `ogimage.py` — generates a 1200×630 social share image from a logo or still.

See [ASSETS.md](ASSETS.md) for the source files each site needs, with sizes
and formats.

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
_shared/deploy.sh dist --exclude 'share/'   # leave remote share/ alone
_shared/deploy.sh dist --dry-run
```

Start with `--dry-run` to print the resolved configuration and the `lftp`
commands without uploading anything.

The mirror compares file sizes because FTP timestamps are unreliable, then
re-uploads HTML, CSS, JS, and other small text assets on every deploy so an
edit that keeps the same byte length is not skipped. Media files are only
uploaded when their size changes.

## Preview

`serve.sh` serves a build directory on `http://localhost:8000`:

```bash
_shared/serve.sh dist
_shared/serve.sh dist 8080
PORT=8080 _shared/serve.sh dist
```

## Cache busting

`cache-bust.py` appends `?v=<content-hash>` to local CSS, JS, image, and font
URLs in a build directory. It handles `href`, `src`, `poster`, asset `data-*`
attributes, and `srcset` in HTML, `url(...)` references in CSS, and icon paths
in `.webmanifest` files. Run it after the build, before deploying:

```bash
python3 _shared/cache-bust.py dist
```

The default directory is `dist`. Unchanged files keep their URL and their cache;
changed files get a new URL. Serve HTML with `Cache-Control: no-cache` so
browsers pick up new asset URLs immediately.

## Image optimisation

`imgopt.py` reads raster sources (JPG/PNG) and writes resized, compressed WebP
or JPEG files into a build directory. The source folder name and relative path
are kept, so `--src static/images --out dist` writes `dist/images/...`.
Reference mode only converts files the pages actually use:

```bash
python3 _shared/imgopt.py --src static/images --out dist \
  --refs template.html static/styles.css
```

Explicit mode converts a folder, optionally filtered by glob:

```bash
python3 _shared/imgopt.py --src static/videos --out dist --match '*.jpg' \
  --max-width 1280 --quality 80 --prune-source --cache .cache/imgopt
```

- `--max-width` downscales wider sources and never upscales.
- `--widths 640,960` also writes `<name>-640.webp` and `<name>-960.webp` for
  `srcset`; the base file keeps the plain name.
- `--prune-source` deletes the original that the site build copied into the
  output tree. Use it when only the derivative is published; leave it off when
  a `<picture>` fallback still points at the original.
- `--cache` reuses encoded files between builds, so a wiped `dist/` does not
  re-encode every asset. Add the cache directory to the site's `.gitignore`.
- Reference mode fails when a referenced asset has no matching source, which
  catches typos in `template.html` and `styles.css`.

Output is WebP at quality 82 by default. `--format jpeg` re-encodes to JPEG
instead, with a white background for transparent areas. `--method 0-6` sets the
WebP effort; the default of 4 is much faster than 6 for a marginal size
difference.

Hand-authored `.webp` files in a source folder are copied through unchanged.
In GitHub Actions, install Pillow in the build job (`actions/setup-python`
followed by `pip install -r _shared/requirements.txt`) before running the
build script.

## App screenshots

`appshots.py` composites raw screenshot captures into the shared phone border
and exports WebP files. Every site uses the same border, `phone-border.png` in
this repository (so `_shared/phone-border.png` in a site); do not keep a copy in
a site's `source/`. Keep raw captures in `source/app-screenshots/<app>/` and
write the composited files into the published images folder, for example
`static/images/apps/<app>/`:

```bash
python3 -m pip install -r requirements.txt
python3 _shared/appshots.py \
  --out static/images/apps/my-app \
  source/app-screenshots/my-app/*.png
```

The border's screen window is built in (`290,70,2386,1248`). `--border` and
`--window` exist only to try out a different frame; change the shared file
instead so every site stays the same. Files are named after the input stems,
so use meaningful names such as `insects.png`, `bones.png`, and `menu.png`.

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
Using `@main` means the deploy step always runs the latest `deploy.sh`:

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
`port`, `lftp-options`, `exclude`, and `skip-if-unconfigured`.

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

The CI deploy step runs this repository directly, but site builds call the
vendored Python tools (`_shared/cache-bust.py`, `_shared/imgopt.py`) both
locally and in CI, and CI installs `_shared/requirements.txt`. Keep every copy
current. Refresh them with:

```bash
cp .sync.env.example .sync.env   # .sync.env is gitignored
# edit TOOLING_REPO and SITE_DIRS
./sync.sh
```

`sync.sh` runs `git subtree pull` in each configured checkout. It never pushes;
review and push the resulting commits when you are ready.

## Favicons

`favicons.py` turns one source image into the standard favicon and app-icon
set. The artwork keeps its aspect ratio and is centred on a square canvas, so
portrait or landscape sources work without distortion.

```bash
python3 favicons.py source/icon.png --out static/images
python3 favicons.py source/icon.png --out static/favicons --background '#f7f1e7'
```

It writes `favicon-16x16.png`, `favicon-32x32.png`, `favicon.ico` (16, 32, 48,
and 64 px), `apple-touch-icon.png`, `android-chrome-192x192.png`, and
`android-chrome-512x512.png`.

The tab icons keep a transparent background. The larger app icons use an opaque
background (white by default) because iOS renders transparency as black. Set
`--background transparent` to keep them transparent, adjust the app-icon margin
with `--padding` (default `0.08`), or write only the tab icons with
`--no-app-icons`.

## Share images

`ogimage.py` writes the JPEG that link previews show (`og:image`). Contain mode
centres a logo on a solid colour and never upscales it; cover mode fills the
frame with a still or poster and crops the overflow evenly:

```bash
python3 ogimage.py source/share.png --out static/share.jpg --background '#ffe200'
python3 ogimage.py source/poster.png --out static/share.jpg --fit cover
```

The default size is 1200×630; `--size 1200x675` keeps a 16:9 artwork intact.
`--padding` sets the contain-mode margin as a fraction of the height (default
`0.12`).

## Icons and sharing convention

Every site keeps the inputs and the exact commands in the repository, so the
icons and share image can be rebuilt at any time. [ASSETS.md](ASSETS.md) lists
the sizes and formats the sources need:

- `source/icon.png` (or `.jpg`) — the favicon artwork, tracked in git.
- `source/share.png` (or `.jpg`) — the share artwork, tracked in git.
- `scripts/icons.sh` — runs `favicons.py` into `static/favicons/` and
  `ogimage.py` into `static/share.jpg`, with the site's colours and padding.
- `static/.htaccess` redirects `/favicon.ico` to `/favicons/favicon.ico`,
  because browsers and crawlers request the root path regardless of the HTML.
- The page head links `favicons/favicon.ico` (`sizes="any"`), the 32 and 16 px
  PNGs, `apple-touch-icon.png` and `site.webmanifest`, and sets `og:image` with
  `og:image:width`, `og:image:height` and `og:image:alt`, plus
  `twitter:card` `summary_large_image` and a canonical URL.
- `static/site.webmanifest` lists `/favicons/android-chrome-192x192.png` and
  `-512x512.png` with the same `theme_color` as the page.

## Vendoring

`_shared/` is the copy used by `./deploy.sh` and by the build scripts, locally
and in CI. Keep it tracked with `git subtree` and do not edit it inside a site
repository. `sync.sh` only works on copies added with `git subtree add`.

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
`apt-get install lftp` on Debian/Ubuntu. `appshots.py`, `favicons.py`,
`imgopt.py`, and `ogimage.py` also need Pillow: `python3 -m pip install -r requirements.txt`.

The password is passed to `lftp` through `LFTP_PASSWORD`, so it never appears in
the process list, on disk, or in a workflow log.
