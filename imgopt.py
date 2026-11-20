#!/usr/bin/env python3
"""Generate web-optimised image derivatives for a build directory.

Reads raster sources (JPG/PNG) from one or more source directories and writes
resized, compressed WebP (or JPEG) files into a build directory. The source
folder name and relative path are preserved, so `--src static/images` writes
`dist/images/...`. Hand-authored WebP files are copied through unchanged, so
assets that should not be re-encoded keep working.

Two selection modes:

  * reference mode (`--refs`): only convert sources whose published path is
    referenced in the given files, usually template.html and styles.css.
  * explicit mode: convert everything under `--src`, optionally filtered with
    `--match` globs.

Use `--prune-source` to remove the original that a site build copied into the
output tree, for assets where only the derivative is published.

This is the compatibility command line. New sites describe the same policy in
a `media.json` manifest and run `media.py` instead; both use the same engine.

Usage:
    imgopt.py --src static/images --out dist --refs template.html static/styles.css
    imgopt.py --src static/videos --out dist --match '*.jpg' \\
        --max-width 1280 --quality 80 --prune-source --cache .cache/imgopt
"""

from __future__ import annotations

import argparse
from pathlib import Path

import media


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("expected a positive number")
    return number


def quality_value(value: str) -> int:
    number = int(value)
    if not 1 <= number <= 100:
        raise argparse.ArgumentTypeError("expected a number from 1 to 100")
    return number


def method_value(value: str) -> int:
    number = int(value)
    if not 0 <= number <= 6:
        raise argparse.ArgumentTypeError("expected a number from 0 to 6")
    return number


def parse_widths(value: str) -> list[int]:
    try:
        widths = sorted({int(part) for part in value.split(",") if part.strip()})
    except ValueError:
        raise argparse.ArgumentTypeError("expected comma-separated widths")
    if not widths or widths[0] < 1:
        raise argparse.ArgumentTypeError("expected comma-separated widths")
    return widths


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate resized WebP/JPEG derivatives for a build directory."
    )
    parser.add_argument(
        "--src",
        type=Path,
        action="extend",
        nargs="+",
        required=True,
        metavar="DIR",
        help="source directory; its name becomes the folder inside --out",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("dist"),
        metavar="DIR",
        help="build root that receives the derivatives (default: dist)",
    )
    parser.add_argument(
        "--refs",
        type=Path,
        action="extend",
        nargs="+",
        default=[],
        metavar="FILE",
        help="only convert sources referenced in these files",
    )
    parser.add_argument(
        "--match",
        action="extend",
        nargs="+",
        default=[],
        metavar="GLOB",
        help="only convert paths matching these globs (e.g. '*.jpg')",
    )
    parser.add_argument(
        "--format",
        choices=["jpeg", "webp"],
        default="webp",
        help="output format (default: webp)",
    )
    parser.add_argument(
        "--quality",
        type=quality_value,
        default=82,
        metavar="N",
        help="encoder quality 1-100 (default: 82)",
    )
    parser.add_argument(
        "--method",
        type=method_value,
        default=4,
        metavar="N",
        help="WebP effort 0-6; higher is slower and slightly smaller (default: 4)",
    )
    parser.add_argument(
        "--max-width",
        type=positive_int,
        default=None,
        metavar="PX",
        help="downscale wider sources to this width (default: keep size)",
    )
    parser.add_argument(
        "--widths",
        type=parse_widths,
        default=[],
        metavar="LIST",
        help="extra widths for srcset variants, e.g. 640,960 (default: none)",
    )
    parser.add_argument(
        "--prune-source",
        action="store_true",
        help="delete the copied original from --out after converting",
    )
    parser.add_argument(
        "--only-if-smaller",
        action="store_true",
        help="skip a derivative that is not smaller than its source",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=None,
        metavar="DIR",
        help="reuse encoded derivatives from this directory between builds",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print planned output without writing anything",
    )
    args = parser.parse_args()

    missing = [str(root) for root in args.src if not root.is_dir()]
    if missing:
        parser.error("missing source directory: " + ", ".join(missing))

    jobs = []
    for root in args.src:
        jobs.append(
            {
                "src": str(root),
                "out": str(args.out / root.name),
                "format": args.format,
                "quality": args.quality,
                "method": args.method,
                "max_width": args.max_width,
                "widths": args.widths,
                "match": args.match,
                "refs": [str(ref) for ref in args.refs],
                "ref_prefix": root.name,
                "prune_source": args.prune_source,
                "only_if_smaller": args.only_if_smaller,
                # imgopt always rewrote its output, and always honoured EXIF.
                "exif_transpose": True,
                "skip_up_to_date": False,
            }
        )

    return media.run(
        {"jobs": jobs},
        Path.cwd(),
        force=False,
        videos=False,
        dry_run=args.dry_run,
        cache=args.cache,
    )


if __name__ == "__main__":
    raise SystemExit(main())
