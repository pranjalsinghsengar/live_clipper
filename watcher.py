"""Live watcher daemon.

Long-running process. Polls all enabled channels every poll_interval_seconds.
When a channel goes live and isn't already being recorded, spawns a
LivePipeline thread.

A single shared Antigravity Agent is created lazily on first use and passed
to all streams. Same for the Whisper model. This is essential: Gemma 4 26B
is 16GB+ and Whisper 'medium' is ~3GB, so one instance per stream would
quickly OOM.

Single-instance guard: we write a PID file in the data dir; if another
watcher is already running, this one exits. Use launchd's KeepAlive=true
to auto-restart on crash.
"""
from __future__ import annotations

import logging
import os
import re
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

from concurrent.futures import ThreadPoolExecutor, as_completed
from config import CONFIG
from db import (
    create_stream,
    init_db,
    list_active_streams,
    list_channels,
    mark_stream_done,
)
from live_pipeline import run_stream
from recorder import is_live

log = logging.getLogger("watcher")


class Watcher:
    def __init__(self) -> None:
        self.active: dict[int, threading.Thread] = {}  # stream_id -> thread
        self.lock = threading.Lock()
        self.whisper_model = None   # lazy-loaded by first transcriber
        self.agent_state: dict[str, Any] = {}   # shared across streams
        self._stop = threading.Event()

    def _load_whisper(self):
        if self.whisper_model is None:
            from faster_whisper import WhisperModel
            model_name = os.environ.get("WHISPER_MODEL", "base")
            log.info("Loading shared Whisper model: %s (cpu_threads=2)", model_name)
            self.whisper_model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=2)
        return self.whisper_model

    def _spawn(self, stream_id: int, url: str, channel_display: str) -> None:
        """Spawn a LivePipeline thread for a stream."""
        recording_path = CONFIG.streams_dir / f"stream_{stream_id}.mp4"
        # create_stream put a placeholder path in the DB; correct it.
        from db import update_stream_path
        update_stream_path(stream_id, str(recording_path))

        def _target():
            try:
                run_stream(
                    stream_id=stream_id,
                    url=url,
                    channel_display=channel_display,
                    recording_path=recording_path,
                    shared_whisper_model=self._load_whisper(),
                    shared_agent_state=self.agent_state,
                )
            except Exception as e:
                log.exception("Stream %d: pipeline crashed: %s", stream_id, e)
            finally:
                with self.lock:
                    self.active.pop(stream_id, None)

        t = threading.Thread(target=_target, name=f"stream-{stream_id}", daemon=True)
        with self.lock:
            self.active[stream_id] = t
        t.start()

    def _already_recording(self, channel_id: int) -> bool:
        """Check if there's already an active stream for this channel."""
        with self.lock:
            active_ids = set(self.active.keys())
        for s in list_active_streams():
            if s["channel_id"] == channel_id and s["id"] in active_ids:
                return True
        return False

    def _scan_once(self) -> None:
        """One polling pass. Check enabled channels in parallel; if live
        and not already recording, spawn a pipeline."""
        channels = list_channels(enabled_only=True)
        if not channels:
            return

        # Filter out already recording channels
        to_check = [ch for ch in channels if not self._already_recording(ch["id"])]
        if not to_check:
            return

        def _check(ch):
            if self._stop.is_set():
                return None
            try:
                live, meta = is_live(ch["url"])
                return (ch, meta) if live else None
            except Exception as e:
                log.warning("is_live check failed for %s: %s", ch["url"], e)
                return None

        discovered = []
        with ThreadPoolExecutor(max_workers=min(len(to_check), 15)) as pool:
            futures = [pool.submit(_check, ch) for ch in to_check]
            for fut in as_completed(futures):
                if self._stop.is_set():
                    break
                res = fut.result()
                if res:
                    discovered.append(res)

        def _viewer_score(item) -> int:
            _, meta = item
            raw = str(meta.get("viewers") or "")
            digits = re.sub(r'[^\d]', '', raw)
            return int(digits) if digits else 0

        # Sort highest viewership first (e.g. CarryMinati 78k > Speed 210k > smaller channels)
        discovered.sort(key=_viewer_score, reverse=True)

        for live_ch, meta in discovered:
            if self._already_recording(live_ch["id"]):
                continue

            # Respect max-parallel limit if set.
            if CONFIG.live_max_parallel > 0:
                with self.lock:
                    if len(self.active) >= CONFIG.live_max_parallel:
                        log.debug("At max_parallel=%d; skipping %s",
                                  CONFIG.live_max_parallel, live_ch["channel"])
                        break

            stream_url = meta.get("url") or live_ch["url"]
            viewers_info = meta.get("viewers") or "live"
            log.info("Channel %s (%s) is live (%s), starting recording",
                     live_ch["channel"], live_ch["platform"], viewers_info)
            recording_path_template = str(CONFIG.streams_dir / "stream_{stream_id}.mp4")
            stream_id = create_stream(live_ch["id"], recording_path_template)
            display = live_ch.get("display_name") or live_ch["channel"]
            self._spawn(stream_id, stream_url, display)

    def run(self) -> None:
        log.info("Watcher started. Polling %d channels every %ds",
                 len(list_channels(enabled_only=True)),
                 CONFIG.live_poll_interval_seconds)

        # Clean up any leftover active stream records from previous sessions
        for orphan in list_active_streams():
            log.info("Cleaning up leftover stream %d from previous session", orphan["id"])
            mark_stream_done(orphan["id"])

        # SIGTERM handler for clean shutdown from launchd.
        def _sigterm(signum, frame):
            log.info("Received SIGTERM, shutting down...")
            self._stop.set()
        signal.signal(signal.SIGTERM, _sigterm)

        while not self._stop.is_set():
            try:
                self._scan_once()
            except Exception as e:
                log.exception("Scan failed: %s", e)

            # Sleep poll_interval, but check _stop every 5s so SIGTERM responds.
            for _ in range(CONFIG.live_poll_interval_seconds // 5 or 1):
                if self._stop.is_set():
                    break
                time.sleep(5)

        # Wait for all active stream threads to finish (with a timeout).
        log.info("Waiting for %d active stream(s) to finish...", len(self.active))
        with self.lock:
            threads = list(self.active.values())
        for t in threads:
            t.join(timeout=60)


def main() -> int:
    init_db()
    logging.basicConfig(
        level=CONFIG.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # PID file guard.
    pid_file = CONFIG.data_dir / "watcher.pid"
    if pid_file.exists():
        try:
            old_pid = int(pid_file.read_text().strip())
            os.kill(old_pid, 0)   # signal 0 = check if alive
            log.error("Another watcher is already running (pid %d). Exiting.", old_pid)
            return 1
        except (ProcessLookupError, ValueError, PermissionError):
            # Stale PID file, claim it.
            pass

    pid_file.write_text(str(os.getpid()))
    try:
        Watcher().run()
    finally:
        try:
            pid_file.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
