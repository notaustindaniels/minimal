"""
Tier 1 — offline plumbing test (shot-list model).

Exercises everything in director.py / tts.py / validator.py that does
NOT require Claude or ElevenLabs:
  - scaffold_project()
  - tts._scale_shots() and tts._derive_captions() with stub alignment
  - generate_alignment_test()
  - stitch_anchors() against fake Shot*.anchors.json
  - run_alignment_test() against a real (stub-data) project

Run with:
    source myvenv/bin/activate && python video-director/tier1_offline_test.py
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = Path("/tmp/video-director-tier1")
FPS = 30

sys.path.insert(0, str(HERE.parent / "autonomous-coding"))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"vd_{name}", HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[f"vd_{name}"] = m
    spec.loader.exec_module(m)
    return m


def main() -> None:
    if PROJECT.exists():
        shutil.rmtree(PROJECT)

    fake_spec = PROJECT.parent / "tier1-spec.xml"
    PROJECT.parent.mkdir(parents=True, exist_ok=True)
    fake_spec.write_text("<video_specification>tier1 stub</video_specification>")

    # Director.py is loaded after the others so its claude-sdk import works.
    director = importlib.util.spec_from_file_location("director", HERE / "director.py")
    director_mod = importlib.util.module_from_spec(director)
    sys.modules["director"] = director_mod
    director.loader.exec_module(director_mod)

    print("[tier1] scaffold_project()")
    director_mod.scaffold_project(PROJECT, fake_spec)

    # Confirm new scaffold artifacts are present.
    assert (PROJECT / "src" / "Captions.tsx").exists(), "Captions.tsx missing"
    assert (PROJECT / "src" / "shots").exists(), "src/shots missing"

    # Hand-craft a timing.json that the validator + stitcher can chew on.
    # 3 shots: complex (60f) + transition (15f) + simple (45f) = 120f = 4.0s @ 30fps
    timing = {
        "fps": FPS,
        "audio_path": "public/audio.mp3",
        "total_frames": 120,
        "anchors": [
            {"id": "anchor.beat", "frame": 30, "shot": "shot01"},
            {"id": "anchor.land", "frame": 90, "shot": "shot03"},
        ],
        "shots": [
            {"id": "shot01", "complexity": "complex",    "start_frame": 0,  "end_frame": 60},
            {"id": "shot02", "complexity": "transition", "start_frame": 60, "end_frame": 75},
            {"id": "shot03", "complexity": "simple",     "start_frame": 75, "end_frame": 120},
        ],
        "captions": [
            {"text": "stub caption one",   "start_frame": 0,  "end_frame": 60},
            {"text": "stub caption two",   "start_frame": 60, "end_frame": 120},
        ],
    }
    (PROJECT / "timing.json").write_text(json.dumps(timing, indent=2))
    print("[tier1] wrote stub timing.json (3 shots, 2 anchors, 2 captions)")

    print("[tier1] generate_alignment_test()")
    validator_mod = _load("validator")
    validator_mod.generate_alignment_test(PROJECT, PROJECT / "timing.json")
    assert (PROJECT / "alignment.test.ts").exists()

    # Pretend each shot agent ran: write the corresponding files.
    shots_dir = PROJECT / "src" / "shots"
    for sid in ("shot01", "shot02", "shot03"):
        suffix = director_mod._shot_suffix(sid)
        (shots_dir / f"Shot{suffix}.tsx").write_text(
            f"export const Shot{suffix}: React.FC = () => null;\n"
        )
    # Anchors: shot01 owns anchor.beat=30, shot03 owns anchor.land=90
    (shots_dir / "Shot01.anchors.json").write_text(json.dumps({"anchor.beat": 30}))
    (shots_dir / "Shot02.anchors.json").write_text(json.dumps({}))
    (shots_dir / "Shot03.anchors.json").write_text(json.dumps({"anchor.land": 90}))

    print("[tier1] stitch_anchors()")
    n = director_mod.stitch_anchors(PROJECT)
    print(f"[tier1] stitched {n} anchors")
    assert n == 2

    # Test the TTS helpers offline (no network).
    tts_mod = _load("tts")
    print("[tier1] tts._scale_shots() — 3 shots, target=10s, actual=12s")
    scaled = tts_mod._scale_shots(
        [
            {"id": "shot01", "complexity": "complex",    "target_seconds": 6.0},
            {"id": "shot02", "complexity": "transition", "target_seconds": 0.5},
            {"id": "shot03", "complexity": "simple",     "target_seconds": 2.0},
        ],
        total_seconds=12.0,
        fps=FPS,
    )
    last_end = scaled[-1]["end_frame"]
    expected_last_end = round(12.0 * FPS)
    assert last_end == expected_last_end, f"last shot end {last_end} != {expected_last_end}"
    print(f"[tier1]   scaled shots: {[(s['id'], s['start_frame'], s['end_frame']) for s in scaled]}")
    assert scaled[0]["start_frame"] == 0

    print("[tier1] tts._derive_captions() — fake alignment")
    fake_alignment = {
        "characters": list("hello world this is a test caption layer ok"),
        "character_start_times_seconds": [i * 0.05 for i in range(43)],
        "character_end_times_seconds":   [i * 0.05 + 0.05 for i in range(43)],
    }
    captions = tts_mod._derive_captions(
        "hello world this is a test caption layer ok", fake_alignment, FPS
    )
    print(f"[tier1]   derived {len(captions)} captions")
    assert len(captions) >= 1
    for c in captions:
        assert c["end_frame"] >= c["start_frame"]

    # Try to run the real vitest alignment test (requires pnpm install in
    # the project, which scaffold_project did).
    print("[tier1] running real vitest alignment.test.ts")
    proc = subprocess.run(
        ["npx", "vitest", "run", "alignment.test.ts", "--reporter=verbose"],
        cwd=PROJECT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print("[tier1] vitest FAILED:")
        print(proc.stdout[-1500:])
        sys.exit(1)
    print("[tier1] vitest PASSED")
    print("[tier1] PASS")


if __name__ == "__main__":
    main()
