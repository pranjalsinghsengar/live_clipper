"""ffmpeg-based clip producer.

Given a source video + a clip spec (start/end seconds + title/caption) we:
  1. Cut the source to [start, end].
  2. Re-encode to a 9:16 vertical clip at OUTPUT_WIDTH x OUTPUT_HEIGHT. The
     source is centre-cropped to a vertical slice and scaled to fill; if the
     source is already vertical we just scale.
  3. Burn the ASS captions into the video (so they survive platform
     re-encoding).
  4. Save to clips/ as concept_<id>_clip_<n>.mp4.

The pipeline calls this once per clip suggestion.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from captions import build_ass
from config import CONFIG

log = logging.getLogger("clip")

_FILTER_CACHE: dict[str, bool] = {}
_ENCODER_CACHE: dict[str, bool] = {}


def _ffmpeg_supports_filter(filter_name: str) -> bool:
    if filter_name not in _FILTER_CACHE:
        try:
            res = subprocess.run([CONFIG.ffmpeg_path or "ffmpeg", "-filters"],
                                 capture_output=True, text=True, timeout=5)
            _FILTER_CACHE[filter_name] = f" {filter_name} " in res.stdout
        except Exception:
            _FILTER_CACHE[filter_name] = False
    return _FILTER_CACHE[filter_name]


def _ffmpeg_supports_encoder(encoder_name: str) -> bool:
    if encoder_name not in _ENCODER_CACHE:
        try:
            res = subprocess.run([CONFIG.ffmpeg_path or "ffmpeg", "-encoders"],
                                 capture_output=True, text=True, timeout=5)
            _ENCODER_CACHE[encoder_name] = f" {encoder_name} " in res.stdout
        except Exception:
            _ENCODER_CACHE[encoder_name] = False
    return _ENCODER_CACHE[encoder_name]


def _probe_duration(video_path: Path) -> float:
    """Use ffprobe to get the source video's duration in seconds."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def make_clip(
    source_video: Path,
    concept_id: int,
    clip_index: int,
    spec: dict[str, Any],
    transcript_words: list[dict[str, Any]] | None = None,
) -> tuple[Path, float]:
    """Render one clip. Returns (clip_path, duration_seconds)."""
    start = float(spec["start"])
    end = float(spec["end"])
    duration = end - start

    clip_path = CONFIG.clips_dir / f"concept_{concept_id}_clip_{clip_index:02d}.mp4"
    ass_path = CONFIG.clips_dir / f"concept_{concept_id}_clip_{clip_index:02d}.ass"

    # Build the ASS subtitle file with sticky hook banner & kinetic captions
    hook_banner = spec.get("hook_banner") or spec.get("title") or ""
    build_ass(transcript_words or [], start, end, ass_path, hook_banner=hook_banner)

    # Centre-crop to 9:16 then scale with square pixel aspect ratio.
    filter_parts = [
        "crop=ih*9/16:ih",
        f"scale={CONFIG.output_width}:{CONFIG.output_height}:flags=lanczos",
        "setsar=1",
    ]
    if _ffmpeg_supports_filter("ass"):
        ass_filter_path = str(ass_path).replace("\\", "/").replace(":", r"\:")
        filter_parts.append(f"ass='{ass_filter_path}'")
    else:
        log.debug("ffmpeg build has no libass; skipping burned subtitles")
    video_filter = ",".join(filter_parts)

    # Use fast libx264 software encoding for bulletproof reliability
    video_codec_args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]

    cmd = [
        CONFIG.ffmpeg_path or "ffmpeg",
        "-y",
        "-ss", f"{start:.3f}",
        "-to", f"{end:.3f}",
        "-i", str(source_video),
        "-vf", video_filter,
        *video_codec_args,
        "-pix_fmt", "yuv420p",   # max platform compatibility
        "-c:a", "aac",
        "-b:a", "192k",
        "-ac", "2",
        "-movflags", "+faststart",  # streaming-friendly mp4
        str(clip_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        log.error("ffmpeg clip render failed: %s\nStderr: %s", e, e.stderr)
        raise
    return clip_path, duration


def load_transcript_words(concept_id: int) -> list[dict[str, Any]] | None:
    """Load the word-level transcript we saved during transcribe(). Used to
    build per-clip ASS files."""
    path = CONFIG.transcripts_dir / f"concept_{concept_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return data.get("words")
