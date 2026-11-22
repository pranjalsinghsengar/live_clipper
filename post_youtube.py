"""YouTube Shorts publishing via YouTube Data API v3.

Unlike Instagram and TikTok, YouTube uses OAuth 2.0 user consent (not a
static API key) because uploading to a channel is a user action. We cache
the refresh token after the first interactive auth.

Prerequisites:
  - A Google Cloud project with YouTube Data API v3 enabled.
  - OAuth 2.0 Client ID (Desktop app type).
  - The downloaded JSON saved as youtube_client_secret.json in PIPELINE_DATA_DIR.
  - One-time interactive auth via `python cli.py youtube-auth`.

Free quota: 10,000 units/day. A video upload costs 1600 units, so you can
upload ~6 videos/day for free. Our pipeline posts at most 2/day, so plenty
of headroom.

A video is classified as a Short by YouTube when:
  - It is vertical (aspect ratio 9:16 or taller).
  - It is 60 seconds or shorter.
Both are guaranteed by our clip.py renderer.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from config import CONFIG

log = logging.getLogger("post_youtube")

# Token cache locations are defined in CONFIG (data_dir/youtube_*.json).
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

DEFAULT_GTA6_TAGS = [
    "GTA 6",
    "GTA VI",
    "Grand Theft Auto 6",
    "Grand Theft Auto VI",
    "GTA 6 Gameplay",
    "GTA 5 vs GTA 6",
    "GTA 6 Comparison",
    "Techno Gamerz",
    "Techno Gamerz GTA 6",
    "Techno Gamerz vs CarryMinati",
    "IShowSpeed",
    "IShowSpeed GTA 6",
    "Speed GTA 6",
    "CarryisLive",
    "CarryMinati",
    "Mythpat",
    "MortaL",
    "Vice City",
    "Rockstar Games",
    "GTA 6 Funny Moments",
    "GTA 6 Clips",
    "Gaming Shorts",
    "Shorts",
    "Trending",
]


_EXCEEDED_ACCOUNTS: set[str] = set()


# --- OAuth ----------------------------------------------------------------

def get_all_token_paths(preferred_account: str | None = None) -> list[Path]:
    """Return all cached YouTube OAuth tokens (primary and secondary accounts).
    Sorts preferred_account or CONFIG.youtube_default_account first."""
    paths: list[Path] = []
    if CONFIG.youtube_token_path.exists():
        paths.append(CONFIG.youtube_token_path)
    for p in sorted(CONFIG.data_dir.glob("youtube_token_*.json")):
        if p not in paths:
            paths.append(p)

    target = preferred_account or getattr(CONFIG, "youtube_default_account", None)
    if target:
        target_clean = target.strip().lower()
        def _sort_key(p: Path) -> int:
            label = p.stem.replace("youtube_token", "").strip("_").lower()
            if label == target_clean or (not label and target_clean in ("primary", "default")):
                return 0
            return 1
        paths.sort(key=_sort_key)
    return paths


def get_authenticated_service(token_path: Path | None = None):
    """Build an authenticated YouTube service object for a specific token or primary.

    Uses the cached token if present and valid; refreshes if expired; falls
    back to interactive OAuth flow if no token exists.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    if token_path is None:
        tokens = get_all_token_paths()
        token_path = tokens[0] if tokens else CONFIG.youtube_token_path

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(
            str(token_path), SCOPES
        )

    if creds and creds.expired and creds.refresh_token:
        # Silent refresh - no browser needed.
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
    elif not creds or not creds.valid:
        raise RuntimeError(
            f"YouTube OAuth token at {token_path} is missing or invalid. Run:\n"
            f"  python cli.py youtube-auth\n"
            f"from the project directory to authorise interactively first."
        )

    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def run_interactive_auth(account: str | None = None) -> Path:
    """One-time interactive OAuth flow. Opens a browser, asks the user to
    authorise, saves the token to disk. Called by `python cli.py youtube-auth`."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CONFIG.youtube_client_secret_path.exists():
        raise FileNotFoundError(
            f"YouTube client secret not found at "
            f"{CONFIG.youtube_client_secret_path}.\n"
            f"Download the OAuth 2.0 Client ID JSON from Google Cloud Console\n"
            f"and save it there first."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CONFIG.youtube_client_secret_path), SCOPES
    )
    # Opens a local server on a free port, browser opens to Google's consent
    # page, user clicks Allow, redirect captures the auth code.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    if account and account.strip():
        clean_acc = account.strip().lower().replace(" ", "_")
        dest = CONFIG.data_dir / f"youtube_token_{clean_acc}.json"
    else:
        dest = CONFIG.youtube_token_path

    dest.write_text(creds.to_json())
    print(f"YouTube OAuth token cached at: {dest}")
    return dest


# --- Upload ---------------------------------------------------------------

def extract_thumbnail(clip_path: Path, out_path: Path | None = None) -> Path:
    """Extract a high-quality vertical poster frame from the middle of the clip."""
    if out_path is None:
        out_path = clip_path.with_suffix(".jpg")
    if out_path.exists() and out_path.stat().st_size > 10_000:
        return out_path
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(clip_path)],
            check=True, capture_output=True, text=True,
        )
        dur = float(out.stdout.strip())
        midpoint = max(0.5, dur / 2.0)
    except Exception:
        midpoint = 5.0

    cmd = [
        CONFIG.ffmpeg_path or "ffmpeg",
        "-y",
        "-ss", f"{midpoint:.3f}",
        "-i", str(clip_path),
        "-vframes", "1",
        "-q:v", "2",
        "-update", "1",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    try:
        from thumbnail_designer import create_streamer_thumbnail
        streamer = "CarryMinati"
        headline = "GTA 5 VS GTA 6"
        subheadline = "WHICH IS BETTER?! 😱"
        stem = clip_path.stem.lower()
        if "police" in stem or "cop" in stem:
            subheadline = "5-STAR POLICE CHASE! 🚨"
        elif "graphics" in stem or "nightlife" in stem or "neon" in stem:
            subheadline = "INSANE GRAPHICS! 🤯⚡"
        elif "water" in stem or "ocean" in stem:
            subheadline = "WATER & WAVE PHYSICS! 🌊"
        elif "bike" in stem or "crash" in stem or "ragdoll" in stem:
            subheadline = "CRASH & RAGDOLL PHYSICS! 💀"
        elif "speed" in stem or "ishowspeed" in stem:
            streamer = "IShowSpeed"
        elif "techno" in stem:
            streamer = "Techno Gamerz"

        create_streamer_thumbnail(out_path, out_path, streamer_name=streamer, headline=headline, subheadline=subheadline)
    except Exception as e:
        log.warning("Could not apply streamer thumbnail enhancements: %s", e)

    return out_path


def _publish_short_to_service(
    youtube,
    token_path: Path,
    clip_path: Path,
    caption: str,
    title: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    from googleapiclient.http import MediaFileUpload

    raw_title = (title or caption.split("\n")[0] or "GTA 6 Best Moment").strip()
    if "#shorts" not in raw_title.lower():
        if len(raw_title) + len(" #shorts #gta6") <= 100:
            final_title = f"{raw_title} #shorts #gta6"
        elif len(raw_title) + len(" #shorts") <= 100:
            final_title = f"{raw_title} #shorts"
        else:
            final_title = raw_title[:91] + " #shorts"
    else:
        final_title = raw_title[:100]

    final_tags = list(DEFAULT_GTA6_TAGS)
    
    # Dynamic context-aware SEO tags injection
    lower_context = f"{raw_title} {caption}".lower()
    if "techno" in lower_context:
        for t in ["Techno Gamerz GTA", "Ujjwal Chaurasia", "Techno Gamerz Gameplay", "Techno Gamerz Live", "Techno Gamerz Vice City"]:
            if t not in final_tags:
                final_tags.append(t)
    if "carry" in lower_context:
        for t in ["CarryisLive GTA", "Ajey Nagar", "CarryMinati Live", "Carry Live Stream"]:
            if t not in final_tags:
                final_tags.append(t)
    if "speed" in lower_context:
        for t in ["IShowSpeed Live", "Speed Stream Highlights", "Speed GTA 6 Moments"]:
            if t not in final_tags:
                final_tags.append(t)
    if "vs" in lower_context or "compare" in lower_context or "comparison" in lower_context:
        for t in ["GTA 5 vs GTA 6", "GTA 6 vs GTA 5 Graphics", "GTA 6 Comparison Shorts", "GTA 6 Next Gen Graphics", "GTA Vice City Comparison"]:
            if t not in final_tags:
                final_tags.append(t)

    if tags:
        for t in tags:
            if t not in final_tags:
                final_tags.append(t)

    # YouTube API enforces a strict <= 500 character limit on all tags combined.
    # Keep only clean alphanumeric/space tags up to 400 characters total.
    clean_tags = []
    current_char_count = 0
    for t in final_tags:
        cleaned_t = re.sub(r"[<>]", "", t).strip()
        if not cleaned_t:
            continue
        tag_cost = len(cleaned_t) + (1 if clean_tags else 0)
        if current_char_count + tag_cost <= 400:
            clean_tags.append(cleaned_t)
            current_char_count += tag_cost
        else:
            break
    final_tags = clean_tags

    clean_caption = caption.strip()
    description = (
        f"{clean_caption}\n\n"
        f"🎮 GTA 6 (Grand Theft Auto VI) Gameplay & Highlights!\n"
        f"🔥 Watch top gaming moments from Vice City.\n\n"
        f"Game: Grand Theft Auto VI (GTA 6)\n"
        f"Developer: Rockstar Games\n\n"
        f"#shorts #gta6 #gaming #carryminati #mythpat #ishowspeed #vicecity "
        f"#rockstargames #grandtheftautovi #trendingshorts"
    ).strip()[:5000]

    body = {
        "snippet": {
            "title": final_title,
            "description": description,
            "categoryId": "20",
            "tags": final_tags,
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "embeddable": True,
        },
    }

    thumb_path = None
    try:
        thumb_path = extract_thumbnail(clip_path)
    except Exception as e:
        log.warning("Could not extract thumbnail for %s: %s", clip_path.name, e)

    media = MediaFileUpload(
        str(clip_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,
    )

    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log.info("Upload progress: %d%%", int(status.progress() * 100))

    video_id = response.get("id")
    if not video_id:
        raise RuntimeError(f"YouTube upload returned no id: {response}")

    account_label = token_path.stem.replace("youtube_token", "").strip("_") or "primary"
    log.info("Uploaded YouTube Short via account '%s': https://youtube.com/shorts/%s (title: %s)",
             account_label, video_id, final_title)

    thumb_uploaded = False
    if thumb_path and thumb_path.exists():
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumb_path), mimetype="image/jpeg"),
            ).execute()
            thumb_uploaded = True
            log.info("Set custom thumbnail for video %s on account '%s'", video_id, account_label)
        except Exception as e:
            log.warning(
                "Custom thumbnail upload skipped for %s (Channel may need phone verification at youtube.com/verify): %s",
                video_id, e
            )

    if CONFIG.delete_clips_after_upload:
        try:
            if clip_path.exists():
                clip_path.unlink()
            ass_path = clip_path.with_suffix(".ass")
            if ass_path.exists():
                ass_path.unlink()
            if thumb_path and thumb_path.exists():
                thumb_path.unlink()
        except OSError:
            pass

    return {
        "youtube": {
            "video_id": video_id,
            "account": account_label,
            "status": "uploaded",
            "url": f"https://youtube.com/shorts/{video_id}",
            "custom_thumbnail": thumb_uploaded,
        }
    }


def publish_short(
    clip_path: Path,
    caption: str,
    title: str | None = None,
    tags: list[str] | None = None,
    account: str | None = None,
) -> dict[str, Any]:
    """Upload a vertical clip as a YouTube Short.

    Automatically fails over across all authenticated YouTube channels/accounts
    if an account hits its daily upload limit (uploadLimitExceeded).
    """
    if not CONFIG.youtube_enabled:
        return {"skipped": "youtube not configured"}

    from googleapiclient.errors import HttpError

    token_paths = get_all_token_paths(preferred_account=account)
    if not token_paths:
        return {"skipped": "no valid youtube tokens found"}

    # Sort known quota-exhausted accounts to the end so they aren't retried needlessly
    token_paths.sort(key=lambda p: 1 if (p.stem.replace("youtube_token", "").strip("_") or "primary") in _EXCEEDED_ACCOUNTS else 0)

    last_error_dict = None
    for token_path in token_paths:
        account_label = token_path.stem.replace("youtube_token", "").strip("_") or "primary"
        try:
            service = get_authenticated_service(token_path)
            return _publish_short_to_service(service, token_path, clip_path, caption, title, tags)
        except HttpError as e:
            err_str = str(e)
            if "uploadLimitExceeded" in err_str or "quotaExceeded" in err_str or "dailyLimitExceeded" in err_str:
                _EXCEEDED_ACCOUNTS.add(account_label)
                log.warning("Account '%s' reached limit (%s). Attempting failover...",
                            account_label, err_str[:120])
                last_error_dict = {
                    "youtube": {
                        "error": "limitExceeded",
                        "account": account_label,
                        "message": f"Account '{account_label}' reached daily upload or quota limit."
                    }
                }
                continue
            raise

    # All accounts exceeded limit
    log.warning("All %d connected YouTube accounts reached daily upload limit.", len(token_paths))
    return last_error_dict or {
        "youtube": {
            "error": "uploadLimitExceeded",
            "message": "All connected YouTube accounts reached daily upload limit."
        }
    }
