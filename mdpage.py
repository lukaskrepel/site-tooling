#!/usr/bin/env python3
"""Render Markdown files as small HTML pages.

Every `<name>.md` in the source directory becomes `<out>/<name>/index.html`, so
`privacy/club-baboo-puzzles.md` is served at `/privacy/club-baboo-puzzles/`.

The Markdown dialect is deliberately small (stdlib only):

    # Heading / ## Heading   -> <h2> / <h3> (one level deeper for the page)
    **bold** / __bold__      -> <b>
    *italic* / _italic_      -> <i>
    [text](url)              -> <a href="url">
    - item                   -> <ul><li>

Blank lines separate paragraphs; single newlines inside a paragraph become
`<br>`.

The page shell is a separate template, so a site keeps only the HTML around the
content. Three placeholders are filled: `{title}`, `{body}`, and
`{stylesheet}`:

    python3 _shared/mdpage.py privacy --out dist/privacy \\
        --template privacy/_page.html --stylesheet ../../styles.css --clean

`--clean` deletes the output directory first, so pages whose Markdown file was
removed disappear too.
"""

from __future__ import annotations

import argparse
import glob
import html
import os
import re
import shutil
from pathlib import Path

DEFAULT_TEMPLATE = """<!doctype html>
<html>
\t<head>
\t\t<meta charset="utf-8" />
\t\t<meta name="viewport" content="width=device-width, initial-scale=1" />
\t\t<link rel="stylesheet" href="{stylesheet}" />
\t\t<title>{title}</title>
\t</head>
\t<body>
\t\t<main>
{body}
\t\t</main>
\t</body>
</html>
"""

LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*|(?<!\w)__(.+?)__(?!\w)")
ITALIC_RE = re.compile(r"\*(.+?)\*|(?<!\w)_(.+?)_(?!\w)")
PLACEHOLDER_RE = re.compile("\x00(\\d+)\x00")
VALUE_RE = re.compile(r"\{(title|body|stylesheet)\}")


def emphasise(text):
    """Convert emphasis markers that are already HTML-escaped."""
    text = BOLD_RE.sub(lambda m: f"<b>{m.group(1) or m.group(2)}</b>", text)
    return ITALIC_RE.sub(lambda m: f"<i>{m.group(1) or m.group(2)}</i>", text)


def inline(text):
    """Render inline Markdown: links, bold, italic.

    Links are swapped for placeholders first so emphasis regexes can't touch
    underscores or asterisks inside URLs (and vice versa).
    """
    text = html.escape(text, quote=False)
    links = []

    def stash(match):
        links.append(match)
        return f"\x00{len(links) - 1}\x00"

    text = emphasise(LINK_RE.sub(stash, text))

    def unstash(match):
        link = links[int(match.group(1))]
        return f'<a href="{link.group(2)}">{emphasise(link.group(1))}</a>'

    return PLACEHOLDER_RE.sub(unstash, text)


def plain(text):
    """Strip inline Markdown for use in <title>."""
    text = LINK_RE.sub(r"\1", text)
    for marker in ("**", "__", "*", "_"):
        text = text.replace(marker, "")
    return text


def extract_title(markdown, fallback):
    """Use the first # heading as the page title."""
    for line in markdown.splitlines():
        match = re.match(r"^#\s+(.+)$", line.strip())
        if match:
            return plain(match.group(1))
    return fallback.replace("-", " ").title()


def render_body(markdown):
    """Convert Markdown bodies to indented HTML blocks."""
    blocks = []
    paragraph = []
    items = []

    def flush_paragraph():
        if paragraph:
            lines = "<br>\n\t\t\t".join(inline(line) for line in paragraph)
            blocks.append(f"\t\t\t<p>{lines}</p>")
            paragraph.clear()

    def flush_list():
        if items:
            lis = "\n".join(f"\t\t\t\t<li>{inline(item)}</li>" for item in items)
            blocks.append(f"\t\t\t<ul>\n{lis}\n\t\t\t</ul>")
            items.clear()

    for raw_line in markdown.splitlines():
        line = raw_line.strip()

        if not line:
            flush_paragraph()
            flush_list()
            continue

        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1)) + 1  # # -> h2, ## -> h3
            blocks.append(f"\t\t\t<h{level}>{inline(heading.group(2))}</h{level}>")
            continue

        if line.startswith("- "):
            flush_paragraph()
            items.append(line[2:])
            continue

        flush_list()
        paragraph.append(line)

    flush_paragraph()
    flush_list()
    return "\n".join(blocks)


def fill(template, values):
    """Replace placeholders in one pass, so content cannot cascade."""
    return VALUE_RE.sub(
        lambda match: values.get(match.group(1), match.group(0)), template
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render Markdown files as an HTML page per file."
    )
    parser.add_argument("source", type=Path, help="directory holding *.md files")
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        metavar="DIR",
        help="output root; each page gets <name>/index.html inside it",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=None,
        metavar="FILE",
        help="page shell with {title}, {body} and {stylesheet} placeholders",
    )
    parser.add_argument(
        "--stylesheet",
        default="",
        metavar="URL",
        help="value for the {stylesheet} placeholder",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="delete --out first, so removed pages disappear",
    )
    args = parser.parse_args()

    if not args.source.is_dir():
        parser.error(f"missing source directory: {args.source}")

    if args.template is not None:
        try:
            template = args.template.read_text(encoding="utf-8")
        except OSError as error:
            parser.error(f"could not read {args.template}: {error}")
    else:
        template = DEFAULT_TEMPLATE

    sources = sorted(glob.glob(os.path.join(args.source, "*.md")))
    if not sources:
        print(f"No .md files found in {args.source}/")
        return 0

    if args.clean and args.out.exists():
        shutil.rmtree(args.out)

    for path in sources:
        name = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as handle:
            markdown = handle.read()

        page = fill(
            template,
            {
                "title": html.escape(extract_title(markdown, name), quote=False),
                "body": render_body(markdown),
                "stylesheet": args.stylesheet,
            },
        )

        out_dir = args.out / name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "index.html"
        out_path.write_text(page, encoding="utf-8")
        os.chmod(out_path, 0o644)
        print(f"  Generated {out_path}")

    print(f"  {len(sources)} page(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
