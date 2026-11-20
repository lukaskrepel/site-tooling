"""Shared content-file grammar for the site builders.

Sites keep their own `scripts/build.py` for page structure, feeds, sitemaps and
data-driven sections; this module is only the content grammar they would
otherwise copy:

    [LABEL: name]
    > A paragraph. Multiple > lines are joined with spaces.
    - A list item

Single-language sites parse the whole file with `parse_content`. Sites with
`### nl` / `### en` headings use `parse_language_content`, which splits each
block first and renders it through the site's own `render_block`.

Inline Markdown is escaped and supports **bold**, *italic*, __bold__,
_italic_ and [links](url). Three link styles are provided, because the sites
genuinely differ: `link_replacer` (external links open in a new tab with an
arrow), `link_replacer_https` (the same, and upgrades `http://` to `https://`),
and `link_replacer_plain` (no arrow).
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable

LABEL_RE = re.compile(r"^\[LABEL:\s*([a-z0-9-]+)\]\s*$", re.MULTILINE)
PLACEHOLDER_RE = re.compile(r"\{\{([a-z0-9-]+)\}\}")
LANGUAGE_HEADING_RE = re.compile(r"^#{2,6}\s*([A-Za-z]{2})\s*$")

BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
ITALIC_RE = re.compile(r"\*(.+?)\*")
BOLD_UNDERSCORE_RE = re.compile(r"(?<![A-Za-z0-9])__(.+?)__(?![A-Za-z0-9])")
ITALIC_UNDERSCORE_RE = re.compile(r"(?<![A-Za-z0-9])_(.+?)_(?![A-Za-z0-9])")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# Brand icon paths from Font Awesome Free 6.6.0 (CC BY 4.0)
# https://fontawesome.com/license/free
SOCIAL_ICONS = {
    "instagram": (
        "0 0 448 512",
        "M224.1 141c-63.6 0-114.9 51.3-114.9 114.9s51.3 114.9 114.9 114.9S339 319.5 339 255.9 287.7 141 224.1 141zm0 189.6c-41.1 0-74.7-33.5-74.7-74.7s33.5-74.7 74.7-74.7 74.7 33.5 74.7 74.7-33.6 74.7-74.7 74.7zm146.4-194.3c0 14.9-12 26.8-26.8 26.8-14.9 0-26.8-12-26.8-26.8s12-26.8 26.8-26.8 26.8 12 26.8 26.8zm76.1 27.2c-1.7-35.9-9.9-67.7-36.2-93.9-26.2-26.2-58-34.4-93.9-36.2-37-2.1-147.9-2.1-184.9 0-35.8 1.7-67.6 9.9-93.9 36.1s-34.4 58-36.2 93.9c-2.1 37-2.1 147.9 0 184.9 1.7 35.9 9.9 67.7 36.2 93.9s58 34.4 93.9 36.2c37 2.1 147.9 2.1 184.9 0 35.9-1.7 67.7-9.9 93.9-36.2 26.2-26.2 34.4-58 36.2-93.9 2.1-37 2.1-147.8 0-184.8zM398.8 388c-7.8 19.6-22.9 34.7-42.6 42.6-29.5 11.7-99.5 9-132.1 9s-102.7 2.6-132.1-9c-19.6-7.8-34.7-22.9-42.6-42.6-11.7-29.5-9-99.5-9-132.1s-2.6-102.7 9-132.1c7.8-19.6 22.9-34.7 42.6-42.6 29.5-11.7 99.5-9 132.1-9s102.7-2.6 132.1 9c19.6 7.8 34.7 22.9 42.6 42.6 11.7 29.5 9 99.5 9 132.1s2.7 102.7-9 132.1z",
    ),
    "youtube": (
        "0 0 576 512",
        "M549.655 124.083c-6.281-23.65-24.787-42.276-48.284-48.597C458.781 64 288 64 288 64S117.22 64 74.629 75.486c-23.497 6.322-42.003 24.947-48.284 48.597-11.412 42.867-11.412 132.305-11.412 132.305s0 89.438 11.412 132.305c6.281 23.65 24.787 41.5 48.284 47.821C117.22 448 288 448 288 448s170.78 0 213.371-11.486c23.497-6.321 42.003-24.171 48.284-47.821 11.412-42.867 11.412-132.305 11.412-132.305s0-89.438-11.412-132.305zm-317.51 213.508V175.185l142.739 81.205-142.739 81.201z",
    ),
    "tiktok": (
        "0 0 448 512",
        "M448,209.91a210.06,210.06,0,0,1-122.77-39.25V349.38A162.55,162.55,0,1,1,185,188.31V278.2a74.62,74.62,0,1,0,52.23,71.18V0l88,0a121.18,121.18,0,0,0,1.86,22.17h0A122.18,122.18,0,0,0,381,102.39a121.43,121.43,0,0,0,67,20.14Z",
    ),
}

LIST_ITEM_INDENT = " " * 20
DEFAULT_LANGUAGE_CODES = ("nl", "en")


def link_replacer(match: re.Match[str]) -> str:
    """External links open in a new tab and carry the arrow marker."""
    label, url = match.group(1), match.group(2)
    if url.startswith(("http://", "https://")):
        return (
            f'<a href="{url}" target="_blank" rel="noopener">{label} '
            '<span class="arrow" aria-hidden="true">↗</span></a>'
        )
    return f'<a href="{url}">{label}</a>'


def link_replacer_https(match: re.Match[str]) -> str:
    """Like `link_replacer`, and upgrades `http://` links to `https://`."""
    label, url = match.group(1), match.group(2)
    if url.startswith(("http://", "https://")):
        url = url.replace("http://", "https://", 1)
        return (
            f'<a href="{url}" target="_blank" rel="noopener">{label} '
            '<span class="arrow" aria-hidden="true">↗</span></a>'
        )
    return f'<a href="{url}">{label}</a>'


def link_replacer_plain(match: re.Match[str]) -> str:
    """External links open in a new tab without the arrow marker."""
    label, url = match.group(1), match.group(2)
    if url.startswith(("http://", "https://")):
        return f'<a href="{url}" target="_blank" rel="noopener">{label}</a>'
    return f'<a href="{url}">{label}</a>'


def md_to_html(text: str, link: Callable[[re.Match[str]], str] = link_replacer) -> str:
    """Escape text, then apply the small Markdown subset the sites use."""
    text = html.escape(text, quote=True)
    text = BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = BOLD_UNDERSCORE_RE.sub(r"<strong>\1</strong>", text)
    text = ITALIC_RE.sub(r"<em>\1</em>", text)
    text = ITALIC_UNDERSCORE_RE.sub(r"<em>\1</em>", text)
    text = LINK_RE.sub(link, text)
    return text


def render_list_item(
    item: str,
    md: Callable[[str], str] = md_to_html,
    icons: dict[str, tuple[str, str]] = SOCIAL_ICONS,
) -> str:
    """Render a list item, using a brand icon when it links to a social network."""
    match = LINK_RE.fullmatch(item.strip())
    icon = None
    label = url = ""

    if match:
        label, url = match.group(1).strip(), match.group(2).strip()
        key = re.sub(r"[^a-z0-9]+", "", label.lower())
        icon = icons.get(key)

    if not icon:
        return f"<li>{md(item)}</li>"

    view_box, path = icon
    label_attr = html.escape(label, quote=True)
    url_attr = html.escape(url, quote=True)
    target = ' target="_blank" rel="noopener"' if url.startswith("http") else ""
    return (
        f'<li><a href="{url_attr}"{target} aria-label="{label_attr}" '
        f'title="{label_attr}">'
        f'<svg viewBox="{view_box}" aria-hidden="true" focusable="false">'
        f'<path d="{path}"/></svg></a></li>'
    )


def parse_content(
    text: str,
    md: Callable[[str], str] = md_to_html,
    item_renderer: Callable[[str], str] = render_list_item,
) -> dict[str, str]:
    """Extract {label: html} pairs from a single-language content file."""
    parts = LABEL_RE.split(text)
    blocks: dict[str, str] = {}

    for index in range(1, len(parts), 2):
        name = parts[index]
        body = parts[index + 1]

        paragraph_lines: list[str] = []
        list_items: list[str] = []

        for raw_line in body.splitlines():
            line = raw_line.strip()
            if line.startswith(">"):
                value = line[1:].strip()
                if value:
                    paragraph_lines.append(value)
            elif line.startswith("- "):
                list_items.append(line[2:].strip())

        if list_items:
            items = [
                f"{'' if position == 0 else LIST_ITEM_INDENT}{item_renderer(item)}"
                for position, item in enumerate(list_items)
            ]
            blocks[name] = "\n".join(items)
        else:
            blocks[name] = md(" ".join(paragraph_lines))

    return blocks


def split_languages(
    name: str, body: str, language_codes: tuple[str, ...] = DEFAULT_LANGUAGE_CODES
) -> dict[str, str]:
    """Split a block body into {language: text}.

    A body without `### xx` headings is shared, so it is returned for every
    language unchanged.
    """
    sections: dict[str, str] = {}
    shared: list[str] = []
    current: str | None = None
    current_lines: list[str] = []

    for raw_line in body.splitlines():
        match = LANGUAGE_HEADING_RE.match(raw_line.strip())
        if match:
            code = match.group(1).lower()
            if code not in language_codes:
                raise ValueError(
                    f"[{name}] uses the unknown language heading "
                    f"'{raw_line.strip()}' (expected "
                    + " or ".join(f"### {known}" for known in language_codes)
                    + ")"
                )
            if current is not None:
                sections[current] = "\n".join(current_lines)
            current, current_lines = code, []
            continue
        if current is None:
            shared.append(raw_line)
        else:
            current_lines.append(raw_line)

    if current is None:
        return {code: body for code in language_codes}

    sections[current] = "\n".join(current_lines)

    if any(line.strip().startswith((">", "- ")) for line in shared):
        raise ValueError(
            f"[{name}] mixes shared text with ### language headings — put every "
            "paragraph under a heading, or remove the headings to share the "
            "block between all languages"
        )

    return sections


def parse_language_content(
    text: str,
    render_block: Callable[[str, str], str],
    language_codes: tuple[str, ...] = DEFAULT_LANGUAGE_CODES,
) -> dict[str, dict[str, str]]:
    """Extract {label: {language: html}} pairs from a bilingual content file."""
    parts = LABEL_RE.split(text)
    blocks: dict[str, dict[str, str]] = {}

    for index in range(1, len(parts), 2):
        name = parts[index]
        if name in blocks:
            raise ValueError(f"[{name}] appears more than once")
        sections = split_languages(name, parts[index + 1], language_codes)
        blocks[name] = {
            code: render_block(name, body) for code, body in sections.items()
        }

    return blocks


def language_blocks(language: dict[str, str]) -> dict[str, str]:
    """Placeholders that differ per language, independent of the content file."""
    is_dutch = language["code"] == "nl"
    return {
        "lang": language["code"],
        "base": language["base"],
        "canonical": language["canonical"],
        "url-nl": language["url"] if is_dutch else language["alt_url"],
        "url-en": language["alt_url"] if is_dutch else language["url"],
        "og-locale": language["og_locale"],
        "og-locale-alt": language["og_locale_alt"],
        "nl-class": "is-active" if is_dutch else "",
        "nl-current": 'aria-current="page"' if is_dutch else "",
        "en-class": "" if is_dutch else "is-active",
        "en-current": "" if is_dutch else 'aria-current="page"',
    }
