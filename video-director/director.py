"""
video-director — Remotion one-shot harness.

Pipeline:

  Phase 0  Spec Refactor            (1 agent) brief.md → video_spec.xml
  Phase A  Director                 (1 agent) video_spec.xml → script.json
  TTS      ElevenLabs + phrase cut  (code)    script.json → audio.mp3 + timing.json
  Phase PE Translation Prompt Eng.  (1 agent) everything → shot_instructions/Shot{NN}.md
  Phase B  Shot agents              (N parallel, max 5 concurrent)
                                    each reads its own instruction file,
                                    writes src/shots/Shot{NN}.tsx + anchors
  Phase C  Compositor               (1 agent + render retry) Root.tsx + mp4

Each shot agent has full access to its own instruction brief from the
PE, the remotion-best-practices skill in docs/remotion-rules/, and an
on-demand image fetcher at tools/fetch_image.py (Pexels → Pixabay →
Wikipedia, with U2-Net small saliency post-processing).

Usage:
    python video-director/director.py \\
        --brief /tmp/my-video/brief.md \\
        --out /tmp/my-video/project

Requires in env: CLAUDE_CODE_OAUTH_TOKEN, ELEVENLABS_API_KEY, PEXELS_API_KEY.
Optional: ELEVENLABS_VOICE_ID, PIXABAY_API_KEY.
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
        # Minimal visual toolkit — required by the composition catalog
        # in prompts/shot_prompt.md (shapes for primitives, google-fonts
        # for the full_bleed_headline layout and typographic heroes).
        "@remotion/shapes": "^4.0.0",
        "@remotion/google-fonts": "^4.0.0",
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

REMOTION_SKILL_DIR = (
    Path.home() / ".claude" / "skills" / "remotion-best-practices" / "rules"
)


def _copy_remotion_skill(project_dir: Path) -> int:
    """
    Copy the FULL remotion-best-practices rule set into
    project_dir/docs/remotion-rules/. Shot agents have Read scoped to
    project_dir only, so the link in shot_prompt.md would be broken
    without this.

    Also generates an INDEX.md so agents can survey the catalog without
    a full glob.
    """
    dest = project_dir / "docs" / "remotion-rules"
    dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    rule_names: list[str] = []
    if REMOTION_SKILL_DIR.exists():
        for src in sorted(REMOTION_SKILL_DIR.glob("*.md")):
            shutil.copy(src, dest / src.name)
            copied += 1
            rule_names.append(src.name)
        # Copy the assets subdirectory too (tsx recipes).
        assets_src = REMOTION_SKILL_DIR / "assets"
        if assets_src.exists():
            assets_dest = dest / "assets"
            assets_dest.mkdir(exist_ok=True)
            for src in assets_src.iterdir():
                if src.is_file():
                    shutil.copy(src, assets_dest / src.name)

    # Write an index so agents can see the catalog.
    index_lines = [
        "# Remotion technique rules — FULL catalog",
        "",
        "This directory holds every rule from the remotion-best-practices",
        "skill. Open any file that matches your shot's ambition. Prefer",
        "high-level techniques over hand-rolled SVG.",
        "",
    ]
    for name in rule_names:
        index_lines.append(f"- `{name}`")
    (dest / "INDEX.md").write_text("\n".join(index_lines) + "\n")
    return copied


def _copy_design_skill(project_dir: Path) -> None:
    """Copy prompts/remotion_design_skill.md → project_dir/docs/remotion-design-skill.md"""
    src = PHASE_PROMPTS / "remotion_design_skill.md"
    if src.exists():
        dest = project_dir / "docs" / "remotion-design-skill.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest)


def _copy_showcase_examples(project_dir: Path) -> None:
    """Copy prompts/showcase_examples.md → project_dir/docs/showcase-examples.md.

    This is the scraped remotion.dev/prompts showcase — the PE uses it as
    a reference library of known-great prompts when writing per-shot briefs.
    Shot agents do not read it; only the PE does.
    """
    src = PHASE_PROMPTS / "showcase_examples.md"
    if src.exists():
        dest = project_dir / "docs" / "showcase-examples.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest)


def _copy_tools(project_dir: Path) -> None:
    """Copy every script in video-director/tools/ → project_dir/tools/.

    Includes:
      - fetch_image.py       (Pexels → Pixabay → Wikipedia + U2-Net saliency)
      - get_shot_timing.py   (authoritative timing block for the PE)
    """
    src_dir = _HERE / "tools"
    if not src_dir.exists():
        return
    dest_dir = project_dir / "tools"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for src in src_dir.glob("*.py"):
        dest = dest_dir / src.name
        shutil.copy(src, dest)
        dest.chmod(0o755)


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

    n_rules = _copy_remotion_skill(project_dir)
    _copy_design_skill(project_dir)
    _copy_showcase_examples(project_dir)
    _copy_tools(project_dir)
    (project_dir / "shot_instructions").mkdir(parents=True, exist_ok=True)
    print(
        f"[scaffold] Remotion skeleton + {n_rules} rules + design skill + "
        f"showcase + fetch_image.py written to {project_dir}"
    )

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


def _authoritative_timing_block(project_dir: Path, shot_id: str) -> str:
    """
    Run tools/get_shot_timing.py via in-process import and return its
    output. This is the single source of truth for phrase text, frame
    window, and anchor contract. Shot agents never see anything else.
    """
    import importlib.util

    tool_path = project_dir / "tools" / "get_shot_timing.py"
    if not tool_path.exists():
        raise RuntimeError(f"get_shot_timing.py not scaffolded at {tool_path}")

    # Load the scaffold-copied script as a module and call its
    # render_timing_block() directly (avoids spawning a subprocess).
    spec = importlib.util.spec_from_file_location("_get_shot_timing", tool_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.render_timing_block(project_dir, shot_id)


def _splice_authoritative_timing_into_brief(
    project_dir: Path, shot_id: str
) -> None:
    """
    Guarantee the per-shot brief starts with the authoritative timing
    block. If the PE wrote its own `## The phrase` / `## Frame window` /
    `## Anchor contract` sections, replace them with the canonical
    output of get_shot_timing.py. If it didn't, prepend the canonical
    block.

    This is the belt-and-suspenders for the one hard rule: frame marks
    cannot miss.
    """
    import re

    suffix = _shot_suffix(shot_id)
    brief_path = project_dir / "shot_instructions" / f"Shot{suffix}.md"
    if not brief_path.exists():
        return

    authoritative = _authoritative_timing_block(project_dir, shot_id).strip() + "\n"
    body = brief_path.read_text()

    # Strip any existing authoritative sections the PE might have written.
    # We remove everything from the first `## The phrase`, `## Frame window`,
    # or `## Anchor contract` heading up until (but not including) the next
    # heading that is NOT one of those three.
    authoritative_headings = {"## The phrase", "## Frame window", "## Anchor contract"}
    lines = body.splitlines()
    stripped: list[str] = []
    skipping = False
    for line in lines:
        if line.startswith("## ") and line.strip() in authoritative_headings:
            skipping = True
            continue
        if skipping and line.startswith("## ") and line.strip() not in authoritative_headings:
            skipping = False
        if not skipping:
            stripped.append(line)

    stripped_body = "\n".join(stripped).lstrip()
    # Also drop any leading H1 the PE wrote before we prepend — we'll
    # put a fresh H1 in front.
    header_match = re.match(r"^# [^\n]*\n+", stripped_body)
    if header_match:
        stripped_body = stripped_body[header_match.end():]

    new_body = (
        f"# Shot{suffix} — Brief\n\n"
        + authoritative
        + "\n"
        + stripped_body.rstrip()
        + "\n"
    )
    brief_path.write_text(new_body)


async def run_phase_prompt_engineer(project_dir: Path, model: str) -> None:
    """
    Phase PE — Translation Prompt Engineer.

    One Claude instance that reads the full project context (spec,
    script, timing, design skill, rules catalog, scraped showcase) and
    writes a lean, concrete, bold per-shot brief to
    <project_dir>/shot_instructions/Shot{NN}.md for every shot.

    After the PE finishes, Python re-splices the authoritative timing
    block (from tools/get_shot_timing.py) into every brief, overwriting
    any timing/phrase/anchor content the PE wrote. This makes the one
    hard rule — frame integrity — literally impossible for the PE to
    break, regardless of prompt discipline.

    Downstream shot agents then receive their brief (authoritative
    timing block + creative direction) appended to the standard
    shot_prompt.md and just execute it.
    """
    print("\n" + "=" * 70)
    print("  PHASE PE — Translation Prompt Engineer")
    print("=" * 70 + "\n")

    instr_dir = project_dir / "shot_instructions"
    instr_dir.mkdir(parents=True, exist_ok=True)

    client = _build_client(
        project_dir=project_dir,
        model=model,
        system_prompt=(
            "You are a translation prompt engineer and art director. "
            "Read the project context. For every shot, first run "
            "`python tools/get_shot_timing.py <shot_id>` via Bash and paste "
            "its stdout verbatim at the top of the brief. Then write the "
            "creative direction below. Write to shot_instructions/Shot{NN}.md."
        ),
        allowed_writes=["Write(shot_instructions/**)", "Edit(shot_instructions/**)"],
    )
    prompt = _load_prompt("prompt_engineer_prompt.md")
    async with client:
        status, _ = await run_agent_session(client, prompt, project_dir)
    if status != "continue":
        raise RuntimeError("Phase PE (prompt engineer) failed")

    # Validate every brief exists AND splice in the authoritative timing.
    timing = json.loads((project_dir / "timing.json").read_text())
    expected = [s["id"] for s in timing.get("shots", [])]
    missing: list[str] = []
    for shot_id in expected:
        suffix = _shot_suffix(shot_id)
        brief_path = instr_dir / f"Shot{suffix}.md"
        if not brief_path.exists() or brief_path.stat().st_size == 0:
            missing.append(shot_id)
            continue
        _splice_authoritative_timing_into_brief(project_dir, shot_id)
    if missing:
        raise RuntimeError(
            f"Phase PE did not produce briefs for: {missing}. "
            f"Check prompt_engineer output above."
        )
    print(
        f"[PE] wrote {len(expected)} per-shot briefs with authoritative "
        f"timing blocks spliced in"
    )


async def run_phase_b_shot(
    shot_id: str,
    project_dir: Path,
    model: str,
    semaphore: asyncio.Semaphore,
) -> tuple[str, str]:
    """
    One shot agent, scoped to its own files. Receives shot_prompt.md
    plus its per-shot brief (written by Phase PE) appended at the bottom.
    """
    suffix = _shot_suffix(shot_id)
    allowed_writes = [
        f"Write(src/shots/Shot{suffix}.tsx)",
        f"Edit(src/shots/Shot{suffix}.tsx)",
        f"Write(src/shots/Shot{suffix}.anchors.json)",
        f"Edit(src/shots/Shot{suffix}.anchors.json)",
        # Shot agents need to write their fetched images into public/assets/
        # via tools/fetch_image.py.
        "Write(public/assets/**)",
        "Edit(public/assets/**)",
    ]

    # Load the custom brief the prompt engineer wrote for this shot.
    brief_path = project_dir / "shot_instructions" / f"Shot{suffix}.md"
    brief_text = brief_path.read_text() if brief_path.exists() else (
        "(no brief found — improvise within the hard constraints above)"
    )

    async with semaphore:
        client = _build_client(
            project_dir=project_dir,
            model=model,
            system_prompt=(
                f"You are the shot agent for {shot_id}. Read your brief, "
                "execute it. Frame integrity and anchor contract are "
                "non-negotiable. Never touch other shots, Root.tsx, "
                "anchors.ts, or timing.json."
            ),
            allowed_writes=allowed_writes,
        )
        prompt = (
            _load_prompt("shot_prompt.md")
            + f"\n\n## SHOT_ID\n\n{shot_id}\n"
            + f"\n\n## SHOT_INSTRUCTIONS\n\n{brief_text}\n"
        )
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


def _extract_broken_shots_from_text(text: str) -> list[str]:
    """
    Find references like 'Shot08.tsx' or 'shot08' or 'shots/Shot08' in
    error output. Returns a sorted unique list of shot ids
    (e.g. ['shot08']).
    """
    import re

    found: set[str] = set()
    # Match Shot<digits>.tsx
    for m in re.finditer(r"Shot0*(\d+)\.tsx", text):
        n = int(m.group(1))
        found.add(f"shot{n:02d}")
    # Match path-style references: src/shots/Shot08
    for m in re.finditer(r"shots/Shot0*(\d+)", text):
        n = int(m.group(1))
        found.add(f"shot{n:02d}")
    return sorted(found)


def _python_render(project_dir: Path) -> tuple[bool, str]:
    """
    Run `pnpm exec remotion render` directly via subprocess. Returns
    (success, captured_output). Used by the Phase C retry loop after a
    minimal-patch agent has fixed a broken shot — we don't need a fresh
    compositor agent to redo Root.tsx, just to retry the render.
    """
    import subprocess

    print("[phase C] retrying render via direct subprocess")
    out_path = project_dir / "out" / "video.mp4"
    proc = subprocess.run(
        [
            "pnpm",
            "exec",
            "remotion",
            "render",
            "src/index.ts",
            "main",
            str(out_path),
        ],
        cwd=project_dir,
        capture_output=True,
        text=True,
        timeout=900,
    )
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if proc.returncode == 0 and out_path.exists():
        return True, output
    return False, output


async def run_shot_patch(
    project_dir: Path,
    model: str,
    shot_id: str,
    error_excerpt: str,
) -> None:
    """
    Spawn a fresh Claude scoped to Edit a single shot file with a
    minimal patch. The patch agent reads the error message and the
    shot file, makes the smallest possible edit, and stops.
    """
    suffix = _shot_suffix(shot_id)
    print(f"[phase C] spawning patch agent for {shot_id}")

    client = _build_client(
        project_dir=project_dir,
        model=model,
        system_prompt=(
            f"You are a minimal-patch agent for {shot_id}. "
            "Read the error, read the shot file, make the smallest "
            "possible edit. Preserve the visual concept."
        ),
        allowed_writes=[
            f"Edit(src/shots/Shot{suffix}.tsx)",
        ],
    )
    base_prompt = _load_prompt("shot_patch_prompt.md")
    # Trim error excerpt to the most relevant ~3000 chars so the prompt
    # doesn't balloon.
    excerpt = error_excerpt[-3000:] if len(error_excerpt) > 3000 else error_excerpt
    prompt = (
        base_prompt
        + f"\n\n## SHOT_ID\n\n{shot_id}\n\n## ERROR_EXCERPT\n\n```\n{excerpt}\n```\n"
    )
    async with client:
        status, _ = await run_agent_session(client, prompt, project_dir)
    if status != "continue":
        print(f"[phase C] patch agent for {shot_id} did not return cleanly")


async def run_phase_c(project_dir: Path, model: str, max_render_retries: int = 3) -> None:
    """
    Compositor: writes Root.tsx, runs alignment test, renders.

    On render failure, parses the captured output for broken shot
    files, spawns a minimal-patch agent for each, then retries the
    render directly via subprocess (no full compositor re-run).
    """
    print("\n" + "=" * 70)
    print("  PHASE C — Compositor")
    print("=" * 70 + "\n")

    client = _build_client(
        project_dir=project_dir,
        model=model,
        system_prompt=(
            "You are the compositor. Assemble shots into Root.tsx, "
            "verify alignment, and render. Never edit shot components."
        ),
    )
    prompt = _load_prompt("compositor_prompt.md")
    async with client:
        status, response = await run_agent_session(client, prompt, project_dir)
    if status != "continue":
        raise RuntimeError("Phase C (compositor) failed")

    out_path = project_dir / "out" / "video.mp4"
    if out_path.exists():
        print(f"\n[done] rendered {out_path}")
        return

    # Compositor finished but no video. Enter the patch + retry loop.
    last_output = response
    for attempt in range(1, max_render_retries + 1):
        broken = _extract_broken_shots_from_text(last_output)
        if not broken:
            raise RuntimeError(
                f"Phase C: render failed and no broken shot files could be "
                f"identified.\nLast output tail:\n{last_output[-1500:]}"
            )

        print(f"[phase C] retry {attempt}/{max_render_retries}: broken shots = {broken}")
        for shot_id in broken:
            await run_shot_patch(project_dir, model, shot_id, last_output)

        ok, last_output = _python_render(project_dir)
        if ok:
            print(f"\n[done] rendered {out_path} (after {attempt} patch retry/retries)")
            return

    raise RuntimeError(
        f"Phase C exhausted {max_render_retries} patch retries.\n"
        f"Last output tail:\n{last_output[-1500:]}"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _preflight() -> None:
    missing = [
        var
        for var in ("CLAUDE_CODE_OAUTH_TOKEN", "ELEVENLABS_API_KEY", "PEXELS_API_KEY")
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

    # Phase A: director agent → script.json (continuous narration + phrases)
    await run_phase_a(project_dir, args.model)

    # Driver: TTS → audio.mp3 + timing.json (anchors + shot frames)
    script = load_script(project_dir / "script.json")
    synthesize_script(script, project_dir, fps=args.fps)

    # Phase PE: translation prompt engineer reads everything and
    # writes shot_instructions/Shot{NN}.md for each shot.
    await run_phase_prompt_engineer(project_dir, args.model)

    # Phase B: parallel shot agents. Each reads its custom brief
    # appended to shot_prompt.md. On-demand Pexels fetches via
    # tools/fetch_image.py. No central catalog → no adjacent-collision
    # coordination needed (the PE prescribes different techniques
    # per adjacent shot up-front).
    await run_phase_b(project_dir, args.model, max_retries=args.max_scene_retries)

    # Phase C: compositor → render (with patch retry on render failure)
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
