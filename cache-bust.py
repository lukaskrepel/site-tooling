#!/usr/bin/env python3
"""Append content-hash query strings to local asset URLs in a build directory.

Static assets are served with long cache lifetimes, so changing a file without
changing its URL leaves returning visitors on the old version. This script adds
?v=<content-hash> to local CSS, JS, image, and font URLs. Changed files get a
new URL; unchanged files keep their cache.

Handles href/src/poster attributes, asset data-* attributes, srcset attributes,
url(...) references in CSS, and icon src paths in .webmanifest files.

Usage: cache-bust.py [DIR]    (default: dist)
"""

import hashlib
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

HASH_LENGTH = 10

ASSET_EXTENSIONS = {
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".svg",
    ".ico",
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
    ".webmanifest",
}

CSS_URL_RE = re.compile(r"url\((?P<quote>[\"']?)(?P<url>[^\"')]+)(?P=quote)\)")
ASSET_ATTR = r"(?:href|src|poster|data-[\w-]+)"
HTML_URL_RE = re.compile(
    rf"(?P<attr>\b{ASSET_ATTR}=[\"'])(?P<url>[^\"']+)(?P<end>[\"'])"
)
SRCSET_RE = re.compile(r"(?P<attr>\bsrcset=[\"'])(?P<value>[^\"']+)(?P<end>[\"'])")
MANIFEST_SRC_RE = re.compile(r'(?P<attr>"src"\s*:\s*")(?P<url>[^"]+)(?P<end>")')

_hashes = {}


def file_hash(path):
    key = str(path)
    if key not in _hashes:
        _hashes[key] = hashlib.sha256(path.read_bytes()).hexdigest()[:HASH_LENGTH]
    return _hashes[key]


def is_local_asset(url):
    if not url or url.startswith(("#", "data:", "mailto:", "tel:", "javascript:")):
        return False

    parts = urlsplit(url)
    if parts.scheme or parts.netloc:
        return False

    return Path(parts.path).suffix.lower() in ASSET_EXTENSIONS


def version_url(url, base, root):
    if not is_local_asset(url):
        return url

    parts = urlsplit(url)
    if parts.path.startswith("/"):
        asset_path = root / parts.path.lstrip("/")
    else:
        asset_path = (base / parts.path).resolve()

    if not asset_path.is_file():
        return url

    params = [p for p in parts.query.split("&") if p and not p.startswith("v=")]
    params.append(f"v={file_hash(asset_path)}")

    return urlunsplit(("", "", parts.path, "&".join(params), parts.fragment))


def version_srcset(value, base, root):
    candidates = []
    for candidate in value.split(","):
        candidate = candidate.strip()
        if not candidate:
            continue
        pieces = candidate.split()
        pieces[0] = version_url(pieces[0], base, root)
        candidates.append(" ".join(pieces))
    return ", ".join(candidates)


def version_manifest_urls(manifest_path, root):
    text = manifest_path.read_text()

    def replace(match):
        return (
            f'{match.group("attr")}'
            f"{version_url(match.group('url'), manifest_path.parent, root)}"
            f'{match.group("end")}'
        )

    manifest_path.write_text(MANIFEST_SRC_RE.sub(replace, text))


def version_css_urls(css_path, root):
    text = css_path.read_text()

    def replace(match):
        url = match.group("url").strip()
        quote = match.group("quote")
        return f"url({quote}{version_url(url, css_path.parent, root)}{quote})"

    css_path.write_text(CSS_URL_RE.sub(replace, text))


def version_html_urls(html_path, root):
    text = html_path.read_text()

    def replace_srcset(match):
        value = version_srcset(match.group("value"), html_path.parent, root)
        return f'{match.group("attr")}{value}{match.group("end")}'

    text = SRCSET_RE.sub(replace_srcset, text)

    def replace_url(match):
        url = match.group("url")
        return (
            f'{match.group("attr")}'
            f"{version_url(url, html_path.parent, root)}"
            f'{match.group("end")}'
        )

    html_path.write_text(HTML_URL_RE.sub(replace_url, text))


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "dist").resolve()
    if not root.is_dir():
        raise SystemExit(f"Missing build directory: {root}")

    for css_path in sorted(root.rglob("*.css")):
        version_css_urls(css_path, root)

    for manifest_path in sorted(root.rglob("*.webmanifest")):
        version_manifest_urls(manifest_path, root)

    html_files = sorted(root.rglob("*.html"))
    for html_path in html_files:
        version_html_urls(html_path, root)

    print(f"  Versioned assets in {len(html_files)} HTML file(s)")


if __name__ == "__main__":
    main()
