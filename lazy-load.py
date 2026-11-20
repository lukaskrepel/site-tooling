#!/usr/bin/env python3
"""Add loading="lazy" to images in built pages.

Skips tags that contain any `--skip` token, so above-the-fold images (and
anything else that should load eagerly) are left alone. Existing lazy
attributes are removed first, which makes the pass idempotent.

Usage:
    python3 _shared/lazy-load.py dist/index.html dist/en/index.html \\
        --skip 'id="lukas-mugshot"' --skip 'class="tv-image"'
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

LAZY_RE = re.compile(r'\s+loading="lazy"')
IMAGE_RE = re.compile(r"<img\b[^>]*/?>")


def add_lazy(tag: str, skip: list[str]) -> str:
    if any(token in tag for token in skip):
        return tag
    if tag.endswith("/>"):
        return tag[:-2] + ' loading="lazy" />'
    return tag[:-1] + ' loading="lazy">'


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Add loading="lazy" to images in built pages.'
    )
    parser.add_argument("pages", nargs="+", type=Path, metavar="PAGE")
    parser.add_argument(
        "--skip",
        action="extend",
        nargs="+",
        default=[],
        metavar="TOKEN",
        help="leave images containing this text eager",
    )
    args = parser.parse_args()

    missing = [str(page) for page in args.pages if not page.is_file()]
    if missing:
        parser.error("missing page: " + ", ".join(missing))

    for path in args.pages:
        html = path.read_text()
        html = LAZY_RE.sub("", html)
        html = IMAGE_RE.sub(lambda match: add_lazy(match.group(0), args.skip), html)
        count = html.count(' loading="lazy"')
        path.write_text(html)
        print(f"  {path}: {count} images lazy-loaded")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
