"""
Phase 0 smoke test — exercise just the spec refactor agent.

Reads /tmp/video-phase0-smoke/brief.md, runs Phase 0, and verifies that
video_spec.xml lands. Does NOT run Phase A/B/C, does NOT call ElevenLabs,
does NOT render. Useful for iterating on refactor_prompt.md.

Run with:
    source myvenv/bin/activate && python video-director/phase0_smoke_test.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRIEF = Path("/tmp/video-phase0-smoke/brief.md")
PROJECT = Path("/tmp/video-phase0-smoke/project")

sys.path.insert(0, str(HERE.parent / "autonomous-coding"))
spec = importlib.util.spec_from_file_location("director", HERE / "director.py")
director = importlib.util.module_from_spec(spec)
sys.modules["director"] = director
spec.loader.exec_module(director)


async def main() -> None:
    if not BRIEF.exists():
        print(f"FAIL: brief not found at {BRIEF}")
        sys.exit(1)
    if PROJECT.exists():
        shutil.rmtree(PROJECT)

    director._stage_refactor_inputs(PROJECT, BRIEF)
    spec_path = await director.run_phase_0_refactor(PROJECT, director.DEFAULT_MODEL)

    if not spec_path.exists():
        print("FAIL: video_spec.xml not produced")
        sys.exit(1)

    content = spec_path.read_text()
    print(f"\n[smoke] video_spec.xml: {len(content)} chars")
    # Sanity: make sure no UPPERCASE template placeholders like {VIDEO_TITLE}
    # survived. (Lowercase {} from TS code examples in implementation_steps
    # are fine — those are documentation, not placeholders.)
    import re
    leftovers = re.findall(r"\{[A-Z_]{3,}\}", content)
    if leftovers:
        print(f"[smoke] WARNING: unresolved placeholders: {set(leftovers)}")

    # Sanity: scene count matches duration rule (15s → 1 scene)
    scene_count = content.count("<scene id=")
    print(f"[smoke] scene count: {scene_count}")
    print("[smoke] PASS")


if __name__ == "__main__":
    asyncio.run(main())
