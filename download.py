"""Detect whether a URL is a YouTube/Vimeo link or a local path, and download
the source video to the local downloads dir. Idempotent: if the file already
exists, it is reused."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from config import CONFIG
from db import add_concept


def detect_source(value: str) -> str:
    """Return 'youtube' for any http(s) URL we can pass to yt-dlp, or 'local'
    for an existing filesystem path."""
    if value.startswith("http://") or value.startswith("https://"):
        return "youtube"  # yt-dlp handles Vimeo, Twitch, etc. too
    if Path(value).expanduser().exists():
        return "local"
    raise ValueError(f"Cannot interpret {value!r} as a URL or a local file path.")


def add_video_to_queue(value: str, title: str | None = None) -> int:
    """Public helper: detect the source and insert a new concept row."""
    source = detect_source(value)
    return add_concept(value, source, title=title)


def download_source(video_url: str, source: str, concept_id: int) -> Path:
    """Return a local filesystem path to the source video file.

    - For 'local' sources we just symlink into downloads/ so the rest of the
      pipeline has a uniform interface.
    - For 'youtube' sources we call yt-dlp.
    """
    if source == "local":
        src = Path(video_url).expanduser().resolve()
        if not src.exists():
            raise FileNotFoundError(f"Local source not found: {src}")
        dst = CONFIG.downloads_dir / f"concept_{concept_id}{src.suffix or '.mp4'}"
        if not dst.exists():
            dst.symlink_to(src)
        return dst

    if source == "youtube":
        dst = CONFIG.downloads_dir / f"concept_{concept_id}.%(ext)s"
        # yt-dlp will replace %(ext)s with the real container.
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--no-progress",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4/best",
            "--merge-output-format", "mp4",
            "-o", str(dst),
            video_url,
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        # Resolve the actual saved path.
        matches = list(CONFIG.downloads_dir.glob(f"concept_{concept_id}.*"))
        if not matches:
            raise RuntimeError(f"yt-dlp reported success but no file was written for {video_url}")
        # Prefer mp4 if it exists.
        mp4 = [m for m in matches if m.suffix.lower() == ".mp4"]
        return (mp4 or matches)[0]

    raise ValueError(f"Unknown source: {source}")


# --- Helper: ensure yt-dlp and ffmpeg are installed ----------------------

def ensure_tools_installed() -> None:
    """Soft check. Errors out with a helpful message if missing."""
    missing = []
    for tool in ("yt-dlp", "ffmpeg"):
        if not shutil.which(tool):
            missing.append(tool)
    if missing:
        raise SystemExit(
            "Missing required binaries: " + ", ".join(missing) + ".\n"
            "Install with Homebrew:\n  brew install " + " ".join(missing)
        )
