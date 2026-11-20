# Asset specifications

What each site needs to deliver, at what size and in what format, so the shared
tools can produce sharp output. The tools scale down but never usefully scale
up: a source smaller than the sizes below gives soft or small results.

Sources live in the site's `source/` folder and are tracked in git, so every
derived file can be rebuilt. Published derivatives live in `static/`. Each
site's `media.json` lists exactly which files are converted, to what size and
format, and where they go.

Two sites are exceptions. `frameorder.nl` keeps its image and poster sources in
`static/`, because `source/` is gitignored there apart from `icon.png` (the video
masters are too large for git). `lukaskrepel.nl` keeps its `source/images` and
most of `source/videos` tracked, but leaves the largest video masters out of git.

## How sources become published files

| Pattern                  | Originals                | Derivatives | Committed    |
| ------------------------ | ------------------------ | ----------- | ------------ |
| A: `source/` → `static/` | `source/`                | `static/`   | both         |
| B: rasters → `dist/`     | `static/` (or `source/`) | `dist/`     | sources only |

The jobs, widths, qualities, and formats live in the site's `media.json`; the
engine is `media.py`. Run `python3 _shared/media.py` after changing a source.

## Icons and sharing

These are built by the `favicon` and `share` jobs in the site's `media.json`
(see the README's "Icons and sharing convention").

| Source file        | Size                                       | Format                            | Produces                                                            |
| ------------------ | ------------------------------------------ | --------------------------------- | ------------------------------------------------------------------- |
| `source/icon.png`  | square, 1024×1024 (minimum 512×512)        | PNG with a transparent background | `static/favicons/` (16, 32, 180, 192, 512 px and a 16–64 px `.ico`) |
| `source/share.png` | logo: at least 1050 px wide or 480 px tall | PNG with a transparent background | `static/share.jpg`, 1200×630, logo centred on a colour              |
| `source/share.jpg` | still or poster: at least 1200×630         | JPG or PNG, full bleed            | `static/share.jpg`, 1200×630, scaled to fill and cropped evenly     |

**Icon artwork.** Crop to the artwork itself with no margin of your own:
`favicons.py` adds padding (3% for tab icons, 8% for app icons). Non-square
artwork is centred on a square canvas, so a wordmark gets very small; use the
mark or a character instead. Tab icons keep the transparency. The 180, 192 and
512 px app icons get an opaque background colour (`--background`), because iOS
shows transparent areas as black. Keep the details bold enough to read at 16 px.

**Share artwork.** Link previews show the image at 1200×630 (about 1.91:1) and
some apps crop it to a square in the middle, so keep the important part
centred. In contain mode (`ogimage.py`, the default) the logo gets a margin of
12% of the height on every side, so the usable area is about 1050×480; a
smaller logo is not enlarged and sits small in the middle. In cover mode
(`--fit cover`) the image fills the frame and the overflow is cut off evenly.
Pass `--size 1200x675` to keep finished 16:9 artwork uncropped. Text in a share
image must still be readable when the preview is shown at about 500 px wide.

**Page tags.** Declare the real output size with `og:image:width` and
`og:image:height` (1200 and 630 unless `--size` changed it) and describe the
image with `og:image:alt`.

## Page images

Images that `media.py` converts to WebP during the build, as listed in the
site's `media.json`.

| Kind                    | Size                                                                                                             | Format                               |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| photos, stills, artwork | at least 2× the largest width shown on the page, up to the `--max-width` the build passes (usually 1280–1600 px) | JPG for photos, PNG for flat artwork |
| logos and line art      | at least 2× the displayed width                                                                                  | PNG with a transparent background    |
| responsive images       | at least the largest `--widths` value (e.g. 1280 px for `--widths 640,960,1280`)                                 | JPG or PNG                           |
| hand-made WebP          | final size                                                                                                       | WebP (copied unchanged)              |

The 2× rule keeps images sharp on high-density screens. Sources wider than
`--max-width` are scaled down; narrower sources are never scaled up.

## App screenshots

`appshots.py` pastes raw captures into the shared phone border,
`phone-border.png` in this repository (2674×1316, transparent screen window at
290,70–2386,1248). Sites don't keep their own copy.

| File                                 | Size                                                                      | Format |
| ------------------------------------ | ------------------------------------------------------------------------- | ------ |
| `source/app-screenshots/<app>/*.png` | raw captures at the app's own resolution, 16:9 landscape (e.g. 2400×1350) | PNG    |

Captures are scaled to fit the 2096×1178 window, so anything 16:9 and at least
that size works. Name each capture after what it shows (`insects.png`,
`menu.png`); the output files keep those names.

## Fonts

Self-hosted fonts live in `static/fonts/<Family>/` with their licence file next
to them (`OFL.txt` for Google Fonts). Publish `.woff2` subsets only; keep the
full `.ttf`/`.otf` files in `source/fonts/` if you need them for editing.
