"""Centralised configuration. Reads from .env and falls back to sane defaults."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except Exception:
    pass

# Load .env from the project root (one level above this file when installed
# as a package, or the same dir in flat layout).
_PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _env_int(key: str, default: int) -> int:
    raw = _env(key, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class Config:
    # Paths
    data_dir: Path = field(default_factory=lambda: Path(_env("PIPELINE_DATA_DIR") or str(Path.home() / "clips_pipeline_data")))
    db_path: Path = field(default=None)
    downloads_dir: Path = field(default=None)
    clips_dir: Path = field(default=None)
    transcripts_dir: Path = field(default=None)
    logs_dir: Path = field(default=None)

    # Antigravity
    antigravity_model_path: str = field(default_factory=lambda: _env("ANTIGRAVITY_MODEL_PATH"))
    antigravity_backend: str = field(default_factory=lambda: _env("ANTIGRAVITY_BACKEND", "gpu"))
    max_clips_per_video: int = field(default_factory=lambda: _env_int("MAX_CLIPS_PER_VIDEO", 10))
    clip_min_seconds: int = field(default_factory=lambda: _env_int("CLIP_MIN_SECONDS", 30))
    clip_max_seconds: int = field(default_factory=lambda: _env_int("CLIP_MAX_SECONDS", 60))

    # ffmpeg
    ffmpeg_path: str = field(default_factory=lambda: _env("FFMPEG_PATH", "ffmpeg"))
    caption_style: str = field(default_factory=lambda: _env("CAPTION_STYLE", "karaoke"))
    output_width: int = field(default_factory=lambda: _env_int("OUTPUT_WIDTH", 720))
    output_height: int = field(default_factory=lambda: _env_int("OUTPUT_HEIGHT", 1280))

    # Instagram
    ig_access_token: str = field(default_factory=lambda: _env("IG_ACCESS_TOKEN"))
    ig_user_id: str = field(default_factory=lambda: _env("IG_USER_ID"))
    public_video_base_url: str = field(default_factory=lambda: _env("PUBLIC_VIDEO_BASE_URL"))

    # TikTok
    tiktok_client_key: str = field(default_factory=lambda: _env("TIKTOK_CLIENT_KEY"))
    tiktok_client_secret: str = field(default_factory=lambda: _env("TIKTOK_CLIENT_SECRET"))
    tiktok_access_token: str = field(default_factory=lambda: _env("TIKTOK_ACCESS_TOKEN"))
    tiktok_open_id: str = field(default_factory=lambda: _env("TIKTOK_OPEN_ID"))

    # YouTube (Data API v3, OAuth 2.0)
    # No env vars needed - we look for client_secret.json + token.json in
    # the data dir. See README for the one-time OAuth setup.
    youtube_enabled_flag: bool = field(default_factory=lambda: _env("YOUTUBE_ENABLED", "1").lower() in ("1", "true", "yes"))
    youtube_default_account: str = field(default_factory=lambda: _env("YOUTUBE_DEFAULT_ACCOUNT", "channel2"))
    delete_clips_after_upload: bool = field(default_factory=lambda: _env("DELETE_CLIPS_AFTER_UPLOAD", "1").lower() in ("1", "true", "yes"))

    # --- Live mode ---
    # The watcher daemon polls every N seconds.
    live_poll_interval_seconds: int = field(default_factory=lambda: _env_int("LIVE_POLL_INTERVAL_SECONDS", 120))
    # Whisper window: every N seconds we take the last N seconds of audio and
    # transcribe. Lower = faster clips, more CPU.
    live_transcribe_window_seconds: int = field(default_factory=lambda: _env_int("LIVE_TRANSCRIBE_WINDOW_SECONDS", 60))
    # How often the curator runs on the rolling transcript.
    live_curate_interval_seconds: int = field(default_factory=lambda: _env_int("LIVE_CURATE_INTERVAL_SECONDS", 120))
    # Recording quality (streamlink format string). "best" = source quality,
    # which can be 6Mbps+ on Twitch. Fallback list supports Twitch and YouTube.
    live_stream_quality: str = field(default_factory=lambda: _env("LIVE_STREAM_QUALITY", "best,1080p60,1080p,720p60,720p"))
    # Cleanup: delete source recordings N hours after stream end.
    live_cleanup_hours: int = field(default_factory=lambda: _env_int("LIVE_CLEANUP_HOURS", 24))
    # Max parallel recordings. 0 = no limit (all channels recorded in parallel).
    live_max_parallel: int = field(default_factory=lambda: _env_int("LIVE_MAX_PARALLEL", 0))
    # Spacing between live clips picked for the same stream (15 min = 900s ensures only peak moments)
    live_min_clip_spacing_seconds: int = field(default_factory=lambda: _env_int("LIVE_MIN_CLIP_SPACING_SECONDS", 900))
    # Cap live clips per stream so we don't upload low-value clips or spam channels
    max_live_clips_per_stream: int = field(default_factory=lambda: _env_int("MAX_LIVE_CLIPS_PER_STREAM", 3))
    # Minimum viral score (1-10) required to clip and upload
    min_viral_score: float = field(default_factory=lambda: float(_env("MIN_VIRAL_SCORE", "8.0")))

    # Logging
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))

    def __post_init__(self) -> None:
        # Resolve data_dir and the sub-paths
        self.data_dir = Path(self.data_dir).expanduser()
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.downloads_dir = self.data_dir / "downloads"
        self.clips_dir = self.data_dir / "clips"
        self.transcripts_dir = self.data_dir / "transcripts"
        self.logs_dir = self.data_dir / "logs"
        self.streams_dir = self.data_dir / "streams"
        self.live_transcripts_dir = self.data_dir / "live_transcripts"
        for d in (self.downloads_dir, self.clips_dir, self.transcripts_dir,
                  self.logs_dir, self.streams_dir, self.live_transcripts_dir):
            d.mkdir(parents=True, exist_ok=True)

        if _env("DB_PATH"):
            self.db_path = Path(_env("DB_PATH")).expanduser()
        else:
            self.db_path = self.data_dir / "state.db"

    # Convenience flags ------------------------------------------------------
    @property
    def instagram_enabled(self) -> bool:
        return bool(self.ig_access_token and self.ig_user_id)

    @property
    def tiktok_enabled(self) -> bool:
        return bool(self.tiktok_access_token and self.tiktok_open_id and self.tiktok_client_key)

    @property
    def youtube_client_secret_path(self) -> Path:
        return self.data_dir / "youtube_client_secret.json"

    @property
    def youtube_token_path(self) -> Path:
        return self.data_dir / "youtube_token.json"

    @property
    def youtube_enabled(self) -> bool:
        """True when either a cached OAuth token exists, or a client_secret is
        present (i.e. setup is in progress). Once the user runs
        `python cli.py youtube-auth`, the token is cached and this stays True."""
        if not self.youtube_enabled_flag:
            return False
        if self.youtube_token_path.exists() or self.youtube_client_secret_path.exists():
            return True
        return bool(list(self.data_dir.glob("youtube_token_*.json")))

    @property
    def antigravity_enabled(self) -> bool:
        """True when a model path is configured. Otherwise curator falls back
        to a heuristic so the pipeline still works."""
        return bool(self.antigravity_model_path) and Path(self.antigravity_model_path).exists()


# Singleton
CONFIG = Config()
