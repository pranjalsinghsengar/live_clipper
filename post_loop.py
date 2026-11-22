"""The posting loop. Picks one random Ready-to-Post clip from the content
table, posts it to Instagram (and/or TikTok if configured), then marks it
Posted.

This script is what the 3PM and 8PM launchd jobs run.
"""
from __future__ import annotations

import logging
from pathlib import Path

from config import CONFIG
from db import fetch_random_ready_clip, mark_content_failed, mark_content_posted
from post_instagram import publish_reel
from post_tiktok import publish_tiktok
from post_youtube import publish_short

log = logging.getLogger("post_loop")


def post_one() -> dict | None:
    """Pick one ready clip and post it. Returns the platform_state dict on
    success, None if the queue was empty."""
    clip = fetch_random_ready_clip()
    if clip is None:
        log.info("No Ready-to-Post clips. Nothing to do.")
        return None

    clip_path = Path(clip["clip_path"])
    if not clip_path.exists():
        mark_content_failed(clip["id"], f"clip file missing: {clip_path}")
        log.error("Content %d: clip file missing: %s", clip["id"], clip_path)
        return None

    caption = clip.get("caption") or clip.get("title") or ""
    platform_state: dict = {}

    if CONFIG.instagram_enabled:
        try:
            platform_state.update(publish_reel(clip_path, caption))
        except Exception as e:
            log.exception("Content %d: Instagram post failed: %s", clip["id"], e)
            mark_content_failed(clip["id"], f"instagram: {e!r}")
            return None

    if CONFIG.tiktok_enabled:
        try:
            platform_state.update(publish_tiktok(clip_path, caption))
        except Exception as e:
            log.exception("Content %d: TikTok post failed: %s", clip["id"], e)
            # Don't fail the whole run if IG succeeded - record partial.
            platform_state.setdefault("tiktok", {"error": str(e)})

    if CONFIG.youtube_enabled:
        try:
            platform_state.update(publish_short(clip_path, caption, title=clip.get("title")))
        except Exception as e:
            log.exception("Content %d: YouTube post failed: %s", clip["id"], e)
            # Same as TikTok - record partial, don't fail the whole run.
            platform_state.setdefault("youtube", {"error": str(e)})

    # If neither platform is configured, this is a no-op but we still mark
    # the clip as "posted" so it doesn't get re-picked every run.
    mark_content_posted(clip["id"], platform_state)
    log.info("Content %d: posted. State=%s", clip["id"], platform_state)
    return platform_state


if __name__ == "__main__":
    logging.basicConfig(
        level=CONFIG.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    post_one()
