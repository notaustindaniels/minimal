"""
Tier 1 — offline plumbing test (phrase-cut model).

Exercises everything in director.py / tts.py / validator.py that does
NOT require Claude or ElevenLabs:
  - scaffold_project()  (no Captions.tsx now)
  - tts._phrases_to_shots() with stub alignment data
  - tts._classify_complexity() boundary cases
  - generate_alignment_test()
  - stitch_anchors() against fake Shot*.anchors.json
  - real vitest run against the stitched anchors

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

    director_spec = importlib.util.spec_from_file_location("director", HERE / "director.py")
    director_mod = importlib.util.module_from_spec(director_spec)
    sys.modules["director"] = director_mod
    director_spec.loader.exec_module(director_mod)

    print("[tier1] scaffold_project()")
    director_mod.scaffold_project(PROJECT, fake_spec)
    assert (PROJECT / "src" / "shots").exists()
    assert not (PROJECT / "src" / "Captions.tsx").exists(), \
        "Captions.tsx should NOT be scaffolded in the phrase-cut model"
    # New scaffold files (PE + tools + docs)
    assert (PROJECT / "tools" / "fetch_image.py").exists(), "fetch_image.py not copied"
    assert (PROJECT / "tools" / "get_shot_timing.py").exists(), "get_shot_timing.py not copied"
    assert (PROJECT / "docs" / "showcase-examples.md").exists(), "showcase-examples.md not copied"
    assert (PROJECT / "docs" / "remotion-design-skill.md").exists(), "remotion-design-skill.md not copied"
    assert (PROJECT / "shot_instructions").exists(), "shot_instructions dir not created"

    # Hand-craft a timing.json that the validator + stitcher can chew on.
    # 3 shots derived from 3 phrases (no captions).
    timing = {
        "fps": FPS,
        "audio_path": "public/audio.mp3",
        "total_frames": 120,
        "anchors": [
            {"id": "anchor.beat", "frame": 30, "shot": "shot01"},
            {"id": "anchor.land", "frame": 90, "shot": "shot03"},
        ],
        "shots": [
            {"id": "shot01", "role": "shot",       "complexity": "complex",    "start_frame": 0,  "end_frame": 60,  "text": "First content phrase."},
            {"id": "shot02", "role": "transition", "complexity": "transition", "start_frame": 60, "end_frame": 75,  "text": "bridging clause."},
            {"id": "shot03", "role": "shot",       "complexity": "simple",     "start_frame": 75, "end_frame": 120, "text": "Punchy payoff."},
        ],
    }
    (PROJECT / "timing.json").write_text(json.dumps(timing, indent=2))

    print("[tier1] generate_alignment_test()")
    validator_mod = _load("validator")
    validator_mod.generate_alignment_test(PROJECT, PROJECT / "timing.json")
    assert (PROJECT / "alignment.test.ts").exists()

    # Pretend each shot agent ran.
    shots_dir = PROJECT / "src" / "shots"
    for sid in ("shot01", "shot02", "shot03"):
        suffix = director_mod._shot_suffix(sid)
        (shots_dir / f"Shot{suffix}.tsx").write_text(
            f"export const Shot{suffix}: React.FC = () => null;\n"
        )
    (shots_dir / "Shot01.anchors.json").write_text(json.dumps({"anchor.beat": 30}))
    (shots_dir / "Shot02.anchors.json").write_text(json.dumps({}))
    (shots_dir / "Shot03.anchors.json").write_text(json.dumps({"anchor.land": 90}))

    print("[tier1] stitch_anchors()")
    n = director_mod.stitch_anchors(PROJECT)
    assert n == 2

    # tts helpers — offline (no network).
    tts_mod = _load("tts")

    print("[tier1] tts._classify_complexity()")
    assert tts_mod._classify_complexity("transition", 0.5) == "transition"
    assert tts_mod._classify_complexity("transition", 5.0) == "transition"
    assert tts_mod._classify_complexity("shot", 1.5) == "simple"
    assert tts_mod._classify_complexity("shot", 4.5) == "complex"

    print("[tier1] tts._phrases_to_shots() with stub alignment (text-based phrases)")
    narration = "First sentence here. Bridging clause. Final punchy payoff line ok."
    n_chars = len(narration)
    fake_alignment = {
        "characters": list(narration),
        "character_start_times_seconds": [i * (6.0 / n_chars) for i in range(n_chars)],
        "character_end_times_seconds":   [(i + 1) * (6.0 / n_chars) for i in range(n_chars)],
    }
    phrases = [
        {"role": "shot",       "text": "First sentence here."},
        {"role": "transition", "text": "Bridging clause."},
        {"role": "shot",       "text": "Final punchy payoff line ok."},
    ]
    shots = tts_mod._phrases_to_shots(
        phrases, narration, fake_alignment, total_frames=180, fps=FPS
    )
    print(f"[tier1]   derived shots: {[(s['id'], s['role'], s['complexity'], s['start_frame'], s['end_frame']) for s in shots]}")
    assert len(shots) == 3
    assert shots[0]["start_frame"] == 0
    assert shots[-1]["end_frame"] == 180
    # Shots are contiguous
    for i in range(len(shots) - 1):
        assert shots[i]["end_frame"] == shots[i + 1]["start_frame"]

    # Unit test: get_shot_timing.py produces the expected block
    print("[tier1] get_shot_timing.py smoke")
    import subprocess
    proc = subprocess.run(
        ["python", "tools/get_shot_timing.py", "shot01"],
        cwd=PROJECT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"get_shot_timing failed: {proc.stderr}"
    out = proc.stdout
    assert "## The phrase" in out
    assert "## Frame window" in out
    assert "## Anchor contract" in out
    assert "start_frame: 0" in out
    assert "end_frame: 60" in out
    assert "fps: 30" in out
    # shot01 owns anchor.beat (frame 30)
    assert "anchor.beat" in out and "absolute frame 30" in out and "local frame 30" in out
    print(f"[tier1]   get_shot_timing output length: {len(out)} chars")

    # Unit test: _splice_authoritative_timing_into_brief replaces any
    # PE-written timing sections with the canonical block.
    print("[tier1] _splice_authoritative_timing_into_brief smoke")
    brief_dir = PROJECT / "shot_instructions"
    brief_dir.mkdir(parents=True, exist_ok=True)
    # Write a brief with WRONG timing info (PE hallucinated)
    (brief_dir / "Shot01.md").write_text(
        "# Shot01 — Brief\n\n"
        "## The phrase\n\n> \"WRONG TEXT\"\n\n"
        "## Frame window\n\n- start_frame: 9999\n- end_frame: 9999\n\n"
        "## Anchor contract\n\nwrong\n\n"
        "## Visual direction\n\nA bold visual concept.\n"
    )
    director_mod._splice_authoritative_timing_into_brief(PROJECT, "shot01")
    spliced = (brief_dir / "Shot01.md").read_text()
    assert "9999" not in spliced, "spliced brief still has hallucinated frame numbers"
    assert "start_frame: 0" in spliced
    assert "end_frame: 60" in spliced
    assert "A bold visual concept." in spliced, "creative direction should be preserved"
    assert "anchor.beat" in spliced, "anchor contract should be replaced with canonical"
    print("[tier1]   splice correctly replaced bogus timing")

    # Real vitest run against the stitched anchors.
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
