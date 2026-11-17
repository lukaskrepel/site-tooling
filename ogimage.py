#!/usr/bin/env python3
"""Generate a social share image (og:image) from one source image.

Contain mode (the default) centres a logo or artwork on a solid background,
for sites whose share image is their logo. Cover mode scales a full-bleed
picture to fill the frame and crops the overflow evenly, for sites that share
a still or poster.

Usage:
    ogimage.py source/share.png --out static/share.jpg --background '#ffe200'
    ogimage.py source/poster.png --out static/share.jpg --fit cover
    ogimage.py source/share.jpg --out static/share.jpg --fit cover --size 1200x675

Writes a JPEG (1200×630 by default, the size Facebook, LinkedIn, X and
WhatsApp all render as a large preview).
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


def parse_color(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#").lower()
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    if len(value) != 6:
        raise argparse.ArgumentTypeError("expected #rgb or #rrggbb")
    try:
        return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        raise argparse.ArgumentTypeError("expected #rgb or #rrggbb")


def parse_size(value: str) -> tuple[int, int]:
    try:
        width, height = (int(part) for part in value.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError("expected WIDTHxHEIGHT, e.g. 1200x630")
    if width < 1 or height < 1:
        raise argparse.ArgumentTypeError("expected a positive size")
    return width, height


def parse_padding(value: str) -> float:
    padding = float(value)
    if not 0 <= padding < 0.5:
        raise argparse.ArgumentTypeError("expected a value from 0 up to 0.5")
    return padding


def contain(
    source: Image.Image,
    size: tuple[int, int],
    background: tuple[int, int, int],
    padding: float,
) -> Image.Image:
    box = source.getchannel("A").getbbox()
    if box:
        source = source.crop(box)
    width, height = size
    inner_w = max(1, round(width - 2 * padding * height))
    inner_h = max(1, round(height * (1 - 2 * padding)))
    # Never upscale: a small logo stays sharp in the middle of the card.
    scale = min(inner_w / source.width, inner_h / source.height, 1.0)
    art_w = max(1, round(source.width * scale))
    art_h = max(1, round(source.height * scale))
    artwork = source.resize((art_w, art_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, background + (255,))
    canvas.alpha_composite(artwork, ((width - art_w) // 2, (height - art_h) // 2))
    return canvas


def cover(
    source: Image.Image,
    size: tuple[int, int],
    background: tuple[int, int, int],
) -> Image.Image:
    width, height = size
    scale = max(width / source.width, height / source.height)
    art_w = max(width, round(source.width * scale))
    art_h = max(height, round(source.height * scale))
    artwork = source.resize((art_w, art_h), Image.Resampling.LANCZOS)
    left = (art_w - width) // 2
    top = (art_h - height) // 2
    canvas = Image.new("RGBA", size, background + (255,))
    canvas.alpha_composite(artwork.crop((left, top, left + width, top + height)))
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a social share image from one source image."
    )
    parser.add_argument("source", type=Path, help="logo, artwork, or still")
    parser.add_argument(
        "--out", type=Path, default=Path("static/share.jpg"), help="output JPEG"
    )
    parser.add_argument(
        "--fit",
        choices=("contain", "cover"),
        default="contain",
        help="contain: centre on a background; cover: fill and crop (default: contain)",
    )
    parser.add_argument(
        "--size",
        type=parse_size,
        default=(1200, 630),
        metavar="WxH",
        help="output size (default: 1200x630)",
    )
    parser.add_argument(
        "--background",
        type=parse_color,
        default=parse_color("#ffffff"),
        metavar="COLOUR",
        help="background behind the artwork and transparent areas (default: #ffffff)",
    )
    parser.add_argument(
        "--padding",
        type=parse_padding,
        default=0.12,
        metavar="FRACTION",
        help="contain mode: margin as a fraction of the height (default: 0.12)",
    )
    parser.add_argument(
        "--quality", type=int, default=85, help="JPEG quality (default: 85)"
    )
    args = parser.parse_args()

    try:
        source = Image.open(args.source).convert("RGBA")
    except OSError as error:
        parser.error(f"could not open {args.source}: {error}")

    if args.fit == "cover":
        image = cover(source, args.size, args.background)
    else:
        image = contain(source, args.size, args.background, args.padding)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(
        args.out, "JPEG", quality=args.quality, optimize=True, progressive=True
    )
    kib = args.out.stat().st_size // 1024
    print(f"✓ {args.out} ({args.size[0]}×{args.size[1]}, {kib} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
