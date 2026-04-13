"""
ElevenLabs TTS + alignment → audio.mp3, timing.json (phrase-cut model).

Phase A writes a continuous narration string AND tags phrase boundaries
with editorial intent (`role: shot` or `role: transition`). This module:

  1. Sends the full narration to ElevenLabs in one call
  2. Receives audio.mp3 + per-character alignment data
  3. Resolves each phrase's char range to a frame range
  4. Emits one Remotion shot per phrase, complexity tag derived from
     duration + role
  5. Resolves any anchors from script.json to frames + binds them to
     whichever shot's frame range contains them

NO captions. Phase A's phrasing decisions ARE the storyboard.

Schema of timing.json:
{
  "fps": 30,
  "audio_path": "public/audio.mp3",
  "total_frames": 2325,
  "anchors": [
    {"id": "anchor.hovering", "frame": 850, "shot": "shot07"}
  ],
  "shots": [
    {
      "id": "shot01",
      "role": "shot",          // from Phase A
      "complexity": "complex", // derived from duration + role
      "start_frame": 0,
      "end_frame": 78,
      "text": "A human heart beats about seventy times per minute."
    },
    ...
  ]
}
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import urllib.request
import urllib.error


ELEVENLABS_API = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel
DEFAULT_MODEL = "eleven_turbo_v2_5"
AUDIO_FILENAME = "audio.mp3"

# Complexity thresholds (seconds), used when role="shot" to derive the
# visual density hint passed to shot agents.
SIMPLE_MAX_SECONDS = 2.5
COMPLEX_MIN_SECONDS = 3.5


class TTSError(RuntimeError):
    pass


def _require_api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise TTSError(
            "ELEVENLABS_API_KEY is not set. Export it in your shell before "
            "running director.py."
        )
    return key


def _voice_id() -> str:
    return os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID)


def _call_elevenlabs(text: str, api_key: str, voice_id: str) -> dict[str, Any]:
    """POST to the with-timestamps endpoint. Returns parsed JSON.

    Response shape (relevant bits):
      audio_base64: base64-encoded MP3 of the spoken text
      alignment: {
        characters: list[str],
        character_start_times_seconds: list[float],
        character_end_times_seconds: list[float],
      }
    """
    url = ELEVENLABS_API.format(voice_id=voice_id)
    payload = json.dumps(
        {
            "text": text,
            "model_id": DEFAULT_MODEL,
        }
    ).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise TTSError(f"ElevenLabs HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise TTSError(f"ElevenLabs request failed: {e.reason}") from e


def _alignment_duration(alignment: dict[str, Any]) -> float:
    ends = alignment.get("character_end_times_seconds") or []
    if ends:
        return float(ends[-1])
    starts = alignment.get("character_start_times_seconds") or []
    return float(starts[-1]) if starts else 0.0


def _char_offset_to_seconds(
    char_offset: int, alignment: dict[str, Any], fallback_duration: float
) -> float:
    """
    Resolve an input-text character offset to a time within the audio.

    ElevenLabs may normalize the input text before alignment, so the
    `characters` array can be a slightly different length than the input.
    Linearly interpolate by ratio so anchors land in the right
    neighborhood even if exact char counts disagree.
    """
    starts: list[float] = alignment.get("character_start_times_seconds") or []
    n = len(starts)
    if n == 0:
        return min(char_offset, 1) * fallback_duration

    aligned_chars = len(alignment.get("characters") or []) or 1
    ratio = max(0.0, min(1.0, char_offset / aligned_chars))
    idx = min(int(round(ratio * (n - 1))), n - 1)
    return float(starts[idx])


def _phrase_char_to_frame(
    char_idx: int, narration: str, alignment_table: list[float], fps: int
) -> int:
    """
    Resolve a character offset in `narration` to a frame using the
    alignment timing table (either start_times or end_times). Uses ratio
    interpolation so it's robust to ElevenLabs text normalization.
    """
    n = len(alignment_table)
    if n == 0:
        return 0
    src_n = max(len(narration), 1)
    ratio = max(0.0, min(1.0, char_idx / src_n))
    idx = min(int(round(ratio * (n - 1))), n - 1)
    return round(float(alignment_table[idx]) * fps)


def _classify_complexity(role: str, duration_seconds: float) -> str:
    """
    Map (Phase A's role tag, actual duration) → visual complexity hint.

    role="transition" always → "transition" regardless of duration.
    role="shot" splits into simple/complex by duration thresholds.
    """
    if role == "transition":
        return "transition"
    if duration_seconds <= SIMPLE_MAX_SECONDS:
        return "simple"
    if duration_seconds >= COMPLEX_MIN_SECONDS:
        return "complex"
    # Middle band: lean simple to keep the rhythm punchy.
    return "simple"


def _resolve_phrase_ranges(
    phrases: list[dict[str, Any]], narration: str
) -> list[tuple[int, int, str]]:
    """
    Resolve each phrase's literal `text` into a (start_char, end_char, role)
    tuple by string-matching against the narration with a cursor.

    Phase A emits phrases as TEXT (not char offsets) because LLMs are
    unreliable at counting indices. We do the index math here, deterministically.

    Rules:
    - phrase[i].text must appear in narration at or after the cursor (the
      end of phrase[i-1]).
    - Whitespace between phrases is allowed and skipped.
    - The first phrase must start at narration[0] (no leading content).
    - The last phrase must end at narration[-1] (no trailing content).

    Raises TTSError on any violation so Phase A retry can fix it.
    """
    if not phrases:
        raise TTSError("script.phrases is empty — Phase A produced no phrase plan")

    out: list[tuple[int, int, str]] = []
    cursor = 0
    for i, p in enumerate(phrases):
        text = (p.get("text") or "").strip()
        role = p.get("role", "shot")
        if not text:
            raise TTSError(f"phrase {i} has empty text")

        # Skip leading whitespace at the cursor.
        while cursor < len(narration) and narration[cursor].isspace():
            cursor += 1

        # Find this phrase's text starting at the cursor. Allow a small
        # leading slack (≤4 chars) in case Phase A added/removed a leading
        # whitespace or punctuation char.
        idx = narration.find(text, cursor)
        if idx == -1 or idx > cursor + 4:
            raise TTSError(
                f"phrase {i} text not found at cursor {cursor}: {text[:60]!r}\n"
                f"  narration tail: {narration[cursor:cursor+80]!r}"
            )
        if i == 0 and idx != 0:
            raise TTSError(
                f"first phrase must start at narration[0], got start={idx}"
            )

        start_char = idx
        end_char = idx + len(text)
        out.append((start_char, end_char, role))
        cursor = end_char

    # The last phrase must reach the end of the narration (allowing trailing whitespace).
    tail = narration[cursor:].strip()
    if tail:
        raise TTSError(
            f"phrases do not cover the full narration; uncovered tail: {tail[:80]!r}"
        )
    return out


def _phrases_to_shots(
    phrases: list[dict[str, Any]],
    narration: str,
    alignment: dict[str, Any],
    total_frames: int,
    fps: int,
) -> list[dict[str, Any]]:
    """
    Convert Phase A's phrase list (text + role) into a contiguous shot
    list with frame ranges. Each phrase becomes exactly one shot. The
    first shot starts at frame 0 and the last ends at total_frames so
    there are no gaps or trailing silence.
    """
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    if not starts or not ends:
        raise TTSError("ElevenLabs returned no alignment data — cannot derive shots")

    resolved = _resolve_phrase_ranges(phrases, narration)

    shots: list[dict[str, Any]] = []
    for i, (start_char, end_char, role) in enumerate(resolved):
        text = narration[start_char:end_char].strip()

        start_frame = _phrase_char_to_frame(start_char, narration, starts, fps)
        end_frame = _phrase_char_to_frame(end_char, narration, ends, fps)

        # First shot starts at 0; last shot ends at total_frames.
        if i == 0:
            start_frame = 0
        if i == len(resolved) - 1:
            end_frame = total_frames
        if end_frame <= start_frame:
            end_frame = start_frame + 1

        duration = (end_frame - start_frame) / fps
        complexity = _classify_complexity(role, duration)

        shots.append(
            {
                "id": f"shot{i + 1:02d}",
                "role": role,
                "complexity": complexity,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "text": text,
            }
        )

    # Stitch boundaries: each shot's end equals the next shot's start so
    # there are no single-frame gaps from rounding.
    for i in range(len(shots) - 1):
        shots[i]["end_frame"] = shots[i + 1]["start_frame"]
        if shots[i]["end_frame"] <= shots[i]["start_frame"]:
            shots[i]["end_frame"] = shots[i]["start_frame"] + 1
    if shots:
        shots[-1]["end_frame"] = total_frames

    return shots


def synthesize_script(
    script: dict[str, Any],
    out_dir: Path,
    fps: int = 30,
) -> dict[str, Any]:
    """
    Generate audio.mp3 + timing.json from a parsed script.json.

    `script` shape:
      {
        "fps": 30,
        "narration": "Continuous voiceover string.",
        "phrases": [{"role": "shot|transition", "start_char": int, "end_char": int}],
        "anchors": [{"id": "...", "char_offset": int}]   # optional
      }

    Returns the timing dict that was written.
    """
    api_key = _require_api_key()
    voice_id = _voice_id()

    narration = script.get("narration") or ""
    if not narration.strip():
        raise TTSError("script.narration is empty — Phase A produced no voiceover")

    phrases_in = script.get("phrases") or []
    if not phrases_in:
        raise TTSError("script.phrases is empty — Phase A produced no phrase plan")

    anchors_in = script.get("anchors") or []

    public_dir = out_dir / "public"
    public_dir.mkdir(parents=True, exist_ok=True)
    audio_path = public_dir / AUDIO_FILENAME

    print(f"[tts] synthesizing {len(narration)} chars of narration")
    resp = _call_elevenlabs(narration, api_key, voice_id)

    audio_b64 = resp.get("audio_base64") or resp.get("audio")
    if not audio_b64:
        raise TTSError("ElevenLabs returned no audio")
    audio_path.write_bytes(base64.b64decode(audio_b64))

    alignment = resp.get("alignment") or {}
    total_seconds = _alignment_duration(alignment)
    if total_seconds <= 0:
        raise TTSError("ElevenLabs returned no usable alignment data")
    total_frames = round(total_seconds * fps)

    # Phase A's phrases drive the shot list directly.
    shots_out = _phrases_to_shots(phrases_in, narration, alignment, total_frames, fps)

    # Resolve anchors against the continuous narration and bind each to
    # whichever shot's frame range contains it.
    def _shot_containing(frame: int) -> str | None:
        for s in shots_out:
            if s["start_frame"] <= frame < s["end_frame"]:
                return s["id"]
        return shots_out[-1]["id"] if shots_out else None

    anchors_out: list[dict[str, Any]] = []
    for a in anchors_in:
        seconds = _char_offset_to_seconds(int(a["char_offset"]), alignment, total_seconds)
        frame = max(0, min(total_frames, round(seconds * fps)))
        anchors_out.append(
            {
                "id": a["id"],
                "frame": frame,
                "shot": _shot_containing(frame),
            }
        )

    timing = {
        "fps": fps,
        "audio_path": f"public/{AUDIO_FILENAME}",
        "total_frames": total_frames,
        "anchors": sorted(anchors_out, key=lambda a: a["frame"]),
        "shots": shots_out,
    }

    n_shots = sum(1 for s in shots_out if s["role"] == "shot")
    n_trans = sum(1 for s in shots_out if s["role"] == "transition")
    timing_path = out_dir / "timing.json"
    timing_path.write_text(json.dumps(timing, indent=2))
    print(
        f"[tts] wrote {audio_path} ({total_seconds:.2f}s, {total_frames} frames), "
        f"{len(anchors_out)} anchors, {len(shots_out)} cuts ({n_shots} shots + {n_trans} transitions)"
    )
    return timing


def load_script(script_path: Path) -> dict[str, Any]:
    """Load and validate the Phase A script.json."""
    data = json.loads(script_path.read_text())
    if "narration" not in data:
        raise TTSError("script.json missing 'narration'")
    if "phrases" not in data:
        raise TTSError("script.json missing 'phrases'")
    data.setdefault("anchors", [])
    return data
