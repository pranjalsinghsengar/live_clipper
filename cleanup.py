"""Source recording cleanup.

Deletes stream recordings older than LIVE_CLEANUP_HOURS (default 24h) after
the stream ended. Only deletes if at least one clip was successfully
extracted (so we don't delete a recording that has zero clips because the
pipeline failed mid-way).

We also delete the corresponding live transcript JSON.

Run hourly via launchd.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import CONFIG
from db import (
    init_db,
    list_streams_for_cleanup,
    list_live_clips_for_stream,
)

log = logging.getLogger("cleanup")


def run_cleanup() -> int:
    init_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=CONFIG.live_cleanup_hours)).isoformat()
    candidates = list_streams_for_cleanup(cutoff)
    if not candidates:
        log.info("No recordings to clean up.")
        return 0

    deleted = 0
    for stream in candidates:
        stream_id = stream["id"]
        recording_path = Path(stream["recording_path"])
        transcript_path = CONFIG.live_transcripts_dir / f"stream_{stream_id}.json"

        # Safety check: don't delete if no clips were ever extracted.
        clips = list_live_clips_for_stream(stream_id)
        successful_clips = [c for c in clips if c["status"] in ("posted", "duplicate")]
        if not successful_clips:
            log.warning("Stream %d: keeping recording (no clips extracted yet).",
                        stream_id)
            continue

        # Delete the recording.
        try:
            if recording_path.exists():
                size_mb = recording_path.stat().st_size / (1024 * 1024)
                recording_path.unlink()
                log.info("Stream %d: deleted %s (%.1f MB)",
                         stream_id, recording_path.name, size_mb)
                deleted += 1
        except OSError as e:
            log.warning("Stream %d: failed to delete %s: %s",
                        stream_id, recording_path, e)

        # Delete the live transcript JSON.
        try:
            if transcript_path.exists():
                transcript_path.unlink()
        except OSError:
            pass

    log.info("Cleanup done. Deleted %d recording(s).", deleted)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=CONFIG.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    sys.exit(run_cleanup())
