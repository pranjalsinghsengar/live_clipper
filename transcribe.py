"""Local transcription via faster-whisper. Saves word-level timestamps so the
caption burner can do karaoke-style highlighting, and so the curator can read
the transcript without re-running Whisper.

faster-whisper is CTranslate2-backed, free, runs entirely on-device. On an
M2/M3 Mac it transcribes a 60min video in 2-4 minutes using the 'small' or
'medium' model. We default to 'medium' for a good balance of accuracy and
speed; override via WHISPER_MODEL env var.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from config import CONFIG


def transcribe(video_path: Path, concept_id: int) -> dict[str, Any]:
    """Run Whisper on the video file. Returns a dict with:
      - text: full transcript string
      - segments: list of {start, end, text}
      - words: list of {start, end, word} (word-level timestamps)
    Saves the same dict as JSON in transcripts/."""
    # Lazy import so the CLI starts fast even when not transcribing.
    from faster_whisper import WhisperModel

    model_size = os.environ.get("WHISPER_MODEL", "medium")
    # device="cpu" with compute_type="int8" is the fastest path on Apple
    # Silicon in May 2025; CTranslate2 doesn't yet expose Metal. We still
    # beat openai-whisper by a wide margin because of int8.
    model = WhisperModel(model_size, device="cpu", compute_type="int8", cpu_threads=2)

    out: dict[str, Any] = {"text": "", "segments": [], "words": []}
    segments_iter, info = model.transcribe(
        str(video_path),
        word_timestamps=True,
        vad_filter=True,           # drop long silences
        beam_size=5,
    )
    out["language"] = info.language
    out["duration_seconds"] = info.duration

    for seg in segments_iter:
        out["segments"].append({
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
        })
        out["text"] += seg.text
        if seg.words:
            for w in seg.words:
                out["words"].append({
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                    "word": w.word.strip(),
                })

    out_path = CONFIG.transcripts_dir / f"concept_{concept_id}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    return out
