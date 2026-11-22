"""TikTok publishing via the Content Posting API (direct upload flow).

Unlike Instagram, TikTok doesn't need a public URL - we upload the file
directly from this machine in chunks.

Flow (v2 API, "file upload" path):
  1. POST /v2/post/publish/video/init/  -> returns upload_url + publish_id.
  2. PUT the video bytes to upload_url (chunked).
  3. POST /v2/post/publish/status/fetch/ with publish_id until SUCCESS.

Scope required: video.upload, video.publish.
Auth: OAuth access token with the right scopes. TikTok's docs cover getting
one; we just use it here.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

import requests

from config import CONFIG

API_BASE = "https://open.tiktokapis.com"


def _chunk_size() -> int:
    """TikTok requires chunks between 5MB and 64MB. We use 16MB."""
    return 16 * 1024 * 1024


def _init_upload(clip_path: Path, caption: str) -> dict[str, str]:
    """Step 1: initialise the upload. Returns {upload_url, publish_id}."""
    file_size = clip_path.stat().st_size
    chunk_size = _chunk_size()
    total_chunks = (file_size + chunk_size - 1) // chunk_size

    # TikTok requires a per-chunk SHA256 of each chunk; we use content-range.
    # Compute the SHA256 of the whole file (used for the "exact" upload mode).
    sha256 = hashlib.sha256()
    with clip_path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            sha256.update(block)
    file_hash = sha256.hexdigest()

    body = {
        "source": "FILE_UPLOAD",
        "video_size": file_size,
        "chunk_size": chunk_size,
        "total_chunk_count": total_chunks,
        "video_hash": file_hash,
    }
    r = requests.post(
        f"{API_BASE}/v2/post/publish/video/init/",
        headers={
            "Authorization": f"Bearer {CONFIG.tiktok_access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json=body,
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("error", {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok init failed: {data}")
    return {
        "upload_url": data["data"]["upload_url"],
        "publish_id": data["data"]["publish_id"],
    }


def _upload_chunks(clip_path: Path, upload_url: str) -> None:
    """Step 2: PUT each chunk to upload_url with Content-Range header."""
    chunk_size = _chunk_size()
    file_size = clip_path.stat().st_size
    total_chunks = (file_size + chunk_size - 1) // chunk_size

    with clip_path.open("rb") as f:
        for i in range(total_chunks):
            chunk = f.read(chunk_size)
            start = i * chunk_size
            end = start + len(chunk) - 1
            r = requests.put(
                upload_url,
                data=chunk,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Type": "video/mp4",
                },
                timeout=300,
            )
            r.raise_for_status()


def _publish(publish_id: str, caption: str) -> None:
    """Step 3: hand off publish_id with post metadata so the video actually
    appears on the user's TikTok."""
    body = {
        "publish_id": publish_id,
        "post_info": {
            "title": caption,
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
            "video_cover_timestamp_ms": 1000,
        },
    }
    r = requests.post(
        f"{API_BASE}/v2/post/publish/video/init/",
        # /init is what v2 docs name this step. (Yes, both steps use /init/.)
        headers={
            "Authorization": f"Bearer {CONFIG.tiktok_access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json=body,
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("error", {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok publish failed: {data}")


def _wait_for_success(publish_id: str, timeout_s: int = 600) -> str:
    """Poll the status endpoint until the video is processed."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = requests.post(
            f"{API_BASE}/v2/post/publish/status/fetch/",
            headers={
                "Authorization": f"Bearer {CONFIG.tiktok_access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={"publish_id": publish_id},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        status = data.get("data", {}).get("status", "PROCESSING")
        if status in ("PUBLISH_COMPLETE", "SUCCESS"):
            return status
        if status in ("FAILED", "REJECTED"):
            raise RuntimeError(f"TikTok upload {status}: {data}")
        time.sleep(10)
    raise TimeoutError(f"TikTok upload timed out after {timeout_s}s")


def publish_tiktok(clip_path: Path, caption: str) -> dict[str, Any]:
    """End-to-end TikTok publish. Returns status dict for DB."""
    if not CONFIG.tiktok_enabled:
        return {"skipped": "tiktok not configured"}

    init = _init_upload(clip_path, caption)
    _upload_chunks(clip_path, init["upload_url"])
    _publish(init["publish_id"], caption)
    status = _wait_for_success(init["publish_id"])
    return {"tiktok": {"publish_id": init["publish_id"], "status": status}}
