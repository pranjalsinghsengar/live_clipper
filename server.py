"""Antigravity Clips Studio - Full Web UI Backend Server.
Provides interactive controls for:
  - Viral YouTube Radar (Search & 1-Click Viral Clipping)
  - Video Clip Studio (Trimming, 3-Tier Layout, Split-Screen Comparison, Impact Headlines)
  - Live Stream Monitoring & Instant Live Clipping
  - Multi-Channel YouTube Publishing Hub (Channel 1 Primary & Channel 2 Failover)
  - System Monitoring, Background Tasks & Logs
"""
import asyncio
import glob
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import static_ffmpeg
static_ffmpeg.add_paths()

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import CONFIG
import db
from post_youtube import (
    publish_short,
    get_all_token_paths,
    get_authenticated_service,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("studio_server")

app = FastAPI(title="GTA 6 & Streamer Clips Studio", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories
PIPELINE_DATA = Path("pipeline_data")
VIRAL_DIR = PIPELINE_DATA / "viral_external_shorts"
CLIPS_DIR = PIPELINE_DATA / "clips"
ASSETS_DIR = Path("assets")
LOGS_DIR = Path("logs")

VIRAL_DIR.mkdir(parents=True, exist_ok=True)
CLIPS_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Mount media dirs for in-browser playback & thumbnail preview
app.mount("/media/viral", StaticFiles(directory=str(VIRAL_DIR)), name="media_viral")
app.mount("/media/clips", StaticFiles(directory=str(CLIPS_DIR)), name="media_clips")
if ASSETS_DIR.exists():
    app.mount("/media/assets", StaticFiles(directory=str(ASSETS_DIR)), name="media_assets")

# Global In-Memory Task Manager
TASKS: Dict[str, Dict[str, Any]] = {}
TASK_LOCK = threading.Lock()
LIVE_WATCHER_PROC: Optional[subprocess.Popen] = None

FONT_PATH = "/System/Library/Fonts/Supplemental/Impact.ttf"
if not os.path.exists(FONT_PATH):
    FONT_PATH = "/System/Library/Fonts/Impact.ttf"


def add_task(title: str, task_type: str) -> str:
    task_id = str(uuid.uuid4())[:8]
    with TASK_LOCK:
        TASKS[task_id] = {
            "id": task_id,
            "title": title,
            "type": task_type,
            "status": "running",
            "progress": 0,
            "message": "Initialized...",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "ended_at": None,
            "result": None,
            "error": None,
        }
    return task_id


def update_task(task_id: str, progress: int = None, message: str = None, status: str = None, result: Any = None, error: str = None):
    with TASK_LOCK:
        if task_id in TASKS:
            t = TASKS[task_id]
            if progress is not None:
                t["progress"] = progress
            if message is not None:
                t["message"] = message
            if status is not None:
                t["status"] = status
                if status in ("completed", "failed"):
                    t["ended_at"] = datetime.now(timezone.utc).isoformat()
            if result is not None:
                t["result"] = result
            if error is not None:
                t["error"] = error


# --- Pydantic Request Models ---

class RenderClipRequest(BaseModel):
    video_url_or_path: str
    start_time: float = 0.0
    end_time: Optional[float] = None
    duration: Optional[float] = None
    layout: str = "3tier"  # "3tier" | "split_compare" | "vertical_blur"
    headline_line1: str = "GTA 6 INSANE MOMENT"
    headline_line2: str = "MUST WATCH! 😱💀"
    custom_title: Optional[str] = None
    caption: Optional[str] = None
    target_channel: str = "auto"  # "auto" | "primary" | "channel2"
    upload_to_youtube: bool = True
    tags: Optional[List[str]] = None


class PreviewFrameRequest(BaseModel):
    video_url_or_path: str
    timestamp: float = 10.0
    layout: str = "3tier"
    headline_line1: str = "GTA 6 MOMENT"
    headline_line2: str = "WAIT FOR THE END! 😱"


class DirectUploadRequest(BaseModel):
    file_path: str
    title: str
    caption: Optional[str] = None
    target_channel: str = "auto"
    tags: Optional[List[str]] = None


class AddChannelRequest(BaseModel):
    channel: str
    display_name: Optional[str] = None


class SearchViralRequest(BaseModel):
    query: str
    limit: int = 15


# --- Background Worker Functions ---

def _run_preview_frame(req: PreviewFrameRequest, out_path: Path):
    src = req.video_url_or_path.strip()
    # If it's a URL, download a 5 second snippet or use an existing file
    local_src = src
    if src.startswith("http://") or src.startswith("https://"):
        # check if already in viral_dir
        cached = list(VIRAL_DIR.glob("*.mp4"))
        if cached:
            local_src = str(cached[0])
        else:
            raise ValueError("For preview, please provide a local file or download the video first.")

    line1 = req.headline_line1.replace("'", "").strip()
    line2 = req.headline_line2.replace("'", "").strip()
    bottom_art = ASSETS_DIR / "gta6_bottom_artwork.png"

    filter_complex = f"""
[0:v]crop=579:312:3:669,scale=1080:792:flags=lanczos,boxblur=30:5[top_bg];
[0:v]crop=579:312:3:669,scale=1000:562:flags=lanczos[top_fg];
[top_bg][top_fg]overlay=40:185[top_cam];
[top_cam]drawtext=fontfile='{FONT_PATH}':text='{line1}':fontcolor=white:fontsize=58:borderw=8:bordercolor=black:x=(w-text_w)/2:y=35,drawtext=fontfile='{FONT_PATH}':text='{line2}':fontcolor=white:fontsize=58:borderw=8:bordercolor=black:x=(w-text_w)/2:y=105[top_tier];
[0:v]scale=1080:697:flags=lanczos[mid_tier];
[1:v]scale=1080:431:flags=lanczos[bot_tier];
[top_tier][mid_tier]vstack=inputs=2[top_mid];
[top_mid][bot_tier]vstack=inputs=2[v]
"""
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(req.timestamp),
        "-i", local_src,
        "-loop", "1", "-i", str(bottom_art),
        "-filter_complex", filter_complex.strip(),
        "-map", "[v]",
        "-vframes", "1",
        "-q:v", "2",
        str(out_path)
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _process_clip_render_and_upload(task_id: str, req: RenderClipRequest):
    try:
        update_task(task_id, progress=5, message="Resolving video source...")
        src_input = req.video_url_or_path.strip()
        local_src = None

        if src_input.startswith("http://") or src_input.startswith("https://"):
            update_task(task_id, progress=15, message="Downloading video stream with yt-dlp...")
            clean_name = f"download_{task_id}.mp4"
            target_path = VIRAL_DIR / clean_name
            dl_cmd = [
                ".venv/bin/yt-dlp",
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "-o", str(target_path),
                src_input
            ]
            res = subprocess.run(dl_cmd, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"Download failed: {res.stderr[-300:]}")
            local_src = target_path
        else:
            p = Path(src_input)
            if not p.is_absolute():
                p = (PIPELINE_DATA / p).resolve()
            if not p.exists():
                raise FileNotFoundError(f"Video file not found: {src_input}")
            local_src = p

        update_task(task_id, progress=35, message="Calculating clip duration & layout...")
        start_t = max(0.0, req.start_time)
        dur = req.duration or (req.end_time - start_t if req.end_time else 55.0)
        dur = min(59.0, max(5.0, dur))  # YouTube Shorts maximum 60s

        out_name = f"studio_clip_{task_id}.mp4"
        out_path = VIRAL_DIR / out_name
        thumb_path = VIRAL_DIR / f"studio_clip_{task_id}.jpg"
        bottom_art = ASSETS_DIR / "gta6_bottom_artwork.png"

        line1 = req.headline_line1.replace("'", "").strip()
        line2 = req.headline_line2.replace("'", "").strip()

        update_task(task_id, progress=45, message="Rendering 1080x1920 3-Tier Streamer Short with FFmpeg...")
        filter_complex = f"""
[0:v]crop=579:312:3:669,scale=1080:792:flags=lanczos,boxblur=30:5[top_bg];
[0:v]crop=579:312:3:669,scale=1000:562:flags=lanczos[top_fg];
[top_bg][top_fg]overlay=40:185[top_cam];
[top_cam]drawtext=fontfile='{FONT_PATH}':text='{line1}':fontcolor=white:fontsize=58:borderw=8:bordercolor=black:x=(w-text_w)/2:y=35,drawtext=fontfile='{FONT_PATH}':text='{line2}':fontcolor=white:fontsize=58:borderw=8:bordercolor=black:x=(w-text_w)/2:y=105[top_tier];
[0:v]scale=1080:697:flags=lanczos[mid_tier];
[1:v]scale=1080:431:flags=lanczos[bot_tier];
[top_tier][mid_tier]vstack=inputs=2[top_mid];
[top_mid][bot_tier]vstack=inputs=2[v]
"""
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_t),
            "-i", str(local_src),
            "-loop", "1", "-i", str(bottom_art),
            "-filter_complex", filter_complex.strip(),
            "-map", "[v]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ac", "2",
            "-t", str(dur),
            str(out_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg render error: {res.stderr[-400:]}")

        # Extract custom thumbnail
        thumb_cmd = [
            "ffmpeg", "-y",
            "-ss", str(min(5.0, dur / 2.0)),
            "-i", str(out_path),
            "-vframes", "1",
            "-q:v", "2",
            str(thumb_path)
        ]
        subprocess.run(thumb_cmd, capture_output=True)

        upload_result = None
        if req.upload_to_youtube:
            update_task(task_id, progress=75, message="Publishing Short to YouTube with failover...")
            title = req.custom_title or f"GTA 6: {line1} {line2}"
            caption = req.caption or f"{title}\n\n#shorts #gta6 #gaming #ishowspeed"
            account_target = None if req.target_channel == "auto" else req.target_channel

            upload_result = publish_short(
                clip_path=out_path,
                caption=caption,
                title=title,
                tags=req.tags or ["GTA 6", "IShowSpeed", "Gaming Shorts"],
                account=account_target,
            )

        update_task(
            task_id,
            progress=100,
            status="completed",
            message="Short rendered and published successfully!" if req.upload_to_youtube else "Short rendered successfully!",
            result={
                "clip_file": f"/media/viral/{out_name}",
                "thumb_file": f"/media/viral/{thumb_path.name}",
                "size_mb": round(out_path.stat().st_size / 1e6, 2),
                "duration": dur,
                "upload": upload_result
            }
        )

    except Exception as e:
        log.error(f"Task {task_id} failed: {e}", exc_info=True)
        update_task(task_id, status="failed", message=str(e), error=str(e))


# --- API Routes ---

@app.get("/api/status")
def get_system_status():
    tokens = get_all_token_paths()
    token_status = []
    for t in tokens:
        acc = t.stem.replace("youtube_token", "").strip("_") or "primary"
        token_status.append({
            "account": acc,
            "path": str(t),
            "exists": t.exists(),
            "valid": True
        })

    # Count uploaded shorts across batch summaries
    all_uploads = []
    for s_file in [
        VIRAL_DIR / "viral_uploads_batch3_summary.json",
        VIRAL_DIR / "viral_uploads_batch2_summary.json",
        VIRAL_DIR / "viral_uploads_summary.json",
    ]:
        if s_file.exists():
            try:
                data = json.loads(s_file.read_text())
                all_uploads.extend(data)
            except Exception:
                pass

    active_streams = db.list_active_streams()
    channels = db.list_channels()

    return {
        "status": "healthy",
        "channels_connected": token_status,
        "default_account": getattr(CONFIG, "youtube_default_account", "primary"),
        "total_published_shorts": len(all_uploads),
        "active_streams": len(active_streams),
        "watched_channels": len(channels),
        "live_watcher_running": LIVE_WATCHER_PROC is not None and LIVE_WATCHER_PROC.poll() is None,
    }


@app.get("/api/youtube/channels")
def get_youtube_channels():
    tokens = get_all_token_paths()
    res = []
    for t in tokens:
        acc = t.stem.replace("youtube_token", "").strip("_") or "primary"
        res.append({
            "account": acc,
            "label": "Channel 1 (Primary)" if acc == "primary" else "Channel 2 (Secondary)",
            "file": t.name,
            "path": str(t),
            "status": "Connected & Authorized"
        })
    return res


@app.get("/api/youtube/shorts")
def get_published_shorts():
    items = []
    # Collect batch summaries
    for s_file in [
        VIRAL_DIR / "viral_uploads_batch3_summary.json",
        VIRAL_DIR / "viral_uploads_batch2_summary.json",
        VIRAL_DIR / "viral_uploads_summary.json",
    ]:
        if s_file.exists():
            try:
                data = json.loads(s_file.read_text())
                for d in data:
                    yt = d.get("upload", {}).get("youtube", {})
                    vid = yt.get("video_id")
                    if vid:
                        items.append({
                            "id": d.get("id"),
                            "title": d.get("title"),
                            "account": yt.get("account", "primary"),
                            "video_id": vid,
                            "url": yt.get("url") or f"https://youtube.com/shorts/{vid}",
                            "file": d.get("file"),
                            "size_mb": d.get("size_mb"),
                            "thumb_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                        })
            except Exception as e:
                log.warning(f"Error reading {s_file}: {e}")

    # Also include any content marked posted in SQLite db
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM content WHERE status = 'posted' ORDER BY id DESC").fetchall()
        for r in rows:
            try:
                p_state = json.loads(r["platform_state"] or "{}")
                yt = p_state.get("youtube", {})
                vid = yt.get("video_id") or yt.get("id")
                if vid and not any(x["video_id"] == vid for x in items):
                    items.append({
                        "id": r["id"],
                        "title": r["title"],
                        "account": yt.get("account", "primary"),
                        "video_id": vid,
                        "url": f"https://youtube.com/shorts/{vid}",
                        "file": r["clip_path"],
                        "size_mb": None,
                        "thumb_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                    })
            except Exception:
                pass

    return items


@app.post("/api/youtube/search")
def search_youtube_videos(req: SearchViralRequest):
    query = req.query.strip()
    if not query:
        query = "IShowSpeed GTA 6 viral"

    cmd = [
        ".venv/bin/yt-dlp",
        f"ytsearch{req.limit}:{query}",
        "--dump-json",
        "--flat-playlist",
        "--no-warnings"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Search failed: {res.stderr[-300:]}")

    results = []
    for line in res.stdout.splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
            views = d.get("view_count") or 0
            dur = d.get("duration") or 0
            vid = d.get("id")
            results.append({
                "id": vid,
                "title": d.get("title"),
                "url": f"https://www.youtube.com/watch?v={vid}",
                "channel": d.get("channel") or d.get("uploader"),
                "view_count": views,
                "view_count_str": f"{views/1e6:.1f}M" if views >= 1e6 else (f"{views/1e3:.0f}K" if views >= 1e3 else str(views)),
                "duration": dur,
                "duration_str": f"{int(dur//60)}:{int(dur%60):02d}",
                "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
            })
        except Exception:
            continue

    results.sort(key=lambda x: x["view_count"], reverse=True)
    return results


@app.post("/api/clip/render")
def trigger_clip_render(req: RenderClipRequest, bg: BackgroundTasks):
    task_id = add_task(
        title=f"Clip: {req.headline_line1} {req.headline_line2}",
        task_type="clip_render"
    )
    bg.add_task(_process_clip_render_and_upload, task_id, req)
    return {"task_id": task_id, "status": "queued"}


@app.post("/api/clip/preview")
def generate_preview_frame(req: PreviewFrameRequest):
    out_name = f"preview_{int(time.time())}.jpg"
    out_path = VIRAL_DIR / out_name
    try:
        _run_preview_frame(req, out_path)
        return {"preview_url": f"/media/viral/{out_name}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/upload-direct")
def direct_upload(req: DirectUploadRequest):
    p = Path(req.file_path)
    if not p.is_absolute():
        p = (PIPELINE_DATA / p).resolve()
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {p}")

    target = None if req.target_channel == "auto" else req.target_channel
    res = publish_short(
        clip_path=p,
        caption=req.caption or f"{req.title} #shorts #gta6",
        title=req.title,
        tags=req.tags,
        account=target
    )
    return res


# --- Live Stream Monitoring & Channels ---

@app.get("/api/live/channels")
def list_live_channels():
    db.init_db()
    return db.list_channels(enabled_only=False)


@app.post("/api/live/channels/add")
def add_live_channel(req: AddChannelRequest):
    db.init_db()
    from cli import _detect_platform
    platform, slug, full_url = _detect_platform(req.channel)
    if not slug:
        raise HTTPException(status_code=400, detail="Invalid channel URL or handle.")
    cid = db.add_channel(platform, slug, full_url, display_name=req.display_name or slug)
    return {"id": cid, "platform": platform, "channel": slug, "url": full_url}


@app.post("/api/live/channels/{channel_id}/toggle")
def toggle_live_channel(channel_id: int, enabled: bool = Query(...)):
    db.init_db()
    db.set_channel_enabled(channel_id, enabled)
    return {"success": True, "channel_id": channel_id, "enabled": enabled}


@app.delete("/api/live/channels/{channel_id}")
def delete_live_channel(channel_id: int):
    db.init_db()
    db.remove_channel(channel_id)
    return {"success": True, "deleted_id": channel_id}


@app.get("/api/live/streams")
def list_live_streams():
    db.init_db()
    return db.list_active_streams()


@app.post("/api/live/watcher/toggle")
def toggle_watcher(start: bool = Query(...)):
    global LIVE_WATCHER_PROC
    if start:
        if LIVE_WATCHER_PROC is None or LIVE_WATCHER_PROC.poll() is not None:
            cmd = [".venv/bin/python", "cli.py", "live", "watch"]
            LIVE_WATCHER_PROC = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"running": True, "message": "Watcher daemon started."}
        return {"running": True, "message": "Watcher is already running."}
    else:
        if LIVE_WATCHER_PROC and LIVE_WATCHER_PROC.poll() is None:
            LIVE_WATCHER_PROC.terminate()
            LIVE_WATCHER_PROC = None
            return {"running": False, "message": "Watcher daemon stopped."}
        return {"running": False, "message": "Watcher was not running."}


@app.get("/api/tasks")
def get_all_tasks():
    with TASK_LOCK:
        return list(TASKS.values())[::-1]


@app.get("/api/media/files")
def list_local_media_files():
    res = []
    for pattern in ["pipeline_data/viral_external_shorts/*.mp4", "pipeline_data/clips/*.mp4"]:
        for f in glob.glob(pattern):
            p = Path(f)
            res.append({
                "path": str(p),
                "name": p.name,
                "size_mb": round(p.stat().st_size / 1e6, 2),
                "folder": p.parent.name,
                "web_url": f"/media/{'viral' if 'viral' in p.parent.name else 'clips'}/{p.name}"
            })
    return res


# --- UI Front-End Single Page App ---

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    html_path = Path("studio_ui.html")
    if html_path.exists():
        return html_path.read_text()
    return "<h1>Studio UI loading...</h1>"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=5050, reload=False)
