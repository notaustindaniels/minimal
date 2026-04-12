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
load_narrations_from_script = _video_tts.load_narrations_from_script
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
// Scene agents write per-scene maps to src/scenes/Scene{N}.anchors.json;
// director.py stitches them here between Phase B and Phase C.

const REGISTERED: Record<string, number> = {};

export function resolveAnchor(id: string): number | null {
  return id in REGISTERED ? REGISTERED[id] : null;
}
"""


def scaffold_project(project_dir: Path, spec_path: Path, install: bool = True) -> None:
    """Copy the video spec in, write the Remotion skeleton, and pnpm install."""
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "src" / "scenes").mkdir(parents=True, exist_ok=True)
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
    Read every src/scenes/Scene*.anchors.json and emit src/anchors.ts.

    Returns the number of anchors registered.
    """
    scenes_dir = project_dir / "src" / "scenes"
    merged: dict[str, int] = {}
    for path in sorted(scenes_dir.glob("Scene*.anchors.json")):
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
        "// Source: src/scenes/Scene*.anchors.json\n\n"
        "const REGISTERED: Record<string, number> = {\n"
        + "\n".join(body_lines)
        + "\n};\n\n"
        "export function resolveAnchor(id: string): number | null {\n"
        "  return id in REGISTERED ? REGISTERED[id] : null;\n"
        "}\n"
    )
    (project_dir / "src" / "anchors.ts").write_text(content)
    return len(merged)


def scenes_owning_anchors(anchor_ids: list[str]) -> list[str]:
    """
    Map a list of failing anchor ids back to their scene ids.

    Anchor ids follow the pattern `sceneN.<name>` by contract.
    """
    owners: set[str] = set()
    for aid in anchor_ids:
        head = aid.split(".", 1)[0]
        owners.add(head)
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


async def run_phase_b_scene(
    scene_id: str, project_dir: Path, model: str
) -> tuple[str, str]:
    """One scene agent, scoped to its own files."""
    # Scene id is "scene1", "scene2", ... The numeric suffix drives filenames.
    suffix = scene_id.replace("scene", "")
    allowed_writes = [
        f"Write(src/scenes/Scene{suffix}.tsx)",
        f"Edit(src/scenes/Scene{suffix}.tsx)",
        f"Write(src/scenes/Scene{suffix}.anchors.json)",
        f"Edit(src/scenes/Scene{suffix}.anchors.json)",
        "Edit(scene_status.json)",
    ]

    client = _build_client(
        project_dir=project_dir,
        model=model,
        system_prompt=(
            f"You are the scene agent for {scene_id}. "
            "Write only your scene's component and anchors.json. "
            "Do not touch other scenes, Root.tsx, or timing.json."
        ),
        allowed_writes=allowed_writes,
    )
    prompt = _load_prompt("scene_prompt.md") + f"\n\n## SCENE_ID\n\n{scene_id}\n"
    async with client:
        status, response = await run_agent_session(client, prompt, project_dir)
    return status, response


async def run_phase_b(project_dir: Path, model: str, max_retries: int) -> None:
    """
    Parallel scene agents, followed by anchor stitching + alignment test.
    Failing anchors re-queue only the owning scenes.
    """
    print("\n" + "=" * 70)
    print("  PHASE B — Scene components (parallel)")
    print("=" * 70 + "\n")

    script = json.loads((project_dir / "script.json").read_text())
    scene_ids = [s["id"] for s in script["scenes"]]
    pending = list(scene_ids)

    # Alignment test is written before Phase B so scene agents can see it.
    generate_alignment_test(project_dir, project_dir / "timing.json")

    for attempt in range(max_retries + 1):
        if not pending:
            break
        print(f"[phase B] attempt {attempt + 1}: running {len(pending)} scene(s) in parallel")
        results = await asyncio.gather(
            *(run_phase_b_scene(sid, project_dir, model) for sid in pending),
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

        # Figure out which scenes own the failing anchors and retry them.
        bad_scenes = scenes_owning_anchors(result.failures)
        if not bad_scenes:
            raise RuntimeError(
                "Alignment test failed but no owning scenes could be identified. "
                f"Failures: {result.failures}\nstderr: {result.stderr[:500]}"
            )
        print(f"[phase B] retrying scenes with alignment failures: {bad_scenes}")
        pending = bad_scenes

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

    # Phase A: director agent → script.json
    await run_phase_a(project_dir, args.model)

    # Driver: TTS → audio.mp3 + timing.json
    narrations = load_narrations_from_script(project_dir / "script.json")
    synthesize_script(narrations, project_dir, fps=args.fps)

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
