#!/usr/bin/env python3
"""Build a simple page from template.html, content.md and static/.

This is the shared builder for sites whose build is just placeholders plus
content: `static/` is copied to `dist/`, and `content.md` fills the
`{{placeholders}}` in `template.html` to produce `dist/index.html`.

Sites with extra build steps (language variants, feeds, data-driven sections)
keep their own `scripts/build.py` and import `content.py` for the grammar.

Usage:
    python3 _shared/pagebuild.py
    python3 _shared/pagebuild.py --template template.html --content content.md
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import content

GENERATOR_COMMENT = (
    "<!doctype html>\n"
    "<!-- Generated from template.html and content.md by _shared/pagebuild.py"
    " — edit those files, not this one. -->"
)


def sync_static(static: Path, out: Path) -> int:
    """Recreate out/ as a clean copy of static/ and return the file count."""
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(static, out, ignore=shutil.ignore_patterns(".DS_Store"))
    return sum(1 for path in out.rglob("*") if path.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build dist/ from template.html, content.md and static/."
    )
    parser.add_argument(
        "--template", type=Path, default=Path("template.html"), metavar="FILE"
    )
    parser.add_argument(
        "--content", type=Path, default=Path("content.md"), metavar="FILE"
    )
    parser.add_argument("--static", type=Path, default=Path("static"), metavar="DIR")
    parser.add_argument("--out", type=Path, default=Path("dist"), metavar="DIR")
    args = parser.parse_args()

    if not args.template.exists():
        print(f"Missing template: {args.template}", file=sys.stderr)
        return 1
    if not args.content.exists():
        print(f"Missing content file: {args.content}", file=sys.stderr)
        return 1
    if not args.static.exists():
        print(f"Missing static directory: {args.static}", file=sys.stderr)
        return 1

    template = args.template.read_text(encoding="utf-8")
    blocks = content.parse_content(args.content.read_text(encoding="utf-8"))

    if not blocks:
        print(f"No [LABEL: ...] blocks found in {args.content}", file=sys.stderr)
        return 1

    placeholders = set(content.PLACEHOLDER_RE.findall(template))
    missing = sorted(placeholders - blocks.keys())
    if missing:
        print(
            "content.md is missing blocks for these placeholders: "
            + ", ".join(missing),
            file=sys.stderr,
        )
        return 1

    for name in sorted(blocks.keys() - placeholders):
        print(f"  note: block '{name}' is not used in template.html")

    # Only touch dist/ once the sources are known to be valid, so a typo in
    # content.md leaves the previously built output intact.
    assets = sync_static(args.static, args.out)

    output = content.PLACEHOLDER_RE.sub(lambda match: blocks[match.group(1)], template)
    output = output.replace("<!doctype html>", GENERATOR_COMMENT, 1)

    output_path = args.out / "index.html"
    output_path.write_text(output, encoding="utf-8")
    print(
        f"✓ Built {args.out}/ — index.html from {len(blocks)} content blocks, "
        f"{assets} asset files copied"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
