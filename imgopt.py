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

Usage:
    imgopt.py --src static/images --out dist --refs template.html static/styles.css
    imgopt.py --src static/videos --out dist --match '*.jpg' \\
        --max-width 1280 --quality 80 --prune-source --cache .cache/imgopt
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import re
import shutil
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


SOURCE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
TARGET_SUFFIX = {"webp": ".webp", "jpeg": ".jpg"}
# Bump when encoder settings change so cached derivatives are not reused.
CACHE_VERSION = "1"


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


def normalize_ref(url: str) -> str:
    for prefix in ("./", "../"):
        while url.startswith(prefix):
            url = url[len(prefix) :]
    return url


def collect_refs(files: list[Path], suffix: str) -> set[str]:
    """Return the published paths referenced by the given text files."""
    pattern = re.compile(r"[A-Za-z0-9_./-]+" + re.escape(suffix))
    refs: set[str] = set()
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as error:
            raise SystemExit(f"Could not read {path}: {error}")
        for match in pattern.finditer(text):
            refs.add(normalize_ref(match.group(0)))
    return refs


def iter_sources(root: Path, matches: list[str]):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if matches and not any(
            fnmatch.fnmatch(relative.as_posix(), pattern) for pattern in matches
        ):
            continue
        yield path, relative


def target_path(
    out: Path, folder: str, relative: Path, suffix: str, label: str = ""
) -> Path:
    stem = relative.with_suffix("")
    return out / folder / stem.parent / f"{stem.name}{label}{suffix}"


def flatten(image: Image.Image) -> Image.Image:
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        canvas = Image.new("RGB", image.size, (255, 255, 255))
        canvas.paste(image, mask=image.getchannel("A"))
        return canvas
    return image.convert("RGB")


def encode(
    source: Path, fmt: str, quality: int, limit: int | None, method: int
) -> bytes:
    with Image.open(source) as raw:
        image = ImageOps.exif_transpose(raw)
        if fmt == "jpeg":
            image = flatten(image)
        elif image.mode not in ("RGB", "RGBA", "L"):
            image = image.convert("RGBA")

        if limit and image.width > limit:
            height = max(1, round(image.height * limit / image.width))
            image = image.resize((limit, height), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        if fmt == "jpeg":
            image.save(buffer, "JPEG", quality=quality, optimize=True, progressive=True)
        else:
            image.save(buffer, "WEBP", quality=quality, method=method)
        return buffer.getvalue()


def cache_key(
    source: Path, fmt: str, quality: int, limit: int | None, method: int
) -> str:
    digest = hashlib.sha256()
    digest.update(source.read_bytes())
    digest.update(
        f"|imgopt{CACHE_VERSION}|{fmt}|{quality}|{limit}|{method}".encode("utf-8")
    )
    return digest.hexdigest()[:16]


def plan_variants(
    source: Path, widths: list[int], max_width: int | None
) -> list[tuple[int | None, str]]:
    """Return (width, filename label) for the base file and extra widths."""
    with Image.open(source) as probe:
        natural = probe.width

    base_width = min(natural, max_width) if max_width else natural
    variants: list[tuple[int | None, str]] = [(max_width, "")]
    for width in widths:
        if width < base_width:
            variants.append((width, f"-{width}"))
    return variants


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
        choices=sorted(TARGET_SUFFIX),
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

    suffix = TARGET_SUFFIX[args.format]
    refs = collect_refs(args.refs, suffix) if args.refs else None
    folders = {root.name for root in args.src}

    if args.cache and not args.dry_run:
        args.cache.mkdir(parents=True, exist_ok=True)

    written = 0
    cached = 0
    skipped = 0
    failed = False
    total_before = 0
    total_after = 0
    satisfied: set[str] = set()

    for root in args.src:
        for source, relative in iter_sources(root, args.match):
            base_target = target_path(args.out, root.name, relative, suffix)
            base_published = f"{root.name}/{relative.with_suffix(suffix)}"

            if refs is not None:
                original_published = f"{root.name}/{relative}"
                if (
                    base_published not in refs
                    and original_published not in refs
                ):
                    continue

            if args.format == "webp" and source.suffix.lower() == ".webp":
                # Keep authored WebP derivatives byte-identical.
                satisfied.add(base_published)
                written += 1
                if args.dry_run:
                    print(f"  would copy {base_target}")
                elif base_target.resolve() != source.resolve():
                    base_target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, base_target)
                continue

            before = source.stat().st_size
            after = 0
            produced = False
            base_kb = 0.0

            for width, label in plan_variants(source, args.widths, args.max_width):
                target = target_path(args.out, root.name, relative, suffix, label)
                key = cache_key(source, args.format, args.quality, width, args.method)
                cache_file = args.cache / f"{key}{suffix}" if args.cache else None

                if cache_file and cache_file.is_file():
                    data = cache_file.read_bytes()
                    cached += 1
                else:
                    try:
                        data = encode(source, args.format, args.quality, width, args.method)
                    except OSError as error:
                        print(f"! could not convert {source}: {error}", file=sys.stderr)
                        failed = True
                        break
                    if cache_file and not args.dry_run:
                        cache_file.write_bytes(data)

                if args.only_if_smaller and len(data) >= before:
                    skipped += 1
                    break

                produced = True
                written += 1
                after += len(data)
                if not label:
                    base_kb = len(data) / 1024

                if args.dry_run:
                    print(f"  would write {target} ({len(data) / 1024:.0f} KB)")
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)

            if not produced:
                continue

            satisfied.add(base_published)
            total_before += before
            total_after += after

            if args.prune_source and not args.dry_run:
                original = args.out / root.name / relative
                if original.is_file():
                    original.unlink()

            if not args.dry_run:
                print(
                    f"  {base_target} ← {source} "
                    f"({before / 1024:.0f} KB → {base_kb:.0f} KB)"
                )

    if refs is not None and not args.match:
        handled = tuple(folder + "/" for folder in folders)
        unresolved = sorted(
            ref
            for ref in refs
            if ref.startswith(handled) and ref not in satisfied
        )
        if unresolved:
            print("! no source found for " + ", ".join(unresolved), file=sys.stderr)
            failed = True

    if args.dry_run:
        print(f"✓ Would write {written} {args.format} file(s)")
    else:
        summary = f"✓ Wrote {written} {args.format} file(s)"
        if total_before:
            summary += (
                f", {total_before / 1024 / 1024:.2f} MB → "
                f"{total_after / 1024 / 1024:.2f} MB"
            )
        if cached:
            summary += f" ({cached} from cache)"
        if skipped:
            summary += f", {skipped} skipped"
        print(summary)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
