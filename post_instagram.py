"""Instagram Reels publishing via the Meta Graph API.

Two-step flow:
  1. POST /{ig_user_id}/media with media_type=REELS, video_url, caption.
     This creates a "media container" and starts a server-side fetch of the
     video. Returns container_id.
  2. POST /{ig_user_id}/media_publish?creation_id={container_id}.
     This actually schedules the reel for publication. The container MUST be
     in FINISHED state, which we poll for.

The video must be reachable by Meta's servers. Two options:
  A. PUBLIC_VIDEO_BASE_URL is set: we expose clips/ under that base URL via
     any static file server you already run (nginx, Cloudflare Tunnel, etc.).
     We just hand Meta `<base>/<clip_filename>`.
  B. PUBLIC_VIDEO_BASE_URL is blank: we spin up a tiny `http.server` on a
     free port and serve clips/ from it for the duration of the upload.
     This works on a home network with a public IP, fails behind CGNAT.
     For reliability use a Cloudflare Tunnel - free, no signup needed for
     a quick tunnel.
"""
from __future__ import annotations

import http.server
import socket
import socketserver
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from config import CONFIG

API_BASE = "https://graph.facebook.com/v21.0"


# --- Local file server (used when PUBLIC_VIDEO_BASE_URL is blank) ---------

class _SilentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args, **kwargs):
        pass


def _start_local_server(directory: Path) -> tuple[socketserver.TCPServer, int, str | None]:
    """Bind a free port, serve `directory` over HTTP. Returns (server, port,
    public_ip) - public_ip is best-effort and may be None."""
    handler = lambda *a, **kw: _SilentHandler(directory, *a, **kw)
    server = socketserver.TCPServer(("0.0.0.0", 0), handler)
    port = server.server_address[1]
    # Best-effort public IP detection. Will be None if it can't reach the
    # outside world (in which case we can't auto-post to IG from home).
    public_ip = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        public_ip = s.getsockname()[0]
        s.close()
    except OSError:
        pass
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port, public_ip


# --- Meta Graph API --------------------------------------------------------

def _container_status(container_id: str) -> str:
    """One of: IN_PROGRESS, FINISHED, ERROR, EXPIRED."""
    r = requests.get(
        f"{API_BASE}/{container_id}",
        params={"fields": "status_code", "access_token": CONFIG.ig_access_token},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("status_code", "IN_PROGRESS")


def publish_reel(clip_path: Path, caption: str) -> dict[str, Any]:
    """Publish a single clip as an Instagram Reel.

    Returns a small status dict that we store in DB.
    Raises on hard failure.
    """
    if not CONFIG.instagram_enabled:
        return {"skipped": "instagram not configured"}

    # 1. Resolve a public URL for the clip.
    server_to_stop: socketserver.TCPServer | None = None
    if CONFIG.public_video_base_url:
        video_url = urljoin(CONFIG.public_video_base_url.rstrip("/") + "/",
                            clip_path.name)
    else:
        server, port, public_ip = _start_local_server(clip_path.parent)
        server_to_stop = server
        if not public_ip:
            server.shutdown()
            return {"skipped": "no public IP - set PUBLIC_VIDEO_BASE_URL or use a tunnel"}
        video_url = f"http://{public_ip}:{port}/{clip_path.name}"

    try:
        # 2. Create container.
        r = requests.post(
            f"{API_BASE}/{CONFIG.ig_user_id}/media",
            data={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "access_token": CONFIG.ig_access_token,
            },
            timeout=60,
        )
        r.raise_for_status()
        container_id = r.json()["id"]

        # 3. Poll for FINISHED. Meta fetches the file from us; this can take
        # 5-60s depending on file size and bandwidth.
        deadline = time.time() + 5 * 60
        while time.time() < deadline:
            status = _container_status(container_id)
            if status == "FINISHED":
                break
            if status in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"IG container {status}: {container_id}")
            time.sleep(5)
        else:
            raise RuntimeError("IG container timed out (5min)")

        # 4. Publish.
        r = requests.post(
            f"{API_BASE}/{CONFIG.ig_user_id}/media_publish",
            data={"creation_id": container_id, "access_token": CONFIG.ig_access_token},
            timeout=60,
        )
        r.raise_for_status()
        media_id = r.json()["id"]
        return {"instagram": {"container_id": container_id, "media_id": media_id}}
    finally:
        if server_to_stop is not None:
            server_to_stop.shutdown()
