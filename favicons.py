#!/usr/bin/env python3
"""Generate a favicon and app-icon set from one source image.

The source can be any size; portrait or landscape artwork is centred on a
square canvas without distortion. Tab icons stay transparent, while the larger
app icons get an opaque background by default because iOS renders transparent
areas as black.

Usage:
    favicons.py source/icon.png --out static/images
    favicons.py source/icon.png --out static/favicons --background '#f7f1e7'
    favicons.py source/icon.png --out static/images --no-app-icons

Writes favicon-16x16.png, favicon-32x32.png, favicon.ico, apple-touch-icon.png,
android-chrome-192x192.png, and android-chrome-512x512.png.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print(
        "Pillow is required: python3 -m pip install -r requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(1)


FAVICON_SIZES = (16, 32)
ICO_SIZES = ((16, 16), (32, 32), (48, 48), (64, 64))
APP_ICON_SIZES = (180, 192, 512)


def parse_color(value: str) -> tuple[int, int, int, int]:
    value = value.strip().lower()
    if value in ("transparent", "none"):
        return (0, 0, 0, 0)
    if value.startswith("#"):
        value = value[1:]
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    if len(value) != 6:
        raise argparse.ArgumentTypeError("expected #rgb, #rrggbb, or transparent")
    try:
        red, green, blue = (int(value[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        raise argparse.ArgumentTypeError("expected #rgb, #rrggbb, or transparent")
    return (red, green, blue, 255)


def parse_padding(value: str) -> float:
    padding = float(value)
    if not 0 <= padding < 0.5:
        raise argparse.ArgumentTypeError("expected a value from 0 up to 0.5")
    return padding


def render(
    source: Image.Image,
    size: int,
    background: tuple[int, int, int, int],
    padding: float,
) -> Image.Image:
    inner = max(1, round(size * (1 - 2 * padding)))
    scale = min(inner / source.width, inner / source.height)
    width = max(1, round(source.width * scale))
    height = max(1, round(source.height * scale))
    artwork = source.resize((width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), background)
    canvas.alpha_composite(artwork, ((size - width) // 2, (size - height) // 2))
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate favicon and app-icon files from one source image."
    )
    parser.add_argument("source", type=Path, help="source image (PNG recommended)")
    parser.add_argument(
        "--out", type=Path, default=Path("static/images"), help="output directory"
    )
    parser.add_argument(
        "--background",
        type=parse_color,
        default=parse_color("#ffffff"),
        metavar="COLOUR",
        help="app-icon background (#rgb, #rrggbb, or transparent; default: #ffffff)",
    )
    parser.add_argument(
        "--padding",
        type=parse_padding,
        default=0.08,
        metavar="FRACTION",
        help="margin around the app-icon artwork (default: 0.08)",
    )
    parser.add_argument(
        "--favicon-padding",
        type=parse_padding,
        default=0.03,
        metavar="FRACTION",
        help="margin around the tab-icon artwork (default: 0.03)",
    )
    parser.add_argument(
        "--no-app-icons",
        action="store_true",
        help="only write the tab icons (16, 32, and ICO)",
    )
    args = parser.parse_args()

    try:
        source = Image.open(args.source).convert("RGBA")
    except OSError as error:
        parser.error(f"could not open {args.source}: {error}")

    args.out.mkdir(parents=True, exist_ok=True)
    written: list[tuple[Path, str]] = []

    for size in FAVICON_SIZES:
        path = args.out / f"favicon-{size}x{size}.png"
        render(source, size, (0, 0, 0, 0), args.favicon_padding).save(path)
        written.append((path, f"{size}×{size}"))

    ico_path = args.out / "favicon.ico"
    render(source, 256, (0, 0, 0, 0), args.favicon_padding).save(
        ico_path, sizes=list(ICO_SIZES)
    )
    written.append((ico_path, ", ".join(f"{w}×{h}" for w, h in ICO_SIZES)))

    if not args.no_app_icons:
        names = {
            180: "apple-touch-icon.png",
            192: "android-chrome-192x192.png",
            512: "android-chrome-512x512.png",
        }
        for size in APP_ICON_SIZES:
            path = args.out / names[size]
            render(source, size, args.background, args.padding).save(path)
            written.append((path, f"{size}×{size}"))

    for path, detail in written:
        print(f"✓ {path} ({detail})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
