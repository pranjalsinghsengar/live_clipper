"""streamlink-based live stream recorder.

Records to a single growing mp4 file. Used by live_pipeline.py for the
real-time clip pipeline. Also used by the end-of-stream final processing
(same file is passed to the existing clip pipeline).

We use streamlink because it handles all the major platforms (Twitch,
YouTube Live, Kick, Trovo, etc.) with one CLI. We do NOT segment the
output - one mp4 per stream is simpler and ffmpeg can read from any
offset in a growing mp4 just fine.
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

log = logging.getLogger("recorder")


def check_youtube_live(url: str) -> tuple[bool, str | None, str | None, str | None]:
    """Direct web check for YouTube live status without triggering streamlink bot checks.
    Returns (is_live, video_id, viewers, title)."""
    import re
    import urllib.request

    check_url = url
    if not check_url.endswith("/live") and "watch?v=" not in check_url:
        check_url = check_url.rstrip("/") + "/live"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    req = urllib.request.Request(check_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

            # Check if this is an upcoming/scheduled waiting room rather than active live broadcast
            if (
                '"style":"UPCOMING"' in html
                or '"status":"LIVE_STREAM_OFFLINE"' in html
                or '"isUpcoming":true' in html
                or "liveStreamOfflineSlateRenderer" in html
                or "Scheduled and hosted" in html
                or '"label":"Upcoming"' in html
            ):
                return False, None, None, None

            is_live = False
            if '"isLive":true' in html or '"viewCount":{"runs":[{"text":' in html:
                is_live = True

            video_id = None
            m_vid = re.search(r'"watchEndpoint":\{"videoId":"([a-zA-Z0-9_-]{11})"', html)
            if m_vid:
                video_id = m_vid.group(1)

            viewers = None
            m_views = re.search(r'"viewCount":\{.*?"simpleText":"([^"]+ watching now)"', html)
            if m_views:
                viewers = m_views.group(1)

            title = None
            m_title = re.search(r"<title>(.+?)</title>", html)
            if m_title:
                title = m_title.group(1).replace(" - YouTube", "").strip()

            return is_live, video_id, viewers, title
    except Exception as e:
        log.warning("YouTube direct web check failed for %s: %s", url, e)
        return False, None, None, None


def _get_cookies_args() -> list[str]:
    """Return streamlink cookie arguments if cookies.txt is present."""
    cookie_paths = [
        CONFIG.data_dir / "youtube_cookies.txt",
        Path.home() / "clips_pipeline_data" / "youtube_cookies.txt",
        Path.home() / "Downloads" / "youtube_cookies.txt",
        Path.home() / "Downloads" / "cookies.txt",
        Path.home() / "Downloads" / "www.youtube.com_cookies.txt",
        Path.home() / "Downloads" / "youtube.com_cookies.txt",
        Path(__file__).parent / "cookies.txt",
    ]
    # Check explicit paths
    for cp in cookie_paths:
        if cp.exists() and cp.stat().st_size > 100:
            log.info("Using YouTube cookie file at %s", cp)
            return ["--http-cookies-file", str(cp)]

    # Check any downloaded cookie file in ~/Downloads
    downloads_dir = Path.home() / "Downloads"
    if downloads_dir.exists():
        for cp in downloads_dir.glob("*cookie*.txt"):
            if cp.stat().st_size > 100:
                log.info("Auto-discovered YouTube cookie file at %s", cp)
                return ["--http-cookies-file", str(cp)]

    return []


def get_youtube_stream_url(url: str) -> str | None:
    """Use yt-dlp with cookies and EJS challenge solver to extract the direct live HLS m3u8 URL."""
    import sys
    cookie_args = _get_cookies_args()
    yt_dlp_cookie_args = []
    for i, a in enumerate(cookie_args):
        if a == "--http-cookies-file" and i + 1 < len(cookie_args):
            yt_dlp_cookie_args = ["--cookies", cookie_args[i + 1]]
            break

    cmd = [
        sys.executable, "-m", "yt_dlp",
        *yt_dlp_cookie_args,
        "--remote-components", "ejs:github",
        "-f", "300/301/best",
        "-g", url,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            lines = [l.strip() for l in res.stdout.strip().split("\n") if l.strip().startswith("http")]
            if lines:
                return lines[0]
    except Exception as e:
        log.warning("get_youtube_stream_url failed for %s: %s", url, e)
    return None


def is_live(url: str, quality: str = "best") -> tuple[bool, dict[str, Any]]:
    """Check if channel is live using direct web check for YouTube, then streamlink.
    Returns (is_live, metadata_dict)."""
    if "youtube.com" in url or "youtu.be" in url:
        yt_live, video_id, viewers, title = check_youtube_live(url)
        if yt_live:
            log.info("YouTube direct web check confirmed live: %s (viewers: %s)", title or video_id, viewers)
            return True, {
                "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else url,
                "title": title,
                "viewers": viewers,
                "video_id": video_id,
            }
        return False, {}

    cookie_args = _get_cookies_args()
    cmd = ["streamlink", *cookie_args, "--stream-timeout", "10", "--json", url, quality]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.warning("streamlink check failed for %s: %s", url, e)
        return False, {"error": str(e)}

    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return False, {"error": f"non-JSON output: {result.stdout[:200]}"}

    if data.get("error"):
        return False, data
    return bool(data.get("url") or data.get("streams")), data


def start_recording(url: str, output_path: Path, quality: str | None = None,
                     stop_event: threading.Event | None = None) -> int:
    """Run streamlink in a subprocess until the stream ends or stop_event
    is set. Blocks. Returns the streamlink exit code.

    We pass --force to overwrite, --no-progress to keep logs clean, and
    --url-as-title to embed the source URL in metadata.
    """
    quality = quality or CONFIG.live_stream_quality
    output_path.parent.mkdir(parents=True, exist_ok=True)

    target_url = url
    stream_quality = quality
    if "youtube.com" in url or "youtu.be" in url:
        direct_url = get_youtube_stream_url(url)
        if direct_url:
            log.info("Recording via direct YouTube live HLS manifest -> %s", output_path)
            target_url = direct_url
            stream_quality = "best"

    cookie_args = _get_cookies_args()
    cmd = [
        "streamlink",
        *cookie_args,
        "--progress", "no",
        "--force",
        "--hls-live-edge", "3",
        "--stream-segment-timeout", "30",
        "--stream-timeout", "60",
        "--stream-segment-threads", "3",
        "-o", str(output_path),
        target_url, stream_quality,
    ]
    log.info("Recording %s -> %s", url, output_path)
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # If a stop_event is provided, poll it and kill the process if set.
    # Otherwise just wait for the process to exit naturally (stream offline).
    if stop_event is not None:
        while proc.poll() is None:
            if stop_event.is_set():
                log.info("Stop event set, terminating streamlink for %s", url)
                proc.terminate()
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill()
                break
            time.sleep(2)
    else:
        proc.wait()

    return proc.returncode


def probe_duration_seconds(path: Path) -> float:
    """Use ffprobe to get the duration of the (possibly still growing) mp4."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            check=True, capture_output=True, text=True, timeout=30,
        )
        return float(out.stdout.strip() or 0.0)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
        return 0.0
