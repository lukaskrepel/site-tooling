#!/usr/bin/env python3
"""Composite app screenshots into a phone border and export WebP files.

Keep raw captures in a source folder such as `source/app-screenshots/<app>/`
and write the composited files into the published images folder, for example
`static/images/apps/<app>/` or `images/apps/<app>/`.

Usage:
    appshots.py --border source/phone_border.png \
        --window 290,70,2386,1248 \
        --out static/images/apps/my-app \
        source/app-screenshots/my-app/*.png

The window is the rectangle inside the border that holds the screen, given as
x1,y1,x2,y2. Files are named after the input stems, so keep the input names
meaningful (`insects.png`, `bones.png`, `menu.png`).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    print(
        "Pillow is required: python3 -m pip install -r requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(1)


def parse_window(value: str) -> tuple[int, int, int, int]:
    parts = value.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("expected x1,y1,x2,y2")
    try:
        x1, y1, x2, y2 = (int(part) for part in parts)
    except ValueError:
        raise argparse.ArgumentTypeError("window values must be integers")
    if x1 < 0 or y1 < 0 or x1 >= x2 or y1 >= y2:
        raise argparse.ArgumentTypeError("expected x1 < x2 and y1 < y2")
    return x1, y1, x2, y2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Composite screenshots into a phone border and export WebP."
    )
    parser.add_argument("--border", required=True, help="phone border PNG")
    parser.add_argument(
        "--window",
        required=True,
        type=parse_window,
        help="screen rectangle inside the border: x1,y1,x2,y2",
    )
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument(
        "--width", type=int, default=1200, help="output width (default: 1200)"
    )
    parser.add_argument(
        "--quality", type=int, default=86, help="WebP quality (default: 86)"
    )
    parser.add_argument(
        "--fit",
        choices=("cover", "contain"),
        default="cover",
        help="how to fit a screenshot into the window (default: cover)",
    )
    parser.add_argument("--prefix", default="", help="prefix for output filenames")
    parser.add_argument("shots", nargs="+", help="raw screenshot files")
    args = parser.parse_args()

    border = Image.open(args.border).convert("RGBA")
    x1, y1, x2, y2 = args.window
    if x2 > border.width or y2 > border.height:
        parser.error(
            f"window {x1},{y1},{x2},{y2} is outside the "
            f"{border.width}x{border.height} border"
        )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    win_w, win_h = x2 - x1, y2 - y1
    for shot_path in args.shots:
        shot = Image.open(shot_path).convert("RGBA")

        if args.fit == "contain":
            fitted = ImageOps.contain(shot, (win_w, win_h), Image.Resampling.LANCZOS)
            layer = Image.new("RGBA", (win_w, win_h), (0, 0, 0, 255))
            layer.alpha_composite(
                fitted, ((win_w - fitted.width) // 2, (win_h - fitted.height) // 2)
            )
        else:
            layer = ImageOps.fit(shot, (win_w, win_h), Image.Resampling.LANCZOS)

        composed = border.copy()
        composed.alpha_composite(layer, (x1, y1))

        if args.width > 0 and composed.width != args.width:
            height = round(composed.height * args.width / composed.width)
            composed = composed.resize((args.width, height), Image.Resampling.LANCZOS)

        out_path = out_dir / f"{args.prefix}{Path(shot_path).stem}.webp"
        composed.save(out_path, "WEBP", quality=args.quality, method=6)
        print(
            f"✓ {out_path} "
            f"({composed.width}×{composed.height}, {out_path.stat().st_size // 1024} KB)"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
