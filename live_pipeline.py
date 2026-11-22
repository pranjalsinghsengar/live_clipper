"""Per-stream orchestrator.

Spawns four parallel threads per active stream:
  1. Recorder: streamlink writing to disk
  2. Transcriber: incremental Whisper on the growing mp4
  3. Curator: every N seconds, send rolling transcript to Antigravity
  4. Clip poster: when curator picks a clip, render it + post immediately

When the stream ends, we run the existing clip pipeline on the full
recording (catches any moments the live loop missed) and let the cleanup
job delete the source file 24h later.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from clip import load_transcript_words, make_clip
from config import CONFIG
from db import (
    add_content,
    add_live_clip,
    list_pending_live_clips,
    mark_live_clip_failed,
    mark_live_clip_posted,
    mark_live_clip_rendering,
    mark_stream_done,
    mark_stream_ended,
    mark_stream_failed,
)
from live_curate import curate_rolling
from live_transcribe import transcribe_growing_file
from recorder import probe_duration_seconds, start_recording

log = logging.getLogger("live_pipeline")


def run_stream(
    stream_id: int,
    url: str,
    channel_display: str,
    recording_path: Path,
    shared_whisper_model=None,
    shared_agent_state: dict | None = None,
) -> None:
    """Run the full live pipeline for one stream. Blocks until the stream
    ends and the post-processing is done."""
    log.info("Stream %d (%s): starting live pipeline -> %s",
             stream_id, channel_display, recording_path)

    transcript_path = CONFIG.live_transcripts_dir / f"stream_{stream_id}.json"
    stop_event = threading.Event()

    # --- Thread 1: Transcriber ---
    transcribe_thread = threading.Thread(
        target=transcribe_growing_file,
        args=(recording_path, transcript_path, stop_event),
        kwargs={"model": shared_whisper_model},
        name=f"transcribe-{stream_id}",
        daemon=True,
    )
    transcribe_thread.start()

    # --- Thread 2: Curator ---
    curate_thread = threading.Thread(
        target=curate_rolling,
        args=(stream_id, transcript_path, stop_event, shared_agent_state),
        name=f"curate-{stream_id}",
        daemon=True,
    )
    curate_thread.start()

    # --- Thread 3: Clip poster (watches DB for pending live_clips) ---
    poster_thread = threading.Thread(
        target=_poster_loop,
        args=(stream_id, recording_path, stop_event),
        name=f"poster-{stream_id}",
        daemon=True,
    )
    poster_thread.start()

    # --- Thread 4 (main): Recorder (blocks until stream ends) ---
    try:
        start_recording(url, recording_path, stop_event=stop_event)
    except Exception as e:
        log.exception("Stream %d: recorder crashed: %s", stream_id, e)
        mark_stream_failed(stream_id, f"recorder: {e!r}")
        stop_event.set()
        return

    log.info("Stream %d: recording ended, finalising", stream_id)
    duration = probe_duration_seconds(recording_path)
    mark_stream_ended(stream_id, duration)

    # Wait for the transcriber to drain the last window.
    stop_event.set()
    transcribe_thread.join(timeout=120)
    curate_thread.join(timeout=10)
    poster_thread.join(timeout=300)   # let any in-flight post finish

    # Final pass: render any pending clips from the live table that the
    # poster thread hadn't gotten to yet.
    _drain_pending_clips(stream_id, recording_path)

    # Auto-queue + immediate clip run: copy the recording into the concepts
    # table with the existing pipeline. This picks up moments the live
    # curator's 10-min window may have missed.
    _run_final_pipeline(stream_id, recording_path)

    mark_stream_done(stream_id)
    log.info("Stream %d: done.", stream_id)


def _poster_loop(stream_id: int, recording_path: Path,
                 stop_event: threading.Event) -> None:
    """Watch the live_clips table for this stream. For each pending clip,
    render it with ffmpeg and post immediately to all configured platforms."""
    seen_ids: set[int] = set()
    while not stop_event.is_set():
        pending = list_pending_live_clips(stream_id)
        for lc in pending:
            if lc["id"] in seen_ids:
                continue
            seen_ids.add(lc["id"])
            try:
                _render_and_post_live_clip(stream_id, recording_path, lc)
            except Exception as e:
                seen_ids.discard(lc["id"])
                log.exception("Stream %d: live_clip %d failed: %s",
                              stream_id, lc["id"], e)
                mark_live_clip_failed(lc["id"], f"{e!r}")
        # Poll every 5 seconds.
        for _ in range(5):
            if stop_event.is_set():
                return
            time.sleep(1)


def _render_and_post_live_clip(stream_id: int, recording_path: Path,
                                live_clip: dict[str, Any]) -> None:
    """Render one live clip and post it to all configured platforms."""
    mark_live_clip_rendering(live_clip["id"])
    spec = {
        "start": float(live_clip["start_seconds"]),
        "end": float(live_clip["end_seconds"]),
        "title": live_clip.get("title") or f"Stream {stream_id} clip",
        "caption": live_clip.get("caption") or "",
        "hook_banner": live_clip.get("hook_banner") or f"🔴 {live_clip.get('title') or 'GTA 6 MOMENT'}"[:35],
    }

    # Build the ASS captions from the live transcript.
    transcript_path = CONFIG.live_transcripts_dir / f"stream_{stream_id}.json"
    transcript_words = None
    if transcript_path.exists():
        transcript_words = json.loads(transcript_path.read_text()).get("words")

    clip_path = CONFIG.clips_dir / f"concept_{stream_id}_clip_{live_clip['id']:02d}.mp4"
    if clip_path.exists() and clip_path.stat().st_size > 0:
        duration = float(spec["end"]) - float(spec["start"])
        log.info("Stream %d: clip %d already rendered (%s)", stream_id, live_clip["id"], clip_path.name)
    else:
        clip_path, duration = make_clip(
            source_video=recording_path,
            concept_id=stream_id,   # not a concept, but we use the same naming
            clip_index=live_clip["id"],
            spec=spec,
            transcript_words=transcript_words,
        )

    # Record in the content table so the post_loop / launchd schedule can
    # see it too. Then post immediately.
    content_id = add_content(
        concept_id=-1,           # no concept - this was a live clip
        title=spec["title"],
        clip_path=str(clip_path),
        caption=spec["caption"],
        duration_seconds=duration,
        start_seconds=spec["start"],
        end_seconds=spec["end"],
    )

    platform_state = _post_to_all(clip_path, spec["caption"], title=spec.get("title"))
    mark_live_clip_posted(live_clip["id"], content_id)

    # Also update the content row with the platform state.
    from db import mark_content_posted
    mark_content_posted(content_id, platform_state)
    log.info("Stream %d: posted live_clip %d -> content %d",
             stream_id, live_clip["id"], content_id)


def _post_to_all(clip_path: Path, caption: str, title: str | None = None) -> dict[str, Any]:
    """Post to all configured platforms. Returns the platform_state dict.
    Failures on one platform don't block the others."""
    from post_instagram import publish_reel
    from post_tiktok import publish_tiktok
    from post_youtube import publish_short

    state: dict[str, Any] = {}
    if CONFIG.instagram_enabled:
        try:
            state.update(publish_reel(clip_path, caption))
        except Exception as e:
            log.exception("Instagram post failed: %s", e)
            state["instagram"] = {"error": str(e)}
    if CONFIG.tiktok_enabled:
        try:
            state.update(publish_tiktok(clip_path, caption))
        except Exception as e:
            log.exception("TikTok post failed: %s", e)
            state["tiktok"] = {"error": str(e)}
    if CONFIG.youtube_enabled:
        try:
            state.update(publish_short(clip_path, caption, title=title))
        except Exception as e:
            log.exception("YouTube post failed: %s", e)
            state["youtube"] = {"error": str(e)}
    return state


def _drain_pending_clips(stream_id: int, recording_path: Path) -> None:
    """At stream end, render + post any live_clips that the poster thread
    hadn't gotten to."""
    pending = list_pending_live_clips(stream_id)
    for lc in pending:
        try:
            _render_and_post_live_clip(stream_id, recording_path, lc)
        except Exception as e:
            log.exception("Stream %d: drain live_clip %d failed: %s",
                          stream_id, lc["id"], e)
            mark_live_clip_failed(lc["id"], f"{e!r}")


def _run_final_pipeline(stream_id: int, recording_path: Path) -> None:
    """Run the existing (non-live) clip pipeline on the full recording.
    Catches moments the live curator's rolling window missed."""
    if not recording_path.exists() or recording_path.stat().st_size < 1000:
        log.warning("Stream %d: recording file %s is empty or not found; skipping final pass", stream_id, recording_path)
        return

    log.info("Stream %d: running final pass on full recording", stream_id)
    try:
        from pipeline import process_concept
        # Treat the stream like a concept with a local source.
        process_concept(stream_id, str(recording_path), "local")
    except Exception as e:
        log.exception("Stream %d: final pipeline failed: %s", stream_id, e)
