"""
Alignment test runner — the enforcement half of "every frame lands on its mark".

In the shot-list model, the test verifies two contracts:

  1. Every anchor declared in timing.json is registered in src/anchors.ts
     within ±1 frame of its declared frame. (Each anchor has an owning
     `shot` that the Phase B agent for that shot is responsible for
     placing the keyframe.)

  2. Every shot declared in timing.json has a Shot{N}.tsx component file.
     The shot's start/end frames are placed by the compositor at Root
     level, but the file's existence is the proof that the shot agent
     ran. We don't unit-test the visuals.

The generated `alignment.test.ts` only encodes contract (1) — it imports
timing.json and src/anchors.ts and asserts every anchor resolves. The
shot-existence check happens in Python (validator.run_alignment_test
verifies file presence before invoking vitest).
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


TOLERANCE_FRAMES = 1


@dataclass
class ValidationResult:
    passed: bool
    total: int
    failures: list[str] = field(default_factory=list)
    missing_shots: list[str] = field(default_factory=list)
    stderr: str = ""

    def summary(self) -> str:
        if self.passed:
            return f"alignment: {self.total}/{self.total} anchors within ±{TOLERANCE_FRAMES} frame"
        bits = []
        if self.failures:
            bits.append(
                f"{self.total - len(self.failures)}/{self.total} anchors passing — "
                f"{len(self.failures)} off-target"
            )
        if self.missing_shots:
            bits.append(f"{len(self.missing_shots)} shot file(s) missing")
        return "alignment: " + "; ".join(bits) if bits else "alignment: failed"


def generate_alignment_test(project_dir: Path, timing_path: Path) -> Path:
    """Write alignment.test.ts into the project."""
    test_path = project_dir / "alignment.test.ts"
    test_path.write_text(
        f"""import {{ describe, test, expect }} from "vitest";
import timing from "./timing.json";
import {{ resolveAnchor }} from "./src/anchors";

const TOLERANCE = {TOLERANCE_FRAMES};

describe("frame alignment invariant", () => {{
  for (const anchor of timing.anchors) {{
    test(`${{anchor.id}} lands within ±${{TOLERANCE}} frame of ${{anchor.frame}}`, () => {{
      const actual = resolveAnchor(anchor.id);
      expect(actual, `anchor ${{anchor.id}} is not registered in src/anchors.ts`).not.toBeNull();
      expect(Math.abs((actual as number) - anchor.frame)).toBeLessThanOrEqual(TOLERANCE);
    }});
  }}
}});
"""
    )
    return test_path


def _check_shot_files(project_dir: Path, timing: dict) -> list[str]:
    """Return shot ids whose .tsx file is missing."""
    shots_dir = project_dir / "src" / "shots"
    missing = []
    for shot in timing.get("shots", []):
        sid = shot["id"]
        # shot01 → Shot01.tsx
        suffix = sid.replace("shot", "").lstrip("0") or "0"
        path_a = shots_dir / f"Shot{sid.replace('shot', '').zfill(2)}.tsx"
        path_b = shots_dir / f"Shot{suffix}.tsx"
        if not path_a.exists() and not path_b.exists():
            missing.append(sid)
    return missing


def run_alignment_test(project_dir: Path) -> ValidationResult:
    """
    Run the alignment test plus a Python-side check that every shot file
    exists. Returns a unified ValidationResult.
    """
    timing = json.loads((project_dir / "timing.json").read_text())
    total = len(timing.get("anchors", []))

    missing_shots = _check_shot_files(project_dir, timing)

    proc = subprocess.run(
        ["npx", "vitest", "run", "alignment.test.ts", "--reporter=verbose"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    stdout = proc.stdout
    stderr = proc.stderr

    failures: list[str] = []
    if proc.returncode != 0:
        patterns = [
            re.compile(r">\s*(\S+)\s+lands within"),    # vitest verbose
            re.compile(r"[×✗]\s+(\S+)\s+lands within"),  # alt symbol form
        ]
        # Vitest splits output across stdout and stderr depending on the
        # reporter and the kind of message. Search both.
        for line in (stdout + "\n" + stderr).splitlines():
            for pat in patterns:
                m = pat.search(line)
                if m:
                    failures.append(m.group(1))
                    break
        # Dedupe, preserve order
        seen = set()
        ordered = []
        for f in failures:
            if f not in seen:
                seen.add(f)
                ordered.append(f)
        failures = ordered

    passed = proc.returncode == 0 and not missing_shots
    combined_tail = ((stderr or "") + "\n" + (stdout or ""))[-2000:]
    return ValidationResult(
        passed=passed,
        total=total,
        failures=failures,
        missing_shots=missing_shots,
        stderr=combined_tail if not passed else "",
    )
