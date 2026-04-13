#!/usr/bin/env python3
"""
fetch_image.py — on-demand image fetcher for shot agents.

Usage:
    python tools/fetch_image.py "<search_query>" <output_path>
        [--orientation landscape|portrait|square]
        [--no-saliency]

Fetches a single photograph for the given search query and writes it to
`output_path`. Also writes a sidecar JSON (<output_path>.json) containing
subject bounding box (from U2-Net small via rembg), dimensions, source,
and attribution. Prints the sidecar JSON to stdout so the calling agent
can parse it directly.

Source chain (primary → fallbacks):
  1. Pexels API  (PEXELS_API_KEY in env) — high-resolution stock photos
  2. Pixabay API (no auth required)       — public stock photos
  3. Wikipedia MediaWiki API               — article lead images

Each source returns an image at roughly 1920×1280 or better. A saliency
pass via U2-Net small (rembg's `u2netp` model) extracts the subject
bounding box so shot agents can position overlay typography in real
negative space.

This script is standalone. It's copied into each project dir by the
director scaffold and invoked via Bash by shot agents when they want an
image. Shot agents do NOT pre-fetch; they call this for what they need.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36 video-director/1.0"
)


def _http_get_json(url: str, headers: dict | None = None, timeout: int = 20) -> dict | None:
    merged = {"User-Agent": _BROWSER_UA}
    if headers:
        merged.update(headers)
    try:
        req = urllib.request.Request(url, headers=merged)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as e:
        print(f"[fetch_image]   http error: {e}", file=sys.stderr)
        return None


def _http_download(url: str, out_path: Path, timeout: int = 60) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _BROWSER_UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            out_path.write_bytes(resp.read())
        return True
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        print(f"[fetch_image]   download error: {e}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Source 1: Pexels
# ---------------------------------------------------------------------------


def try_pexels(
    query: str, out_path: Path, orientation: str = "landscape"
) -> dict | None:
    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        print("[fetch_image]   PEXELS_API_KEY not set — skipping pexels", file=sys.stderr)
        return None

    url = (
        "https://api.pexels.com/v1/search?"
        f"query={urllib.parse.quote(query)}"
        f"&orientation={orientation}"
        "&per_page=5&size=large"
    )
    data = _http_get_json(url, headers={"Authorization": api_key})
    if not data or not data.get("photos"):
        return None

    photo = data["photos"][0]
    # Prefer `original` (full uncompressed, often 4000+px wide) so Ken
    # Burns zooms can go tight without pixelation. Fall back through
    # progressively lower sizes if the key is missing for some reason.
    src = photo.get("src") or {}
    img_url = (
        src.get("original")
        or src.get("large2x")
        or src.get("large")
        or src.get("medium")
    )
    if not img_url:
        return None

    if not _http_download(img_url, out_path):
        return None

    return {
        "source": "pexels",
        "width": photo.get("width"),
        "height": photo.get("height"),
        "source_url": photo.get("url"),
        "photographer": photo.get("photographer"),
        "photographer_url": photo.get("photographer_url"),
        "attribution": f"Photo by {photo.get('photographer', 'unknown')} on Pexels",
    }


# ---------------------------------------------------------------------------
# Source 2: Pixabay (no auth for small queries)
# ---------------------------------------------------------------------------


def try_pixabay(query: str, out_path: Path) -> dict | None:
    # Pixabay technically requires a key but has a demo/fallback for
    # small volume. Use the env var if present; otherwise skip.
    api_key = os.environ.get("PIXABAY_API_KEY")
    if not api_key:
        print("[fetch_image]   PIXABAY_API_KEY not set — skipping pixabay", file=sys.stderr)
        return None

    url = (
        "https://pixabay.com/api/?"
        f"key={api_key}"
        f"&q={urllib.parse.quote(query)}"
        "&image_type=photo&orientation=horizontal"
        "&per_page=5&safesearch=true"
    )
    data = _http_get_json(url)
    if not data or not data.get("hits"):
        return None

    hit = data["hits"][0]
    img_url = hit.get("largeImageURL") or hit.get("webformatURL")
    if not img_url or not _http_download(img_url, out_path):
        return None

    return {
        "source": "pixabay",
        "width": hit.get("imageWidth"),
        "height": hit.get("imageHeight"),
        "source_url": hit.get("pageURL"),
        "photographer": hit.get("user"),
        "attribution": f"Image by {hit.get('user', 'unknown')} on Pixabay",
    }


# ---------------------------------------------------------------------------
# Source 3: Wikipedia MediaWiki API (last resort)
# ---------------------------------------------------------------------------


def try_wikipedia(query: str, out_path: Path) -> dict | None:
    url = (
        "https://en.wikipedia.org/w/api.php?"
        "action=query&format=json"
        "&prop=pageimages&piprop=thumbnail&pithumbsize=1920&redirects=1"
        f"&titles={urllib.parse.quote(query)}"
    )
    data = _http_get_json(
        url,
        headers={"User-Agent": "video-director/1.0 (https://github.com/notaustindaniels/minimal)"},
    )
    if not data:
        return None

    pages = (data.get("query") or {}).get("pages") or {}
    for page_id, page in pages.items():
        if str(page_id) == "-1":
            continue
        thumb = page.get("thumbnail")
        if not thumb or not thumb.get("source"):
            continue
        img_url = thumb["source"]
        if not _http_download(img_url, out_path):
            continue
        return {
            "source": "wikipedia",
            "width": thumb.get("width"),
            "height": thumb.get("height"),
            "source_url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(page.get('title', query))}",
            "attribution": f"From Wikipedia article '{page.get('title', query)}'",
        }
    return None


# ---------------------------------------------------------------------------
# Saliency (U2-Net small via rembg)
# ---------------------------------------------------------------------------


def compute_saliency_bbox(img_path: Path) -> dict | None:
    """
    Run U2-Net small on `img_path` and return the subject bounding box
    as {x, y, w, h} plus image dimensions. Returns None if rembg is
    unavailable or the model fails to extract a subject.
    """
    try:
        from rembg import remove, new_session
        from PIL import Image
    except ImportError as e:
        print(f"[fetch_image]   rembg not installed: {e}", file=sys.stderr)
        return None

    try:
        session = new_session("u2netp")  # u2netp = the small variant
        with open(img_path, "rb") as f:
            input_bytes = f.read()
        output_bytes = remove(input_bytes, session=session)
        out_img = Image.open(io.BytesIO(output_bytes))
        bbox = out_img.getbbox()  # (left, top, right, bottom) or None
        if bbox is None:
            return None
        left, top, right, bottom = bbox
        width, height = out_img.size
        return {
            "subject_bbox": {
                "x": left,
                "y": top,
                "w": right - left,
                "h": bottom - top,
            },
            "image_width": width,
            "image_height": height,
            "subject_bbox_normalized": {
                "x": round(left / width, 4),
                "y": round(top / height, 4),
                "w": round((right - left) / width, 4),
                "h": round((bottom - top) / height, 4),
            },
        }
    except Exception as e:
        print(f"[fetch_image]   saliency error: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def fetch_image(
    query: str,
    out_path: Path,
    orientation: str = "landscape",
    compute_saliency: bool = True,
) -> dict:
    """
    Try each source in order until one succeeds, then optionally run
    saliency and return the combined sidecar dict.

    Raises SystemExit(1) if every source fails.
    """
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    sources = [
        ("pexels", lambda: try_pexels(query, out_path, orientation)),
        ("pixabay", lambda: try_pixabay(query, out_path)),
        ("wikipedia", lambda: try_wikipedia(query, out_path)),
    ]

    source_meta: dict | None = None
    for name, fn in sources:
        print(f"[fetch_image] trying {name} for query={query!r}", file=sys.stderr)
        source_meta = fn()
        if source_meta and out_path.exists() and out_path.stat().st_size > 0:
            print(f"[fetch_image]   got {out_path} via {name}", file=sys.stderr)
            break
    else:
        print(f"[fetch_image] ALL sources failed for {query!r}", file=sys.stderr)
        sys.exit(1)

    sidecar: dict[str, Any] = {
        "query": query,
        "filename": str(out_path),
        **(source_meta or {}),
    }

    if compute_saliency:
        sal = compute_saliency_bbox(out_path)
        if sal:
            sidecar.update(sal)

    sidecar_path = out_path.with_suffix(out_path.suffix + ".json")
    sidecar_path.write_text(json.dumps(sidecar, indent=2))

    # Print the sidecar JSON to stdout for the calling agent.
    print(json.dumps(sidecar, indent=2))
    return sidecar


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch one image for a shot agent and compute its saliency bbox."
    )
    parser.add_argument("query", help="Search query, e.g. 'ruby-throated hummingbird in flight'")
    parser.add_argument("output_path", help="Where to save the image (e.g. public/assets/shot04.jpg)")
    parser.add_argument(
        "--orientation",
        choices=("landscape", "portrait", "square"),
        default="landscape",
    )
    parser.add_argument(
        "--no-saliency",
        action="store_true",
        help="Skip the U2-Net saliency pass (faster, no bbox in sidecar)",
    )
    args = parser.parse_args()

    fetch_image(
        query=args.query,
        out_path=Path(args.output_path),
        orientation=args.orientation,
        compute_saliency=not args.no_saliency,
    )


if __name__ == "__main__":
    main()
