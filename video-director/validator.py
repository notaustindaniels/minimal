"""
Alignment test runner — the enforcement half of "every frame lands on its mark".

Phase A writes `alignment.test.ts` into the project. This module runs it via
vitest and parses results so director.py can gate Phase B and Phase C on a
green test run.

The test file is generated (not hand-written) so its shape is known: one
test per anchor in timing.json, each asserting the component's actual frame
is within ±1 frame of the declared anchor frame.
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
    stderr: str = ""

    def summary(self) -> str:
        if self.passed:
            return f"alignment: {self.total}/{self.total} anchors within ±{TOLERANCE_FRAMES} frame"
        return (
            f"alignment: {self.total - len(self.failures)}/{self.total} passing — "
            f"{len(self.failures)} off-target"
        )


def generate_alignment_test(project_dir: Path, timing_path: Path) -> Path:
    """
    Write alignment.test.ts into the project.

    The generated test imports timing.json and the Remotion composition,
    then asserts every anchor resolves to the declared frame within tolerance.
    Scene components must expose an `anchors` export mapping anchor id →
    actual frame used by the component (a keyframe, a Sequence `from`, etc.).
    This is the contract Phase B scene agents must satisfy.
    """
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


def run_alignment_test(project_dir: Path) -> ValidationResult:
    """
    Run `npx vitest run alignment.test.ts` and parse the result.

    vitest's default reporter prints a passing count line and one `FAIL`
    line per failing test. That's enough to build a ValidationResult.
    """
    timing = json.loads((project_dir / "timing.json").read_text())
    total = len(timing.get("anchors", []))

    proc = subprocess.run(
        ["npx", "vitest", "run", "alignment.test.ts", "--reporter=verbose"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    stdout = proc.stdout
    stderr = proc.stderr

    if proc.returncode == 0:
        return ValidationResult(passed=True, total=total, stderr=stderr)

    # Collect failing anchor ids from vitest output. Vitest 1.x verbose
    # reporter prints either:
    #   FAIL  alignment.test.ts > frame alignment invariant > scene1.start lands within ±1 frame of 0
    # or:
    #   × scene1.start lands within ±1 frame of 0
    # We accept either form.
    failures = []
    patterns = [
        re.compile(r"FAIL\s+\S+.*?>\s*(\S+)\s+lands within"),
        re.compile(r"[×✗]\s+(\S+)\s+lands within"),
    ]
    for line in stdout.splitlines():
        for pat in patterns:
            m = pat.search(line)
            if m:
                failures.append(m.group(1))
                break
    # Dedupe, preserve order.
    seen = set()
    ordered_failures = []
    for f in failures:
        if f not in seen:
            seen.add(f)
            ordered_failures.append(f)

    return ValidationResult(
        passed=False,
        total=total,
        failures=ordered_failures,
        stderr=stderr or stdout[-2000:],
    )
