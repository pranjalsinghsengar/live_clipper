"""Incremental transcription of a growing mp4 file.

We poll the file's duration with ffprobe. Every `window_seconds` of new audio
that appears, we extract that window with ffmpeg and run faster-whisper on
it. Word timestamps are stored relative to the start of the stream (not the
window) so the curator can ask for any time range.

The output is a JSON file that grows over time:
{
  "language": "en",
  "duration_seconds": 3600.0,
  "words": [{"start": 0.0, "end": 0.4, "word": "..."}, ...],
  "segments": [...],
  "last_transcribed_at": 1234.5   # stream-relative seconds
}
"""
from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from config import CONFIG

log = logging.getLogger("live_transcribe")

_whisper_lock = threading.Lock()


def _load_state(state_path: Path) -> dict[str, Any]:
    if state_path.exists():
        return json.loads(state_path.read_text())
    return {
        "language": None,
        "duration_seconds": 0.0,
        "words": [],
        "segments": [],
        "last_transcribed_at": 0.0,
    }


def _save_state(state_path: Path, state: dict[str, Any]) -> None:
    state_path.write_text(json.dumps(state, ensure_ascii=False))


def _extract_window(video_path: Path, start: float, end: float, out_wav: Path) -> bool:
    """ffmpeg-extract [start, end] seconds of audio to a 16kHz mono wav."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
        "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000",
        "-f", "wav",
        str(out_wav),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        return out_wav.exists() and out_wav.stat().st_size > 0
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        log.warning("ffmpeg window extract failed for [%s, %s]: %s", start, end, e)
        return False


def _transcribe_wav(wav_path: Path, model) -> tuple[list[dict], list[dict], str | None]:
    """Run Whisper on a wav file. Returns (words, segments, language)."""
    with _whisper_lock:
        segments_iter, info = model.transcribe(
            str(wav_path),
            word_timestamps=True,
            vad_filter=True,
            beam_size=1,                # 1 = greedy decode for real-time speed
            temperature=0.0,            # prevent 6x temperature fallback loops on game audio
            language=None,              # auto-detect
        )
        words: list[dict] = []
        segs: list[dict] = []
        for seg in segments_iter:
            segs.append({
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": seg.text.strip(),
            })
            if seg.words:
                for w in seg.words:
                    words.append({
                        "start": round(w.start, 3),
                        "end": round(w.end, 3),
                        "word": w.word.strip(),
                    })
        return words, segs, info.language


def transcribe_growing_file(
    video_path: Path,
    state_path: Path,
    stop_event: threading.Event,
    model=None,
) -> None:
    """Loop: poll duration, transcribe new windows, append to state.

    Blocks until stop_event is set (caller signals stream ended).

    If `model` is None we lazily load faster-whisper here; otherwise reuse
    a shared model passed in by the watcher (more efficient when many
    streams run in parallel).
    """
    if model is None:
        from faster_whisper import WhisperModel
        model = WhisperModel(os.environ.get("WHISPER_MODEL", "small"),
                             device="cpu", compute_type="int8")
        log.info("Loaded live Whisper model: %s", os.environ.get("WHISPER_MODEL", "small"))

    window_s = CONFIG.live_transcribe_window_seconds
    state = _load_state(state_path)

    while not stop_event.is_set():
        # How long is the recording now?
        try:
            from recorder import probe_duration_seconds
            current_duration = probe_duration_seconds(video_path)
        except Exception as e:
            log.warning("probe_duration failed for %s: %s", video_path, e)
            time.sleep(5)
            continue

        if current_duration <= 0:
            # Stream not started writing yet, or ffprobe can't read it.
            time.sleep(5)
            continue

        # What's the next window to transcribe?
        last_done = float(state.get("last_transcribed_at", 0.0))
        next_window_start = last_done
        if next_window_start + window_s > current_duration:
            # Not enough new audio yet. Wait for more.
            time.sleep(max(5, int(window_s - (current_duration - next_window_start))))
            continue

        # Extract and transcribe [next_window_start, next_window_start + window_s).
        wav_path = state_path.with_suffix(f".{int(next_window_start)}.wav")
        if not _extract_window(video_path, next_window_start,
                               next_window_start + window_s, wav_path):
            time.sleep(5)
            continue

        try:
            words, segs, lang = _transcribe_wav(wav_path, model)
        except Exception as e:
            log.exception("Whisper failed on %s: %s", wav_path, e)
            time.sleep(5)
            continue
        finally:
            try:
                wav_path.unlink()
            except OSError:
                pass

        # Shift timestamps to be stream-relative and merge.
        for w in words:
            w["start"] = round(w["start"] + next_window_start, 3)
            w["end"] = round(w["end"] + next_window_start, 3)
        for s in segs:
            s["start"] = round(s["start"] + next_window_start, 3)
            s["end"] = round(s["end"] + next_window_start, 3)

        state["words"].extend(words)
        state["segments"].extend(segs)
        state["last_transcribed_at"] = next_window_start + window_s
        state["duration_seconds"] = current_duration
        if lang and not state.get("language"):
            state["language"] = lang
        _save_state(state_path, state)

        log.info("Stream %s: transcribed window [%d-%d]s, %d words total",
                 video_path.stem, next_window_start,
                 next_window_start + window_s, len(state["words"]))

    # Final state update with the final duration.
    try:
        from recorder import probe_duration_seconds
        state["duration_seconds"] = probe_duration_seconds(video_path)
        _save_state(state_path, state)
    except Exception:
        pass


import os  # used by lazy-load block above; placed at bottom to keep imports clean
