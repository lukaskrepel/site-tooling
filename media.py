#!/usr/bin/env python3
"""Convert media into published output, driven by a manifest.

A site keeps its conversion policy in `media.json` at the repository root and
runs one command:

    python3 _shared/media.py            # remake whatever is out of date
    python3 _shared/media.py --force    # remake everything
    python3 _shared/media.py --videos   # also run the video jobs
    python3 _shared/media.py --dry-run  # show what would happen

Every job describes where files come from (`src`), where they go (`out`), and
how they are encoded. The manifest is the policy; this script is the engine, so
a site never ships converter code of its own.

Image job keys:

    src               file or directory
    out               directory (src is a directory: relative paths are kept)
                      or target file (src is a file)
    include           paths inside src, or a named group: "@published"
    match             globs, relative to src
    format            webp | jpeg | png | copy
    quality           1-100 (default 82)
    method            WebP effort 0-6 (default 4)
    progressive       JPEG progressive flag (default true)
    flatten           JPEG: composite transparency on white (default false)
    mode              preserve | rgb (default preserve)
    max_width         downscale wider sources, never upscale
    widths            extra srcset widths, written as <name>-<width>.<ext>
    size              exact [width, height]
    crop, aspect      crop the centre to an aspect ratio before resizing
    trim              crop fully transparent borders
    resize            round | truncate (height rounding; default round)
    only_if_smaller   false, true (skip), or "copy" (publish source instead)
    exif_transpose    honour EXIF orientation (default false)
    prune_source      delete the original copied into out
    refs              only convert files referenced in these text files
    ref_prefix        published folder used to match refs (default out's name)
    skip_up_to_date   skip outputs newer than the source (default true)

Other job types:

    {"favicon": {"src": ..., "out": DIR, "background": "#rrggbb",
                 "padding": 0.08, "trim": true}}
    {"video": {"src": ..., "out": ..., "command": ["avconvert", "-s",
                "{src}", "-p", "Preset1280x720", "-o", "{out}", "--replace"]}}

Relative paths are resolved against the manifest's directory. Outputs are
written with 0644 permissions, because some web servers answer 403 otherwise.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import NoReturn

try:
    from PIL import Image, ImageOps
except ImportError:
    print(
        "Pillow is required: python3 -m pip install -r requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(1)


SOURCE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
COPY_SUFFIXES = SOURCE_SUFFIXES + (".gif",)
TARGET_SUFFIX = {"webp": ".webp", "jpeg": ".jpg", "png": ".png"}
# Bump when encoder settings change so cached derivatives are not reused.
CACHE_VERSION = "1"
FILE_MODE = 0o644

FAVICON_OUTPUTS = (
    "favicon-16x16.png",
    "favicon-32x32.png",
    "favicon.ico",
    "apple-touch-icon.png",
    "android-chrome-192x192.png",
    "android-chrome-512x512.png",
)

IMAGE_KEYS = {
    "src",
    "out",
    "include",
    "match",
    "format",
    "quality",
    "method",
    "progressive",
    "flatten",
    "mode",
    "max_width",
    "widths",
    "size",
    "crop",
    "aspect",
    "trim",
    "resize",
    "only_if_smaller",
    "exif_transpose",
    "prune_source",
    "refs",
    "ref_prefix",
    "skip_up_to_date",
}
FAVICON_KEYS = {"src", "out", "background", "padding", "trim"}
VIDEO_KEYS = {"src", "out", "command"}


@dataclass
class Stats:
    written: int = 0
    up_to_date: int = 0
    skipped: int = 0
    cached: int = 0
    videos: int = 0
    videos_skipped: int = 0


@dataclass
class Context:
    root: Path
    groups: dict
    cache: Path | None
    force: bool
    videos: bool
    dry_run: bool
    stats: Stats = field(default_factory=Stats)
    failures: int = 0


def fail(message: str) -> NoReturn:
    raise SystemExit(f"error: {message}")


def resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def write_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.chmod(path, FILE_MODE)


def glob_match(relative: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(relative, pattern) or PurePosixPath(relative).match(pattern):
            return True
        # `**/*.jpg` should also match a file at the top level.
        if pattern.startswith("**/"):
            stripped = pattern[3:]
            if fnmatch.fnmatch(relative, stripped) or PurePosixPath(relative).match(
                stripped
            ):
                return True
    return False


# ---------- Manifest selection ----------


def selector_values(selector: dict, ctx: Context) -> list[str]:
    allowed = {"json", "path", "dir"}
    unknown = set(selector) - allowed
    if unknown:
        fail("unknown include selector key(s): " + ", ".join(sorted(unknown)))
    if "json" not in selector or "path" not in selector:
        fail("an include selector needs 'json' and 'path'")

    document = resolve(ctx.root, selector["json"])
    try:
        data = json.loads(document.read_text(encoding="utf-8"))
    except OSError as error:
        fail(f"could not read selector file {document}: {error}")
    except json.JSONDecodeError as error:
        fail(f"could not parse selector file {document}: {error}")

    values: list = list(data) if isinstance(data, list) else [data]
    for token in str(selector["path"]).split("."):
        iterate = token.endswith("[]")
        key = token[:-2] if iterate else token
        collected: list = []
        for value in values:
            if not isinstance(value, dict) or key not in value:
                continue
            item = value[key]
            if iterate:
                collected.extend(item if isinstance(item, list) else [])
            else:
                collected.append(item)
        values = collected

    strings = [value for value in values if isinstance(value, str) and value]
    if not strings:
        fail(f"selector {selector['path']} in {document} matched nothing")
    directory = str(selector.get("dir", "")).strip("/")
    return [f"{directory}/{value}" if directory else value for value in strings]


def include_paths(value, ctx: Context) -> list[str]:
    if isinstance(value, str):
        entries = ctx.groups.get(value[1:]) if value.startswith("@") else [value]
        if entries is None:
            fail(f"unknown include group: {value}")
        if not isinstance(entries, list):
            fail(f"include group {value} must be a list")
    elif isinstance(value, list):
        entries = value
    else:
        fail("'include' must be a path, '@group' or a list")

    paths: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            paths.append(entry)
        elif isinstance(entry, dict):
            paths.extend(selector_values(entry, ctx))
        else:
            fail("include entries must be paths or selectors")
    return list(dict.fromkeys(paths))


def collect_sources(job: dict, source_root: Path, ctx: Context) -> list[Path]:
    matches = job.get("match", [])
    format_name = job["format"]

    if "include" in job:
        relatives = []
        missing = []
        for entry in include_paths(job["include"], ctx):
            relative = Path(entry)
            if relative.is_absolute():
                fail(f"include paths must be relative to src: {entry}")
            if not (source_root / relative).is_file():
                missing.append(entry)
                continue
            if matches and not glob_match(relative.as_posix(), matches):
                continue
            relatives.append(relative)
        if missing:
            fail(f"missing source(s) in {source_root}: " + ", ".join(sorted(missing)))
        if not relatives:
            fail(f"no sources selected in {source_root}")
        return relatives

    suffixes = COPY_SUFFIXES if format_name == "copy" else SOURCE_SUFFIXES
    relatives = []
    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source_root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if path.suffix.lower() not in suffixes:
            continue
        if matches and not glob_match(relative.as_posix(), matches):
            continue
        relatives.append(relative)
    return relatives


# ---------- Encoding ----------


def trim(image: Image.Image) -> Image.Image:
    """Crop fully transparent borders."""
    image = image.convert("RGBA")
    return image.crop(image.getbbox())


def flatten(image: Image.Image) -> Image.Image:
    """Composite transparency on white, for JPEG."""
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        canvas = Image.new("RGB", image.size, (255, 255, 255))
        canvas.paste(image, mask=image.getchannel("A"))
        return canvas
    return image.convert("RGB")


def scale(image: Image.Image, width: int, resize: str) -> Image.Image:
    ratio = width / image.width
    if resize == "truncate":
        height = int(image.height * ratio)
    else:
        height = round(image.height * ratio)
    return image.resize((width, max(1, height)), Image.Resampling.LANCZOS)


def center_crop(image: Image.Image, aspect: float) -> Image.Image:
    height = round(image.width / aspect)
    top = (image.height - height) // 2
    return image.crop((0, top, image.width, top + height))


def encode(source: Path, settings: dict) -> bytes:
    with Image.open(source) as raw:
        image = ImageOps.exif_transpose(raw) if settings["exif_transpose"] else raw
        if settings["trim"]:
            image = trim(image)

        format_name = settings["format"]
        if format_name == "jpeg":
            if settings["flatten"]:
                image = flatten(image)
            elif settings["mode"] == "rgb":
                image = image.convert("RGB")
        elif format_name == "webp":
            if settings["mode"] == "rgb":
                image = image.convert("RGB")
            elif image.mode not in ("RGB", "RGBA", "L"):
                image = image.convert("RGBA")

        if settings["max_width"] and image.width > settings["max_width"]:
            image = scale(image, settings["max_width"], settings["resize"])

        if settings["size"]:
            if settings["aspect"]:
                image = center_crop(image, settings["aspect"])
            image = image.resize(tuple(settings["size"]), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        if format_name == "jpeg":
            image.save(
                buffer,
                "JPEG",
                quality=settings["quality"],
                optimize=True,
                progressive=settings["progressive"],
            )
        elif format_name == "png":
            image.save(buffer, "PNG", optimize=True)
        else:
            image.save(
                buffer,
                "WEBP",
                quality=settings["quality"],
                method=settings["method"],
            )
        return buffer.getvalue()


def cache_key(source: Path, settings: dict) -> str:
    digest = hashlib.sha256()
    digest.update(source.read_bytes())
    digest.update(
        (
            f"|media{CACHE_VERSION}|{settings['format']}|{settings['quality']}"
            f"|{settings['method']}|{settings['progressive']}"
            f"|{settings['flatten']}|{settings['exif_transpose']}"
            f"|{settings['max_width']}|{settings['size']}|{settings['aspect']}"
            f"|{settings['trim']}|{settings['resize']}|{settings['mode']}"
        ).encode()
    )
    return digest.hexdigest()[:16]


# ---------- Jobs ----------


def validate_manifest(manifest: dict) -> None:
    jobs = manifest.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        fail("the manifest needs a non-empty 'jobs' list")
    groups = manifest.get("groups", {})
    if not isinstance(groups, dict):
        fail("'groups' must be an object")
    for name, entries in groups.items():
        if not isinstance(entries, list):
            fail(f"group {name!r} must be a list")

    unknown_root = set(manifest) - {"jobs", "groups", "cache"}
    if unknown_root:
        fail("unknown manifest key(s): " + ", ".join(sorted(unknown_root)))

    for index, job in enumerate(jobs):
        if not isinstance(job, dict):
            fail(f"job {index + 1} must be an object")
        if "video" in job:
            kinds = set(job)
            if kinds != {"video"}:
                fail(f"video job {index + 1} must contain only 'video'")
            spec = job["video"]
            allowed, label = VIDEO_KEYS, "video"
        elif "favicon" in job:
            kinds = set(job)
            if kinds != {"favicon"}:
                fail(f"favicon job {index + 1} must contain only 'favicon'")
            spec = job["favicon"]
            allowed, label = FAVICON_KEYS, "favicon"
        else:
            spec = job
            allowed, label = IMAGE_KEYS, "image"

        if not isinstance(spec, dict):
            fail(f"{label} job {index + 1} must be an object")
        unknown = set(spec) - allowed
        if unknown:
            fail(
                f"unknown {label} job key(s) in job {index + 1}: "
                + ", ".join(sorted(unknown))
            )
        for required in ("src", "out"):
            if required not in spec:
                fail(f"{label} job {index + 1} is missing '{required}'")

        if label != "image":
            continue

        if "format" not in spec:
            fail(f"image job {index + 1} is missing 'format'")
        if spec["format"] not in ("webp", "jpeg", "png", "copy"):
            fail(f"job {index + 1}: unknown format {spec['format']!r}")
        if not isinstance(spec["src"], str) or not isinstance(spec["out"], str):
            fail(f"job {index + 1}: src and out must be strings")
        if spec["format"] == "copy" and spec.get("refs"):
            fail(f"job {index + 1}: a copy job cannot use refs")
        if spec.get("only_if_smaller") == "copy" and spec.get("widths"):
            fail(f"job {index + 1}: 'copy' fallback cannot write width variants")
        quality = spec.get("quality", 82)
        if not isinstance(quality, int) or not 1 <= quality <= 100:
            fail(f"job {index + 1}: quality must be 1-100")
        method = spec.get("method", 4)
        if not isinstance(method, int) or not 0 <= method <= 6:
            fail(f"job {index + 1}: method must be 0-6")
        if spec.get("max_width") is not None and (
            not isinstance(spec["max_width"], int) or spec["max_width"] < 1
        ):
            fail(f"job {index + 1}: max_width must be a positive integer")
        if "widths" in spec and (
            not isinstance(spec["widths"], list)
            or not all(isinstance(width, int) and width > 0 for width in spec["widths"])
        ):
            fail(f"job {index + 1}: widths must be a list of positive integers")
        if spec.get("resize", "round") not in ("round", "truncate"):
            fail(f"job {index + 1}: resize must be 'round' or 'truncate'")
        if spec.get("mode", "preserve") not in ("preserve", "rgb"):
            fail(f"job {index + 1}: mode must be 'preserve' or 'rgb'")
        if spec.get("crop") not in (None, "center"):
            fail(f"job {index + 1}: crop must be 'center'")
        if spec.get("crop") and not spec.get("aspect"):
            fail(f"job {index + 1}: crop needs an aspect")
        if spec.get("aspect") and not spec.get("crop"):
            fail(f"job {index + 1}: aspect needs crop 'center'")
        if spec["format"] == "copy" and (
            spec.get("widths")
            or spec.get("only_if_smaller")
            or spec.get("max_width")
            or spec.get("size")
            or spec.get("trim")
            or spec.get("prune_source")
        ):
            fail(f"job {index + 1}: a copy job takes no image options")
        if spec.get("only_if_smaller") not in (None, True, False, "copy", "skip"):
            fail(f"job {index + 1}: only_if_smaller must be true, false or 'copy'")
        if "size" in spec and (
            not isinstance(spec["size"], list) or len(spec["size"]) != 2
        ):
            fail(f"job {index + 1}: size must be [width, height]")


def image_settings(job: dict, width: int | None) -> dict:
    return {
        "format": job["format"],
        "quality": int(job.get("quality", 82)),
        "method": int(job.get("method", 4)),
        "progressive": bool(job.get("progressive", True)),
        "flatten": bool(job.get("flatten", False)),
        "exif_transpose": bool(job.get("exif_transpose", False)),
        "max_width": width,
        "size": job.get("size"),
        "aspect": job.get("aspect"),
        "trim": bool(job.get("trim", False)),
        "resize": job.get("resize", "round"),
        "mode": job.get("mode", "preserve"),
    }


def output_path(out: Path, relative: Path, suffix: str, label: str = "") -> Path:
    stem = relative.with_suffix("")
    return out / stem.parent / f"{stem.name}{label}{suffix}"


def plan_outputs(job: dict, source: Path, relative: Path | None, out: Path):
    """Return [(width, path)] for the base file and any width variants."""
    format_name = job["format"]
    if relative is None:
        base = out
    elif format_name == "copy":
        return [(None, out / relative)]
    else:
        base = output_path(out, relative, TARGET_SUFFIX[format_name])

    widths = job.get("widths") or []
    max_width = job.get("max_width")
    if not widths:
        return [(max_width, base)]

    with Image.open(source) as probe:
        natural = probe.width
    base_width = min(natural, max_width) if max_width else natural
    targets = [(max_width, base)]
    for width in sorted(set(widths)):
        if width < base_width:
            if relative is None:
                variant = out.with_name(f"{out.stem}-{width}{out.suffix}")
            else:
                variant = output_path(
                    out, relative, TARGET_SUFFIX[format_name], f"-{width}"
                )
            targets.append((width, variant))
    return targets


def is_up_to_date(source: Path, targets: list[Path]) -> bool:
    source_time = source.stat().st_mtime
    return all(
        target.is_file() and target.stat().st_mtime >= source_time for target in targets
    )


def cached_encode(source: Path, settings: dict, ctx: Context) -> bytes:
    if ctx.cache is None:
        return encode(source, settings)
    cache_file = ctx.cache / (
        cache_key(source, settings) + TARGET_SUFFIX[settings["format"]]
    )
    if cache_file.is_file():
        ctx.stats.cached += 1
        return cache_file.read_bytes()
    data = encode(source, settings)
    if not ctx.dry_run:
        write_file(cache_file, data)
    return data


def print_written(target: Path, source: Path, before: int, after: int) -> None:
    print(f"  {target} ← {source} ({before / 1024:.0f} KB → {after / 1024:.0f} KB)")


def run_image_job(job: dict, ctx: Context) -> None:
    source_root = resolve(ctx.root, job["src"])
    out = resolve(ctx.root, job["out"])
    if not source_root.exists():
        fail(f"missing source: {source_root}")

    format_name = job["format"]
    only_if_smaller = job.get("only_if_smaller", False)
    if only_if_smaller is True:
        only_if_smaller = "skip"
    prune = bool(job.get("prune_source", False))
    skip_fresh = bool(job.get("skip_up_to_date", True))
    force = ctx.force or not skip_fresh

    refs: set[str] | None = None
    ref_prefix = job.get("ref_prefix", out.name)
    if job.get("refs"):
        if source_root.is_file():
            fail(f"'refs' needs a directory source: {source_root}")
        refs = collect_refs(
            (resolve(ctx.root, ref) for ref in job["refs"]),
            TARGET_SUFFIX[format_name],
        )

    satisfied: set[str] = set()

    if source_root.is_file():
        if any(key in job for key in ("include", "match", "refs", "prune_source")):
            fail(f"{source_root}: file sources take no include/match/refs/prune_source")
        if job.get("widths"):
            fail(f"{source_root}: width variants need a directory source")
        sources = [(source_root, None)]
    else:
        sources = [
            (source_root / relative, relative)
            for relative in collect_sources(job, source_root, ctx)
        ]

    for source, relative in sources:
        if format_name == "copy":
            target = out / relative if relative is not None else out
            if not force and is_up_to_date(source, [target]):
                ctx.stats.up_to_date += 1
                continue
            data = source.read_bytes()
            if ctx.dry_run:
                print(f"  would copy {target}")
            else:
                write_file(target, data)
                print(f"  {target} ← {source} (copied)")
            ctx.stats.written += 1
            continue

        targets = plan_outputs(job, source, relative, out)

        if refs is not None:
            suffix = TARGET_SUFFIX[format_name]
            published = (
                f"{ref_prefix}/{relative.with_suffix(suffix)}"
                if relative is not None
                else None
            )
            original = f"{ref_prefix}/{relative}" if relative is not None else None
            if published not in refs and original not in refs:
                continue

        if format_name == "webp" and source.suffix.lower() == ".webp":
            # Authored WebP derivatives are published byte-identical.
            target = targets[0][1]
            if not force and is_up_to_date(source, [target]):
                ctx.stats.up_to_date += 1
            elif ctx.dry_run:
                print(f"  would copy {target}")
                ctx.stats.written += 1
            else:
                if target.resolve() != source.resolve():
                    write_file(target, source.read_bytes())
                print(f"  {target} ← {source} (copied)")
                ctx.stats.written += 1
            if relative is not None:
                satisfied.add(f"{ref_prefix}/{relative.with_suffix('.webp')}")
            continue

        if not force and is_up_to_date(source, [path for _, path in targets]):
            ctx.stats.up_to_date += 1
            if prune and relative is not None and not ctx.dry_run:
                copied_original = out / relative
                if copied_original.is_file():
                    copied_original.unlink()
            if relative is not None:
                satisfied.add(
                    f"{ref_prefix}/{relative.with_suffix(TARGET_SUFFIX[format_name])}"
                )
            continue

        before = source.stat().st_size
        produced = False
        for width, target in targets:
            settings = image_settings(job, width)
            try:
                data = cached_encode(source, settings, ctx)
            except OSError as error:
                print(f"! could not convert {source}: {error}", file=sys.stderr)
                ctx.failures += 1
                break

            if only_if_smaller == "copy" and len(data) >= before:
                data = source.read_bytes()
                if ctx.dry_run:
                    print(f"  would copy {target}")
                else:
                    write_file(target, data)
                    print(f"  {target} ← {source} (copied, not smaller)")
                produced = True
                ctx.stats.written += 1
                break
            if only_if_smaller == "skip" and len(data) >= before:
                ctx.stats.skipped += 1
                break

            if ctx.dry_run:
                print(f"  would write {target} ({len(data) / 1024:.0f} KB)")
            else:
                write_file(target, data)
                print_written(target, source, before, len(data))
            produced = True
            ctx.stats.written += 1

        if not produced:
            continue

        if relative is not None:
            satisfied.add(
                f"{ref_prefix}/{relative.with_suffix(TARGET_SUFFIX[format_name])}"
            )
        if prune and relative is not None and not ctx.dry_run:
            copied_original = out / relative
            if copied_original.is_file():
                copied_original.unlink()

    if refs is not None and not job.get("match") and "include" not in job:
        handled = f"{ref_prefix}/"
        unresolved = sorted(
            ref for ref in refs if ref.startswith(handled) and ref not in satisfied
        )
        if unresolved:
            fail("no source found for " + ", ".join(unresolved))


def normalize_ref(url: str) -> str:
    for prefix in ("./", "../"):
        while url.startswith(prefix):
            url = url[len(prefix) :]
    return url


def collect_refs(files, suffix: str) -> set[str]:
    refs: set[str] = set()
    pattern = re.compile(r"[A-Za-z0-9_./-]+" + re.escape(suffix))
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as error:
            fail(f"could not read {path}: {error}")
        for match in pattern.finditer(text):
            refs.add(normalize_ref(match.group(0)))
    return refs


def run_favicon_job(spec: dict, ctx: Context) -> None:
    source = resolve(ctx.root, spec["src"])
    out = resolve(ctx.root, spec["out"])
    if not source.is_file():
        fail(f"missing source: {source}")

    expected = [out / name for name in FAVICON_OUTPUTS]
    fresh = is_up_to_date(source, expected)
    if fresh and not ctx.force:
        ctx.stats.up_to_date += 1
        return

    if ctx.dry_run:
        print(f"  would write {out}/favicon*.png and favicon.ico")
        ctx.stats.written += len(expected)
        return

    with Image.open(source) as opened:
        image = trim(opened) if spec.get("trim") else opened.convert("RGBA")
        with tempfile.TemporaryDirectory() as temporary:
            icon = Path(temporary) / "icon.png"
            image.save(icon)
            command = [
                sys.executable,
                str(Path(__file__).with_name("favicons.py")),
                str(icon),
                "--out",
                str(out),
            ]
            if spec.get("background"):
                command += ["--background", str(spec["background"])]
            if spec.get("padding") is not None:
                command += ["--padding", str(spec["padding"])]
            try:
                subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
            except subprocess.CalledProcessError as error:
                fail(f"favicons.py failed for {source}: {error}")

    for path in expected:
        if path.is_file():
            os.chmod(path, FILE_MODE)
    print(f"  {out}/ ← {source} (favicon set)")
    ctx.stats.written += len(expected)


def run_video_job(spec: dict, ctx: Context) -> None:
    if not ctx.videos:
        ctx.stats.videos_skipped += 1
        return

    source = resolve(ctx.root, spec["src"])
    out = resolve(ctx.root, spec["out"])
    if not source.is_file():
        fail(f"missing source: {source}")
    command = spec.get("command")
    if not isinstance(command, list) or not command:
        fail(f"video job for {source} needs a command list")

    if (
        not ctx.force
        and out.is_file()
        and out.stat().st_mtime >= source.stat().st_mtime
    ):
        ctx.stats.up_to_date += 1
        return

    argv = [
        str(part).replace("{src}", str(source)).replace("{out}", str(out))
        for part in command
    ]
    if ctx.dry_run:
        print(f"  would run {' '.join(argv)}")
        ctx.stats.videos += 1
        return

    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(argv, check=True)
    except subprocess.CalledProcessError as error:
        fail(f"video command failed for {source}: {error}")
    if out.is_file():
        os.chmod(out, FILE_MODE)
    print(f"  {out} ← {source} (video)")
    ctx.stats.videos += 1


def run(
    manifest: dict,
    root: Path,
    *,
    force: bool = False,
    videos: bool = False,
    dry_run: bool = False,
    cache: Path | None = None,
) -> int:
    validate_manifest(manifest)

    if cache is not None and not cache.is_absolute():
        cache = root / cache
    manifest_cache = manifest.get("cache")
    if cache is None and manifest_cache:
        cache = resolve(root, manifest_cache)

    ctx = Context(
        root=root,
        groups=manifest.get("groups", {}),
        cache=cache,
        force=force,
        videos=videos,
        dry_run=dry_run,
    )
    if ctx.cache is not None and not ctx.dry_run:
        ctx.cache.mkdir(parents=True, exist_ok=True)

    for job in manifest["jobs"]:
        if "video" in job:
            run_video_job(job["video"], ctx)
        elif "favicon" in job:
            run_favicon_job(job["favicon"], ctx)
        else:
            run_image_job(job, ctx)

    stats = ctx.stats
    if dry_run:
        print(f"✓ Would write {stats.written} file(s)")
    else:
        summary = f"✓ {stats.written} file(s) written"
        details = []
        if stats.up_to_date:
            details.append(f"{stats.up_to_date} up to date")
        if stats.skipped:
            details.append(f"{stats.skipped} skipped (not smaller)")
        if stats.cached:
            details.append(f"{stats.cached} from cache")
        if videos and stats.videos:
            details.append(f"{stats.videos} video(s)")
        elif stats.videos_skipped:
            details.append(f"{stats.videos_skipped} video job(s) skipped")
        if details:
            summary += " (" + ", ".join(details) + ")"
        print(summary)
    return 1 if ctx.failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert media according to a media.json manifest."
    )
    parser.add_argument(
        "manifest",
        nargs="?",
        type=Path,
        default=Path("media.json"),
        help="manifest path (default: media.json)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="remake every output, even when it looks up to date",
    )
    parser.add_argument(
        "--videos",
        action="store_true",
        help="also run video jobs (skipped by default)",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=None,
        metavar="DIR",
        help="reuse encoded derivatives from this directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print planned work without writing anything",
    )
    args = parser.parse_args()

    if not args.manifest.is_file():
        fail(
            f"manifest not found: {args.manifest} "
            "(run from the site root or pass a path)"
        )
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"could not parse {args.manifest}: {error}")
    if not isinstance(manifest, dict):
        fail(f"{args.manifest} must contain an object")

    return run(
        manifest,
        args.manifest.resolve().parent,
        force=args.force,
        videos=args.videos,
        dry_run=args.dry_run,
        cache=args.cache,
    )


if __name__ == "__main__":
    raise SystemExit(main())
