#!/usr/bin/env python3
"""
get_shot_timing.py — deterministic timing block generator for a single shot.

Usage:
    python tools/get_shot_timing.py <shot_id>

Example:
    python tools/get_shot_timing.py shot04

Output (to stdout, markdown): the authoritative `## The phrase`,
`## Frame window`, and `## Anchor contract` sections for the given
shot, derived directly from `timing.json` in the current working
directory (the project root). The translation prompt engineer MUST
paste this output VERBATIM at the top of each shot's brief. Frame
numbers, phrase text, and anchor local-frame math are non-negotiable;
this tool is the only source of truth.

This script is standalone and has no dependencies beyond Python stdlib.
It's copied into each project dir by the scaffold.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _shot_suffix(shot_id: str) -> str:
    n = shot_id.replace("shot", "").lstrip("0") or "0"
    return f"{int(n):02d}"


def render_timing_block(project_dir: Path, shot_id: str) -> str:
    timing_path = project_dir / "timing.json"
    if not timing_path.exists():
        print(f"error: timing.json not found at {timing_path}", file=sys.stderr)
        sys.exit(2)

    timing = json.loads(timing_path.read_text())
    fps = int(timing.get("fps", 30))
    shots = timing.get("shots", [])
    anchors = timing.get("anchors", [])

    shot = next((s for s in shots if s["id"] == shot_id), None)
    if shot is None:
        print(f"error: shot id {shot_id!r} not found in timing.json", file=sys.stderr)
        print(f"  available ids: {[s['id'] for s in shots]}", file=sys.stderr)
        sys.exit(3)

    start_frame = int(shot["start_frame"])
    end_frame = int(shot["end_frame"])
    duration_frames = end_frame - start_frame
    duration_seconds = duration_frames / fps

    phrase_text = (shot.get("text") or "").strip()
    role = shot.get("role", "shot")
    complexity = shot.get("complexity", "simple")
    suffix = _shot_suffix(shot_id)

    lines: list[str] = []
    lines.append("## The phrase")
    lines.append("")
    lines.append(f"> {json.dumps(phrase_text)}")
    lines.append("")
    lines.append("## Frame window")
    lines.append("")
    lines.append(f"- start_frame: {start_frame}")
    lines.append(f"- end_frame: {end_frame}")
    lines.append(f"- duration_frames: {duration_frames}")
    lines.append(f"- duration_seconds: {duration_seconds:.2f}")
    lines.append(f"- fps: {fps}")
    lines.append(f"- role: {role}")
    lines.append(f"- complexity hint: {complexity}")
    lines.append("")

    # Anchor contract
    owned = [
        a
        for a in anchors
        if a.get("shot") == shot_id
    ]
    lines.append("## Anchor contract")
    lines.append("")
    if not owned:
        lines.append(
            f"No anchors for this shot. Write `{{}}` to Shot{suffix}.anchors.json."
        )
    else:
        for a in owned:
            abs_frame = int(a["frame"])
            local_frame = abs_frame - start_frame
            lines.append(
                f"- **{a['id']}** — absolute frame {abs_frame}, local frame {local_frame}."
            )
            lines.append(
                f"  Your keyframe for this anchor MUST land within ±1 frame of the "
                f"local position. Register the absolute frame "
                f"(`{a['id']}: {abs_frame}`) in Shot{suffix}.anchors.json."
            )
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python tools/get_shot_timing.py <shot_id>", file=sys.stderr)
        sys.exit(1)

    shot_id = sys.argv[1].strip()
    project_dir = Path.cwd()
    block = render_timing_block(project_dir, shot_id)
    print(block)


if __name__ == "__main__":
    main()
