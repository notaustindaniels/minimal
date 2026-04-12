"""
ElevenLabs TTS + alignment → timing.json.

Phase A gate: director.py calls synthesize_script() with a parsed script.json
(list of scenes, each with narration text and anchor ids). This module:

  1. Calls ElevenLabs text-to-speech-with-timestamps for each scene
  2. Concatenates audio to a single audio.wav
  3. Uses the per-character alignment response to compute absolute frames
     for every declared anchor at the project fps
  4. Writes timing.json — the source of truth Phase B scene agents read

timing.json schema:
{
  "fps": 30,
  "audio_path": "public/audio.wav",
  "total_frames": 1800,
  "anchors": [
    {"id": "scene1.start",    "frame": 0,   "seconds": 0.0},
    {"id": "scene1.narration.0", "frame": 12, "seconds": 0.4},
    ...
  ],
  "scenes": [
    {"id": "scene1", "start_frame": 0, "end_frame": 450}
  ]
}
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import urllib.request
import urllib.error


ELEVENLABS_API = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel
DEFAULT_MODEL = "eleven_turbo_v2_5"
# The with-timestamps endpoint returns MP3 in audio_base64 by default.
# We keep that — Remotion handles mp3 natively via staticFile().
AUDIO_FILENAME = "audio.mp3"


@dataclass
class SceneNarration:
    """One scene's narration payload as consumed by the director."""

    scene_id: str
    text: str
    # Anchor id prefixes that must resolve to frames within this scene.
    # The director declares anchor positions as character offsets (0 = start
    # of this scene's narration, len(text) = end). Must be sorted ascending.
    anchor_char_offsets: list[tuple[str, int]]


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
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise TTSError(f"ElevenLabs HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise TTSError(f"ElevenLabs request failed: {e.reason}") from e


def _alignment_duration(alignment: dict[str, Any]) -> float:
    """Return the audio duration in seconds, derived from alignment data."""
    ends = alignment.get("character_end_times_seconds") or []
    if ends:
        return float(ends[-1])
    starts = alignment.get("character_start_times_seconds") or []
    return float(starts[-1]) if starts else 0.0


def _char_offset_to_seconds(
    char_offset: int, alignment: dict[str, Any], fallback_duration: float
) -> float:
    """
    Resolve an input-text character offset to an absolute time within the
    scene's audio.

    ElevenLabs may normalize the text before alignment (expanding em-dashes,
    collapsing whitespace, etc.), so the alignment `characters` array can be
    a slightly different length than the input. We linearly interpolate:
    take char_offset / len(input_text) and find the matching position in the
    alignment array. This is robust against length mismatch and never
    overshoots the audio duration.
    """
    starts: list[float] = alignment.get("character_start_times_seconds") or []
    n = len(starts)
    if n == 0:
        return min(char_offset, 1) * fallback_duration

    # Map by ratio rather than direct indexing.
    ratio = max(0.0, min(1.0, char_offset / max(len(alignment.get("characters") or []), 1)))
    idx = min(int(round(ratio * (n - 1))), n - 1)
    return float(starts[idx])


def synthesize_script(
    narrations: list[SceneNarration],
    out_dir: Path,
    fps: int = 30,
) -> dict[str, Any]:
    """
    Generate audio.wav and timing.json from a list of scene narrations.

    Args:
        narrations: Ordered list of per-scene narration payloads.
        out_dir: Directory to write `public/audio.wav` and `timing.json`.
                 (The Remotion project's `public/` is the convention for
                 staticFile() assets — see the remotion-best-practices skill.)
        fps: Project frame rate. Anchors snap to integer frames.

    Returns:
        The timing dict that was written to timing.json.
    """
    api_key = _require_api_key()
    voice_id = _voice_id()

    public_dir = out_dir / "public"
    public_dir.mkdir(parents=True, exist_ok=True)
    audio_path = public_dir / AUDIO_FILENAME

    all_audio = bytearray()
    anchors: list[dict[str, Any]] = []
    scenes: list[dict[str, Any]] = []
    elapsed_seconds = 0.0

    for scene in narrations:
        print(f"[tts] synthesizing {scene.scene_id} ({len(scene.text)} chars)")
        resp = _call_elevenlabs(scene.text, api_key, voice_id)

        audio_b64 = resp.get("audio_base64") or resp.get("audio")
        if not audio_b64:
            raise TTSError(f"No audio in response for {scene.scene_id}")
        audio_bytes = base64.b64decode(audio_b64)

        alignment = resp.get("alignment") or {}
        scene_duration = _alignment_duration(alignment)
        if scene_duration <= 0:
            raise TTSError(
                f"ElevenLabs returned no usable alignment data for {scene.scene_id}"
            )

        scene_start_seconds = elapsed_seconds
        scene_start_frame = round(scene_start_seconds * fps)
        scene_end_seconds = scene_start_seconds + scene_duration
        scene_end_frame = round(scene_end_seconds * fps)

        # Scene start anchor (always emitted).
        anchors.append(
            {
                "id": f"{scene.scene_id}.start",
                "frame": scene_start_frame,
                "seconds": round(scene_start_seconds, 4),
            }
        )

        # Resolve each declared char-offset anchor inside the scene, then
        # clamp the resulting frame to (start, end) so the contract holds
        # even if the director picks an offset near the boundary.
        for anchor_id, char_offset in scene.anchor_char_offsets:
            rel_seconds = _char_offset_to_seconds(
                char_offset, alignment, scene_duration
            )
            abs_seconds = scene_start_seconds + rel_seconds
            frame = round(abs_seconds * fps)
            frame = max(scene_start_frame, min(scene_end_frame, frame))
            anchors.append(
                {
                    "id": anchor_id,
                    "frame": frame,
                    "seconds": round(frame / fps, 4),
                }
            )

        scenes.append(
            {
                "id": scene.scene_id,
                "start_frame": scene_start_frame,
                "end_frame": scene_end_frame,
            }
        )
        # Scene end anchor.
        anchors.append(
            {
                "id": f"{scene.scene_id}.end",
                "frame": scene_end_frame,
                "seconds": round(scene_end_seconds, 4),
            }
        )

        all_audio.extend(audio_bytes)
        elapsed_seconds = scene_end_seconds

    audio_path.write_bytes(bytes(all_audio))
    total_frames = round(elapsed_seconds * fps)

    timing = {
        "fps": fps,
        "audio_path": f"public/{AUDIO_FILENAME}",
        "total_frames": total_frames,
        "anchors": sorted(anchors, key=lambda a: a["frame"]),
        "scenes": scenes,
    }

    timing_path = out_dir / "timing.json"
    timing_path.write_text(json.dumps(timing, indent=2))
    print(
        f"[tts] wrote {audio_path} ({elapsed_seconds:.2f}s, {total_frames} frames) "
        f"and {timing_path} ({len(anchors)} anchors)"
    )
    return timing


def load_narrations_from_script(script_path: Path) -> list[SceneNarration]:
    """
    Parse script.json (written by the director in Phase A) into SceneNarration.

    script.json schema (director's contract):
    {
      "fps": 30,
      "scenes": [
        {
          "id": "scene1",
          "narration": "Full text of this scene's voiceover.",
          "anchors": [
            {"id": "scene1.beat1", "char_offset": 42},
            {"id": "scene1.beat2", "char_offset": 88}
          ]
        }
      ]
    }
    """
    data = json.loads(script_path.read_text())
    result = []
    for scene in data.get("scenes", []):
        anchors = [
            (a["id"], int(a["char_offset"])) for a in scene.get("anchors", [])
        ]
        result.append(
            SceneNarration(
                scene_id=scene["id"],
                text=scene["narration"],
                anchor_char_offsets=sorted(anchors, key=lambda x: x[1]),
            )
        )
    return result
