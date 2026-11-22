"""The clip pipeline. Given a concept id (or all queued todos), download the
source, transcribe it, ask Antigravity to pick viral moments, render clips,
and write them to the content table.

This script is what the weekly launchd job runs.
"""
from __future__ import annotations

import logging
import traceback
from pathlib import Path

from config import CONFIG
from clip import load_transcript_words, make_clip
from curate import curate
from db import (
    fetch_todo_concepts,
    mark_concept_failed,
    mark_concept_processed,
    add_content,
)
from download import download_source, ensure_tools_installed

log = logging.getLogger("pipeline")


def process_concept(concept_id: int, video_url: str, source: str) -> int:
    """Returns the number of clips successfully rendered for this concept."""
    log.info("Concept %d: downloading %s", concept_id, video_url)
    source_video = download_source(video_url, source, concept_id)

    log.info("Concept %d: transcribing + curating", concept_id)
    clips_spec = curate(source_video, concept_id)
    if not clips_spec:
        log.warning("Concept %d: curator returned no clips", concept_id)
        return 0

    log.info("Concept %d: rendering %d clips", concept_id, len(clips_spec))
    transcript_words = load_transcript_words(concept_id)
    rendered = 0
    for idx, spec in enumerate(clips_spec, start=1):
        try:
            clip_path, duration = make_clip(
                source_video, concept_id, idx, spec, transcript_words
            )
            add_content(
                concept_id=concept_id,
                title=spec.get("title") or f"Clip {idx}",
                clip_path=str(clip_path),
                caption=spec.get("caption", ""),
                duration_seconds=duration,
                start_seconds=float(spec["start"]),
                end_seconds=float(spec["end"]),
            )
            rendered += 1
        except Exception as e:
            # No content row was created yet, so there's nothing to mark
            # failed - just log and move on. One bad clip shouldn't waste
            # the whole video.
            log.exception("Concept %d clip %d failed: %s", concept_id, idx, e)

    mark_concept_processed(concept_id)
    log.info("Concept %d: done, %d clips in content table", concept_id, rendered)
    return rendered


def run_pending(limit: int = 2) -> int:
    """Process up to `limit` todo concepts. Returns count of clips rendered."""
    ensure_tools_installed()
    todo = fetch_todo_concepts(limit=limit)
    if not todo:
        log.info("No todo concepts. Queue is empty.")
        return 0

    total_clips = 0
    for concept in todo:
        cid = concept["id"]
        try:
            total_clips += process_concept(cid, concept["video_url"], concept["source"])
        except Exception as e:
            log.exception("Concept %d failed: %s", cid, e)
            mark_concept_failed(cid, f"{e!r}\n{traceback.format_exc()}")
    return total_clips


if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(
        level=CONFIG.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Run the clip pipeline on queued concepts.")
    parser.add_argument("--limit", type=int, default=2,
                        help="Max concepts to process in one run (default 2)")
    args = parser.parse_args()
    clips = run_pending(limit=args.limit)
    print(f"Rendered {clips} clips.")
    sys.exit(0)
