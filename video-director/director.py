"""
video-director — Remotion one-shot harness.

Orchestrates three phases against a video spec:

  Phase A  (sequential, 1 agent)
      Director agent reads video_spec.xml and writes script.json +
      scene_status.json. The driver then calls ElevenLabs TTS on the
      script, writing public/audio.wav and timing.json. The driver
      then generates alignment.test.ts from timing.json.

  Phase B  (parallel, N agents — one per scene)
      Each scene agent writes src/scenes/Scene{N}.tsx and
      src/scenes/Scene{N}.anchors.json. After all finish, the driver
      stitches src/anchors.ts from every anchors.json file and runs
      the alignment test. Failing anchors are mapped back to the
      scene that owns them and those scenes are re-queued for a
      fresh agent pass (up to --max-scene-retries).

  Phase C  (sequential, 1 agent)
      Compositor agent writes src/Root.tsx, runs the alignment test,
      and renders out/video.mp4 via `npx remotion render`.

Usage:
    python video-director/director.py \\
        --spec /tmp/my-video/video_spec.xml \\
        --out /tmp/my-video/project

Requires CLAUDE_CODE_OAUTH_TOKEN and ELEVENLABS_API_KEY in the environment.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent

# Put autonomous-coding on sys.path so `from agent import run_agent_session`
# resolves. This also exposes autonomous-coding/security.py as `security`,
# which would shadow our extended hook — so we load video-director/security.py
# by absolute path below instead of importing it by name.
_AUTONOMOUS = _HERE.parent / "autonomous-coding"
if str(_AUTONOMOUS) not in sys.path:
    sys.path.insert(0, str(_AUTONOMOUS))

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher  # noqa: E402

from agent import run_agent_session  # noqa: E402  (from autonomous-coding)


def _load_video_module(name: str):
    full_name = f"video_director_{name}"
    spec = importlib.util.spec_from_file_location(full_name, _HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module  # required for @dataclass to resolve __module__
    spec.loader.exec_module(module)
    return module


_video_security = _load_video_module("security")
_video_tts = _load_video_module("tts")
_video_validator = _load_video_module("validator")

bash_security_hook = _video_security.bash_security_hook
load_script = _video_tts.load_script
synthesize_script = _video_tts.synthesize_script
generate_alignment_test = _video_validator.generate_alignment_test
run_alignment_test = _video_validator.run_alignment_test


DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
MAX_SCENE_RETRIES = 2

BUILTIN_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]

PHASE_PROMPTS = _HERE / "prompts"


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------


def _build_client(
    project_dir: Path,
    model: str,
    system_prompt: str,
    allowed_writes: list[str] | None = None,
) -> ClaudeSDKClient:
    """
    Build a ClaudeSDKClient scoped to project_dir with the video security
    hook and optional per-phase write restrictions.

    `allowed_writes` is a list of permission-string globs (e.g.
    `["Write(src/scenes/Scene3.tsx)", "Write(src/scenes/Scene3.anchors.json)"]`).
    When provided, the client's permission config replaces the broad
    `Write(./**)` / `Edit(./**)` with the narrower set, so a scene agent
    cannot touch another scene's files.
    """
    project_dir.mkdir(parents=True, exist_ok=True)

    if allowed_writes is None:
        write_perms = ["Write(./**)", "Edit(./**)"]
    else:
        write_perms = allowed_writes

    settings = {
        "sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True},
        "permissions": {
            "defaultMode": "acceptEdits",
            "allow": [
                "Read(./**)",
                "Glob(./**)",
                "Grep(./**)",
                *write_perms,
                "Bash(*)",
            ],
        },
    }

    settings_file = project_dir / ".claude_settings.json"
    settings_file.write_text(json.dumps(settings, indent=2))

    return ClaudeSDKClient(
        options=ClaudeAgentOptions(
            model=model,
            system_prompt=system_prompt,
            allowed_tools=BUILTIN_TOOLS,
            hooks={
                "PreToolUse": [
                    HookMatcher(matcher="Bash", hooks=[bash_security_hook]),
                ],
            },
            max_turns=200,
            cwd=str(project_dir.resolve()),
            settings=str(settings_file.resolve()),
        )
    )


def _load_prompt(name: str) -> str:
    return (PHASE_PROMPTS / name).read_text()


# ---------------------------------------------------------------------------
# Project scaffolding
# ---------------------------------------------------------------------------


REMOTION_PACKAGE_JSON = {
    "name": "video-director-output",
    "version": "0.1.0",
    "private": True,
    "scripts": {
        "test": "vitest run",
        "render": "remotion render src/index.ts main out/video.mp4",
    },
    "dependencies": {
        "react": "^18.3.1",
        "react-dom": "^18.3.1",
        "remotion": "^4.0.0",
        "@remotion/cli": "^4.0.0",
        "@remotion/bundler": "^4.0.0",
    },
    "devDependencies": {
        "typescript": "^5.4.0",
        "vitest": "^1.6.0",
        "@types/react": "^18.3.0",
    },
}

REMOTION_INDEX_TS = """import { registerRoot } from "remotion";
import { RemotionRoot } from "./Root";
registerRoot(RemotionRoot);
"""

ROOT_STUB = """// Placeholder Root.tsx — replaced by Phase C compositor.
import { Composition } from "remotion";

const Empty: React.FC = () => null;

export const RemotionRoot: React.FC = () => (
  <Composition id="main" component={Empty} durationInFrames={1} fps={30} width={1920} height={1080} />
);
"""

REMOTION_TSCONFIG = {
    "compilerOptions": {
        "target": "ES2020",
        "module": "ESNext",
        "moduleResolution": "bundler",
        "jsx": "react-jsx",
        "strict": True,
        "esModuleInterop": True,
        "resolveJsonModule": True,
        "skipLibCheck": True,
    },
    "include": ["src", "alignment.test.ts", "timing.json"],
}

REMOTION_VITEST_CONFIG = """import { defineConfig } from "vitest/config";
export default defineConfig({
  test: {
    include: ["alignment.test.ts"],
    environment: "node",
  },
});
"""

ANCHORS_STUB = """// Auto-generated by director.py. Do not hand-edit.
// Shot agents write per-shot maps to src/shots/Shot{N}.anchors.json;
// director.py stitches them here between Phase B and Phase C.

const REGISTERED: Record<string, number> = {};

export function resolveAnchor(id: string): number | null {
  return id in REGISTERED ? REGISTERED[id] : null;
}
"""

CAPTIONS_TSX = """// Auto-generated caption overlay. Reads timing.json captions and renders
// the active caption for the current frame. Mounted at the Root level by
// the compositor — shot components do NOT render captions themselves.
import React from "react";
import { useCurrentFrame } from "remotion";
import timing from "../timing.json";

interface Caption {
  text: string;
  start_frame: number;
  end_frame: number;
}

export const Captions: React.FC = () => {
  const frame = useCurrentFrame();
  const captions = (timing as { captions?: Caption[] }).captions ?? [];
  const active = captions.find(
    (c) => frame >= c.start_frame && frame < c.end_frame
  );
  if (!active) return null;
  return (
    <div
      style={{
        position: "absolute",
        bottom: 96,
        left: 0,
        right: 0,
        textAlign: "center",
        pointerEvents: "none",
      }}
    >
      <span
        style={{
          display: "inline-block",
          padding: "12px 24px",
          background: "rgba(0,0,0,0.55)",
          color: "white",
          fontFamily:
            "system-ui, -apple-system, 'Segoe UI', sans-serif",
          fontSize: 44,
          fontWeight: 600,
          lineHeight: 1.2,
          borderRadius: 8,
          maxWidth: "80%",
          whiteSpace: "pre-wrap",
        }}
      >
        {active.text}
      </span>
    </div>
  );
};
"""


def scaffold_project(project_dir: Path, spec_path: Path, install: bool = True) -> None:
    """Copy the video spec in, write the Remotion skeleton, and pnpm install."""
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "src" / "shots").mkdir(parents=True, exist_ok=True)
    (project_dir / "public").mkdir(parents=True, exist_ok=True)
    (project_dir / "out").mkdir(parents=True, exist_ok=True)

    spec_dest = project_dir / "video_spec.xml"
    if spec_path.resolve() != spec_dest.resolve():
        shutil.copy(spec_path, spec_dest)

    (project_dir / "package.json").write_text(
        json.dumps(REMOTION_PACKAGE_JSON, indent=2)
    )
    (project_dir / "tsconfig.json").write_text(json.dumps(REMOTION_TSCONFIG, indent=2))
    (project_dir / "vitest.config.ts").write_text(REMOTION_VITEST_CONFIG)
    (project_dir / "src" / "anchors.ts").write_text(ANCHORS_STUB)
    (project_dir / "src" / "index.ts").write_text(REMOTION_INDEX_TS)
    (project_dir / "src" / "Root.tsx").write_text(ROOT_STUB)
    (project_dir / "src" / "Captions.tsx").write_text(CAPTIONS_TSX)
    print(f"[scaffold] Remotion skeleton written to {project_dir}")

    if install:
        import subprocess
        print("[scaffold] running pnpm install (this can take a minute)...")
        result = subprocess.run(
            ["pnpm", "install", "--silent"],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"[scaffold] pnpm install failed:\n{result.stderr}")
            raise RuntimeError("pnpm install failed during scaffold")
        print("[scaffold] pnpm install complete")


# ---------------------------------------------------------------------------
# anchors.ts stitching
# ---------------------------------------------------------------------------


def stitch_anchors(project_dir: Path) -> int:
    """
    Read every src/shots/Shot*.anchors.json and emit src/anchors.ts.

    Returns the number of anchors registered.
    """
    shots_dir = project_dir / "src" / "shots"
    merged: dict[str, int] = {}
    for path in sorted(shots_dir.glob("Shot*.anchors.json")):
        data = json.loads(path.read_text())
        for anchor_id, frame in data.items():
            if anchor_id in merged and merged[anchor_id] != frame:
                print(
                    f"[stitch] WARNING: {anchor_id} declared twice "
                    f"({merged[anchor_id]} vs {frame} in {path.name})"
                )
            merged[anchor_id] = int(frame)

    body_lines = [f'  "{k}": {v},' for k, v in sorted(merged.items())]
    content = (
        "// Auto-generated by director.py. Do not hand-edit.\n"
        "// Source: src/shots/Shot*.anchors.json\n\n"
        "const REGISTERED: Record<string, number> = {\n"
        + "\n".join(body_lines)
        + "\n};\n\n"
        "export function resolveAnchor(id: string): number | null {\n"
        "  return id in REGISTERED ? REGISTERED[id] : null;\n"
        "}\n"
    )
    (project_dir / "src" / "anchors.ts").write_text(content)
    return len(merged)


def shots_owning_anchors(anchor_ids: list[str], timing: dict) -> list[str]:
    """
    Map failing anchor ids back to the shots that own them, using
    timing.json's anchor → shot association written by Phase A + tts.py.
    """
    owners: set[str] = set()
    by_id = {a["id"]: a for a in timing.get("anchors", [])}
    for aid in anchor_ids:
        a = by_id.get(aid)
        if a and a.get("shot"):
            owners.add(a["shot"])
    return sorted(owners)


# ---------------------------------------------------------------------------
# Phase runners
# ---------------------------------------------------------------------------


def _stage_refactor_inputs(project_dir: Path, brief_path: Path) -> None:
    """Copy brief.md and the spec template into project_dir for Phase 0."""
    project_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(brief_path, project_dir / "brief.md")
    shutil.copy(
        PHASE_PROMPTS / "video_spec_template.xml",
        project_dir / "video_spec_template.xml",
    )


async def run_phase_0_refactor(project_dir: Path, model: str) -> Path:
    """
    Spec refactor agent: reads brief.md + video_spec_template.xml from
    project_dir and writes a concrete video_spec.xml. Returns the path to
    the produced spec.
    """
    print("\n" + "=" * 70)
    print("  PHASE 0 — Spec Refactor")
    print("=" * 70 + "\n")

    client = _build_client(
        project_dir=project_dir,
        model=model,
        system_prompt=(
            "You are a video spec writer. Read brief.md + the template, "
            "write video_spec.xml. Nothing else."
        ),
        allowed_writes=["Write(video_spec.xml)", "Edit(video_spec.xml)"],
    )
    prompt = _load_prompt("refactor_prompt.md")
    async with client:
        status, _ = await run_agent_session(client, prompt, project_dir)
    if status != "continue":
        raise RuntimeError("Phase 0 (spec refactor) failed")

    spec_path = project_dir / "video_spec.xml"
    if not spec_path.exists():
        raise RuntimeError(
            "Phase 0 finished without writing video_spec.xml. "
            "Check the refactor agent's output above."
        )
    return spec_path


async def run_phase_a(project_dir: Path, model: str) -> None:
    """Director agent: writes script.json + scene_status.json."""
    print("\n" + "=" * 70)
    print("  PHASE A — Director")
    print("=" * 70 + "\n")

    client = _build_client(
        project_dir=project_dir,
        model=model,
        system_prompt="You are a video director. Produce scripts and timing plans only; never render.",
    )
    prompt = _load_prompt("director_prompt.md")
    async with client:
        status, _ = await run_agent_session(client, prompt, project_dir)
    if status != "continue":
        raise RuntimeError("Phase A (director) failed")

    script_path = project_dir / "script.json"
    if not script_path.exists():
        raise RuntimeError(
            "Phase A finished without writing script.json. "
            "Check the director agent's output above."
        )


def _shot_suffix(shot_id: str) -> str:
    """shot01 → 01, shot7 → 07."""
    n = shot_id.replace("shot", "").lstrip("0") or "0"
    return f"{int(n):02d}"


async def run_phase_b_shot(
    shot_id: str,
    project_dir: Path,
    model: str,
    semaphore: asyncio.Semaphore,
) -> tuple[str, str]:
    """One shot agent, scoped to its own files."""
    suffix = _shot_suffix(shot_id)
    allowed_writes = [
        f"Write(src/shots/Shot{suffix}.tsx)",
        f"Edit(src/shots/Shot{suffix}.tsx)",
        f"Write(src/shots/Shot{suffix}.anchors.json)",
        f"Edit(src/shots/Shot{suffix}.anchors.json)",
    ]

    async with semaphore:
        client = _build_client(
            project_dir=project_dir,
            model=model,
            system_prompt=(
                f"You are the shot agent for {shot_id}. "
                "Write only your shot's component and anchors.json. "
                "Never render captions — those are an overlay layer the "
                "compositor mounts. Never touch other shots, Root.tsx, "
                "Captions.tsx, or timing.json."
            ),
            allowed_writes=allowed_writes,
        )
        prompt = _load_prompt("shot_prompt.md") + f"\n\n## SHOT_ID\n\n{shot_id}\n"
        async with client:
            status, response = await run_agent_session(client, prompt, project_dir)
        return status, response


async def run_phase_b(
    project_dir: Path,
    model: str,
    max_retries: int,
    max_concurrent: int = 5,
) -> None:
    """
    Parallel shot agents (semaphore-limited), followed by anchor stitching
    and the alignment test. Failing anchors re-queue only the owning shots.
    """
    print("\n" + "=" * 70)
    print("  PHASE B — Shot components (parallel)")
    print("=" * 70 + "\n")

    timing = json.loads((project_dir / "timing.json").read_text())
    shot_ids = [s["id"] for s in timing.get("shots", [])]
    if not shot_ids:
        raise RuntimeError("Phase B: timing.json has no shots")
    pending = list(shot_ids)

    # Alignment test is written before Phase B so shot agents can see it.
    generate_alignment_test(project_dir, project_dir / "timing.json")

    semaphore = asyncio.Semaphore(max_concurrent)

    for attempt in range(max_retries + 1):
        if not pending:
            break
        print(
            f"[phase B] attempt {attempt + 1}: running {len(pending)} shot(s) "
            f"(max {max_concurrent} concurrent)"
        )
        results = await asyncio.gather(
            *(run_phase_b_shot(sid, project_dir, model, semaphore) for sid in pending),
            return_exceptions=True,
        )
        for sid, res in zip(pending, results):
            if isinstance(res, Exception):
                print(f"[phase B] {sid} raised: {res}")

        n_anchors = stitch_anchors(project_dir)
        print(f"[phase B] stitched {n_anchors} anchors into src/anchors.ts")

        result = run_alignment_test(project_dir)
        print(f"[phase B] {result.summary()}")
        if result.passed:
            return

        # Re-queue: shots whose anchors failed, plus shots whose .tsx is missing.
        bad_shots = set(shots_owning_anchors(result.failures, timing))
        bad_shots.update(result.missing_shots)
        if not bad_shots:
            raise RuntimeError(
                "Alignment test failed but no owning shots could be identified.\n"
                f"Failures: {result.failures}\n"
                f"Missing: {result.missing_shots}\n"
                f"stderr: {result.stderr[:500]}"
            )
        pending = sorted(bad_shots)
        print(f"[phase B] retrying shots with alignment failures: {pending}")

    raise RuntimeError(
        f"Phase B exhausted {max_retries + 1} attempts without passing alignment test"
    )


async def run_phase_c(project_dir: Path, model: str) -> None:
    """Compositor: writes Root.tsx, runs alignment test, renders."""
    print("\n" + "=" * 70)
    print("  PHASE C — Compositor")
    print("=" * 70 + "\n")

    client = _build_client(
        project_dir=project_dir,
        model=model,
        system_prompt=(
            "You are the compositor. Assemble scenes into Root.tsx, "
            "verify alignment, and render. Never edit scene components."
        ),
    )
    prompt = _load_prompt("compositor_prompt.md")
    async with client:
        status, _ = await run_agent_session(client, prompt, project_dir)
    if status != "continue":
        raise RuntimeError("Phase C (compositor) failed")

    out_path = project_dir / "out" / "video.mp4"
    if not out_path.exists():
        raise RuntimeError(
            f"Phase C finished without producing {out_path}. "
            "Check compositor output above."
        )
    print(f"\n[done] rendered {out_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _preflight() -> None:
    missing = [
        var
        for var in ("CLAUDE_CODE_OAUTH_TOKEN", "ELEVENLABS_API_KEY")
        if not os.environ.get(var)
    ]
    if missing:
        print(f"Error: required environment variables not set: {', '.join(missing)}")
        sys.exit(1)


async def main_async(args: argparse.Namespace) -> None:
    _preflight()

    project_dir = Path(args.out).resolve()

    if args.brief:
        # Phase 0: stage inputs, run refactor agent, then proceed with the
        # spec it produced.
        brief_path = Path(args.brief).resolve()
        if not brief_path.exists():
            print(f"Error: brief not found at {brief_path}")
            sys.exit(1)
        _stage_refactor_inputs(project_dir, brief_path)
        spec_path = await run_phase_0_refactor(project_dir, args.model)
    else:
        spec_path = Path(args.spec).resolve()
        if not spec_path.exists():
            print(f"Error: spec not found at {spec_path}")
            sys.exit(1)

    scaffold_project(project_dir, spec_path)

    # Phase A: director agent → script.json (continuous narration + shots)
    await run_phase_a(project_dir, args.model)

    # Driver: TTS → audio.mp3 + timing.json (anchors + shot frames + captions)
    script = load_script(project_dir / "script.json")
    synthesize_script(script, project_dir, fps=args.fps)

    # Phase B: parallel scene agents (with alignment retry loop)
    await run_phase_b(project_dir, args.model, max_retries=args.max_scene_retries)

    # Phase C: compositor → render
    await run_phase_c(project_dir, args.model)


def main() -> None:
    parser = argparse.ArgumentParser(description="Remotion video one-shot harness")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--spec", help="Path to a hand-written video_spec.xml")
    source.add_argument(
        "--brief",
        help=(
            "Path to a brief.md (topic + answers). Phase 0 spec refactor agent "
            "will turn it into video_spec.xml before the rest of the harness runs."
        ),
    )
    parser.add_argument("--out", required=True, help="Project output directory")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument(
        "--max-scene-retries",
        type=int,
        default=MAX_SCENE_RETRIES,
        help="How many times to re-run failing scene agents on alignment failure",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
