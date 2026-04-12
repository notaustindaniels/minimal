"""
Video harness security hook.

Extends the autonomous-coding allowlist with the commands Remotion + TTS
workflows need: `npx` (for `npx remotion`, `npx vitest`), `pnpm`, `ffmpeg`,
`ffprobe`. The hook itself is the same allowlist-enforcing implementation
from autonomous-coding/security.py — we just widen the allowed set.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# Load autonomous-coding/security.py by absolute path so it doesn't collide
# with this module's own name on sys.path.
_BASE_PATH = (
    Path(__file__).resolve().parent.parent / "autonomous-coding" / "security.py"
)
_spec = importlib.util.spec_from_file_location("autonomous_coding_security", _BASE_PATH)
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)


# Extend the base allowlist in place so the shared hook picks up the new
# commands. This is safe because video-director runs in its own process.
_VIDEO_EXTRA_COMMANDS = {
    "npx",      # npx remotion render, npx vitest run
    "pnpm",     # dependency install (preferred over npm in this repo)
    "ffmpeg",   # audio/video muxing, format conversion
    "ffprobe",  # inspecting durations, stream metadata
    "find",     # locating generated assets
    "mv",       # moving rendered outputs into place
}

_base.ALLOWED_COMMANDS.update(_VIDEO_EXTRA_COMMANDS)


# Re-export the hook so video client code can import from one place.
bash_security_hook = _base.bash_security_hook
ALLOWED_COMMANDS = _base.ALLOWED_COMMANDS
