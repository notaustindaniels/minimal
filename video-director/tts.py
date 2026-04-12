"""
ElevenLabs TTS + alignment → audio.mp3, timing.json (continuous-narration model).

This module is responsible for converting Phase A's `script.json` (one
continuous narration string + anchor list + shot list) into:

  - public/audio.mp3   — the spoken voiceover, one continuous track
  - timing.json        — frame-accurate metadata: anchors resolved to
                          frames, shot frame ranges (scaled to fit the
                          actual audio length), and a caption layer
                          derived from per-character alignment data.

Schema of timing.json:
{
  "fps": 30,
  "audio_path": "public/audio.mp3",
  "total_frames": 2325,
  "anchors": [
    {"id": "hook",      "frame": 42,   "shot": "shot02"},
    {"id": "punchline", "frame": 1140, "shot": "shot07"}
  ],
  "shots": [
    {"id": "shot01", "complexity": "complex",    "start_frame": 0,   "end_frame": 180},
    {"id": "shot02", "complexity": "transition", "start_frame": 180, "end_frame": 195},
    ...
  ],
  "captions": [
    {"text": "Airline economics are dominated by",  "start_frame": 0,  "end_frame": 51},
    {"text": "fixed costs that don't go away.",      "start_frame": 51, "end_frame": 96},
    ...
  ]
}
"""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

import urllib.request
import urllib.error


ELEVENLABS_API = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel
DEFAULT_MODEL = "eleven_turbo_v2_5"
AUDIO_FILENAME = "audio.mp3"

# Caption grouping target: emit a new caption every N words OR at any
# punctuation that ends a clause. Six words is a comfortable read for
# captions overlaid on motion graphics.
CAPTION_TARGET_WORDS = 6
CAPTION_BREAK_PUNCT = set(".!?,;:—")


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


def _derive_captions(
    narration: str, alignment: dict[str, Any], fps: int
) -> list[dict[str, Any]]:
    """
    Group the narration into caption-sized chunks (one per ~6 words or
    until a clause-ending punctuation), and resolve their start/end frame
    from the alignment data.
    """
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    if not starts or not ends:
        return []

    aligned_n = len(starts)
    src_n = len(narration)
    if src_n == 0:
        return []

    def char_time(idx: int, table: list[float]) -> float:
        ratio = max(0.0, min(1.0, idx / src_n))
        ai = min(int(round(ratio * (aligned_n - 1))), aligned_n - 1)
        return float(table[ai])

    word_pattern = re.compile(r"\S+")
    word_spans = [(m.start(), m.end()) for m in word_pattern.finditer(narration)]
    if not word_spans:
        return []

    captions: list[dict[str, Any]] = []
    chunk: list[tuple[int, int]] = []
    for span in word_spans:
        chunk.append(span)
        word_text = narration[span[0]:span[1]]
        last_char = word_text[-1] if word_text else ""
        if len(chunk) >= CAPTION_TARGET_WORDS or last_char in CAPTION_BREAK_PUNCT:
            captions.append(_finalize_caption(chunk, narration, char_time, starts, ends, fps))
            chunk = []
    if chunk:
        captions.append(_finalize_caption(chunk, narration, char_time, starts, ends, fps))

    # Snap end_frame[i] = start_frame[i+1] so there's no gap/overlap.
    for i in range(len(captions) - 1):
        captions[i]["end_frame"] = captions[i + 1]["start_frame"]
    if captions:
        last_end = round(_alignment_duration(alignment) * fps)
        captions[-1]["end_frame"] = max(captions[-1]["end_frame"], last_end)
    return captions


def _finalize_caption(
    chunk: list[tuple[int, int]],
    narration: str,
    char_time,
    starts: list[float],
    ends: list[float],
    fps: int,
) -> dict[str, Any]:
    first_char = chunk[0][0]
    last_char = chunk[-1][1] - 1
    text = narration[first_char : chunk[-1][1]].strip()
    return {
        "text": text,
        "start_frame": round(char_time(first_char, starts) * fps),
        "end_frame": round(char_time(last_char, ends) * fps),
    }


def _scale_shots(
    shots: list[dict[str, Any]], total_seconds: float, fps: int
) -> list[dict[str, Any]]:
    """
    Director plans shots with target_seconds. Actual TTS audio is
    `total_seconds`. Scale every shot proportionally so they sum to
    exactly the audio length, snap to whole frames, and have the last
    shot absorb the rounding remainder.
    """
    if not shots:
        return []
    target_total = sum(float(s.get("target_seconds", 0)) for s in shots)
    if target_total <= 0:
        # Fall back: equal split.
        per = total_seconds / len(shots)
        target_total = per * len(shots)
        for s in shots:
            s["target_seconds"] = per

    scale = total_seconds / target_total
    out: list[dict[str, Any]] = []
    cursor_frame = 0
    for i, shot in enumerate(shots):
        scaled_seconds = float(shot["target_seconds"]) * scale
        if i == len(shots) - 1:
            end_frame = round(total_seconds * fps)
        else:
            end_frame = cursor_frame + max(1, round(scaled_seconds * fps))
        out.append(
            {
                "id": shot["id"],
                "complexity": shot.get("complexity", "simple"),
                "start_frame": cursor_frame,
                "end_frame": end_frame,
            }
        )
        cursor_frame = end_frame
    return out


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
        "anchors": [{"id": "...", "char_offset": int, "shot": "shotNN"}],
        "shots":   [{"id": "...", "complexity": "...", "target_seconds": float, "visual": "..."}]
      }

    Returns the timing dict that was written.
    """
    api_key = _require_api_key()
    voice_id = _voice_id()

    narration = script.get("narration") or ""
    if not narration.strip():
        raise TTSError("script.narration is empty — Phase A produced no voiceover")

    anchors_in = script.get("anchors") or []
    shots_in = script.get("shots") or []
    if not shots_in:
        raise TTSError("script.shots is empty — Phase A produced no shot list")

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

    # Scale shots to fit actual audio duration.
    shots_out = _scale_shots(shots_in, total_seconds, fps)

    # Resolve anchors against the continuous narration, then re-bind each
    # anchor to whichever shot's frame range actually contains it. Phase A
    # assigned anchors to shots based on the planned timeline, but TTS
    # scaling can shift the boundaries — the post-scaling assignment is
    # the source of truth, so the right shot agent owns each anchor.
    def _shot_containing(frame: int) -> str | None:
        for s in shots_out:
            if s["start_frame"] <= frame < s["end_frame"]:
                return s["id"]
        # Anchor at the very last frame — clamp to the final shot.
        return shots_out[-1]["id"] if shots_out else None

    anchors_out: list[dict[str, Any]] = []
    for a in anchors_in:
        seconds = _char_offset_to_seconds(int(a["char_offset"]), alignment, total_seconds)
        frame = max(0, min(total_frames, round(seconds * fps)))
        actual_shot = _shot_containing(frame)
        planned_shot = a.get("shot")
        if planned_shot and actual_shot and planned_shot != actual_shot:
            print(
                f"[tts] anchor {a['id']} reassigned: planned {planned_shot} → "
                f"actual {actual_shot} (frame {frame})"
            )
        anchors_out.append(
            {
                "id": a["id"],
                "frame": frame,
                "shot": actual_shot,
            }
        )

    # Derive captions from per-character alignment.
    captions = _derive_captions(narration, alignment, fps)

    timing = {
        "fps": fps,
        "audio_path": f"public/{AUDIO_FILENAME}",
        "total_frames": total_frames,
        "anchors": sorted(anchors_out, key=lambda a: a["frame"]),
        "shots": shots_out,
        "captions": captions,
    }

    timing_path = out_dir / "timing.json"
    timing_path.write_text(json.dumps(timing, indent=2))
    print(
        f"[tts] wrote {audio_path} ({total_seconds:.2f}s, {total_frames} frames), "
        f"{len(anchors_out)} anchors, {len(shots_out)} shots, {len(captions)} captions"
    )
    return timing


def load_script(script_path: Path) -> dict[str, Any]:
    """Load and validate the Phase A script.json."""
    data = json.loads(script_path.read_text())
    if "narration" not in data:
        raise TTSError("script.json missing 'narration'")
    if "shots" not in data:
        raise TTSError("script.json missing 'shots'")
    data.setdefault("anchors", [])
    return data
