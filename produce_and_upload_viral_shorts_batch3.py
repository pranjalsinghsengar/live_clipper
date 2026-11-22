"""Batch 3 Producer & Multi-Channel Publisher for Viral GTA 6 Moments.
Layout: 3-tier streamer layout (1080x1920) matching reference GOwKsw3W7cQ.
Channels: Channel 2 (channel2) and Channel 1 (primary) failover.
"""
import os
import sys
import json
import logging
import subprocess
from pathlib import Path

# Ensure static-ffmpeg is initialized for ffmpeg 7.0 with drawtext & libass
import static_ffmpeg
static_ffmpeg.add_paths()

from post_youtube import publish_short

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("viral_shorts_batch3")

DATA_DIR = Path("pipeline_data/viral_external_shorts")
ASSETS_DIR = Path("assets")
BOTTOM_ARTWORK = ASSETS_DIR / "gta6_bottom_artwork.png"

FONT_PATH = "/System/Library/Fonts/Supplemental/Impact.ttf"
if not os.path.exists(FONT_PATH):
    FONT_PATH = "/System/Library/Fonts/Impact.ttf"

BATCH3_CLIPS = [
    {
        "id": 11,
        "source": DATA_DIR / "boat_blade.mp4",
        "output": DATA_DIR / "viral_short_11.mp4",
        "thumb": DATA_DIR / "viral_short_11.jpg",
        "title": "GTA 6: THROWS A GUY INTO A BOAT BLADE! 💀🚤 #shorts #gta6",
        "caption": "Speed throws a guy into a spinning boat blade in GTA 6! 😭🚤 #ishowspeed #gta6 #funny #gaming #shorts",
        "line1": "THROWS A GUY INTO A",
        "line2": "SPINNING BOAT BLADE! 💀🚤",
        "target_account": "channel2",
        "tags": ["GTA 6 Boat", "Boat Propeller", "Speed GTA 6", "IShowSpeed Live"],
        "max_duration": None,
    },
    {
        "id": 12,
        "source": DATA_DIR / "lookalike.mp4",
        "output": DATA_DIR / "viral_short_12.mp4",
        "thumb": DATA_DIR / "viral_short_12.jpg",
        "title": "GTA 6: FINDS HIS EXACT LOOKALIKE! 😱💀 #shorts #gta6",
        "caption": "Speed finds his actual clone and lookalike NPC in GTA 6! 🤯💀 #ishowspeed #lookalike #gta6 #shorts #viral",
        "line1": "SPEED FINDS HIS EXACT",
        "line2": "LOOKALIKE IN GTA 6! 😱💀",
        "target_account": "channel2",
        "tags": ["IShowSpeed Lookalike", "Speed Twin GTA 6", "GTA 6 NPC", "IShowSpeed Live"],
        "max_duration": None,
    },
    {
        "id": 13,
        "source": DATA_DIR / "plane_throw.mp4",
        "output": DATA_DIR / "viral_short_13.mp4",
        "thumb": DATA_DIR / "viral_short_13.jpg",
        "title": "GTA 6: THROWS A GIRL OUT OF A PLANE! 😭✈️ #shorts #gta6",
        "caption": "Speed throws a girl out of a plane during a GTA 6 heist mission! 😭💀 #ishowspeed #gta6 #heist #shorts #funny",
        "line1": "THROWS A GIRL OUT OF",
        "line2": "A PLANE IN GTA 6! 😭✈️",
        "target_account": "channel2",
        "tags": ["GTA 6 Heist", "Plane Throw", "Speed Funny Moments", "Vice City"],
        "max_duration": None,
    },
    {
        "id": 14,
        "source": DATA_DIR / "subscribers.mp4",
        "output": DATA_DIR / "viral_short_14.mp4",
        "thumb": DATA_DIR / "viral_short_14.jpg",
        "title": "GTA 6: SPEED HITS 63 MILLION SUBS! 🎉👑 #shorts #gta6",
        "caption": "IShowSpeed officially hits 63 Million Subscribers live while playing GTA 6! 👑🎉 #ishowspeed #63million #speedlive #gta6 #shorts",
        "line1": "SPEED HITS 63 MILLION",
        "line2": "SUBS PLAYING GTA 6! 🎉👑",
        "target_account": "primary",
        "tags": ["IShowSpeed Milestone", "63 Million Subs", "Speed Live", "GTA 6 Stream"],
        "max_duration": None,
    },
    {
        "id": 15,
        "source": DATA_DIR / "meets_jimmy.mp4",
        "output": DATA_DIR / "viral_short_15.mp4",
        "thumb": DATA_DIR / "viral_short_15.jpg",
        "title": "GTA 6: MEETS JIMMY FROM GTA 5! 🤯🔥 #shorts #gta6",
        "caption": "Speed encounters Michael's son Jimmy De Santa in GTA 6! 🎮🔥 #gta5 #gta6 #jimmy #ishowspeed #shorts",
        "line1": "SPEED MEETS MICHAEL'S",
        "line2": "SON JIMMY IN GTA 6! 🤯🔥",
        "target_account": "primary",
        "tags": ["Jimmy De Santa", "GTA 5 Jimmy", "GTA 6 Cameo", "IShowSpeed GTA 6"],
        "max_duration": 58,
    },
    {
        "id": 16,
        "source": DATA_DIR / "niko_bellic.mp4",
        "output": DATA_DIR / "viral_short_16.mp4",
        "thumb": DATA_DIR / "viral_short_16.jpg",
        "title": "GTA 6: SPEED MEETS NIKO BELLIC FROM GTA 4! 😱🇷🇺 #shorts #gta6",
        "caption": "Speed runs into legendary protagonist Niko Bellic in GTA 6! 😱💀 #nikobellic #gta4 #gta6 #ishowspeed #shorts",
        "line1": "SPEED MEETS NIKO",
        "line2": "BELLIC IN GTA 6?! 😱🇷🇺",
        "target_account": "primary",
        "tags": ["Niko Bellic", "GTA 4 Niko", "GTA 6 Cameo", "IShowSpeed"],
        "max_duration": 55,
    },
]


def render_3tier_short(clip_info: dict) -> Path:
    out_path = clip_info["output"]
    if out_path.exists() and out_path.stat().st_size > 5_000_000:
        log.info(f"Clip {clip_info['id']} already rendered ({out_path.stat().st_size / 1e6:.2f} MB)")
        return out_path

    line1 = clip_info["line1"]
    line2 = clip_info["line2"]
    src = str(clip_info["source"])
    max_dur = clip_info.get("max_duration")

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
        "-i", src,
        "-loop", "1", "-i", str(BOTTOM_ARTWORK),
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
        "-shortest",
    ]
    if max_dur:
        cmd.extend(["-t", str(max_dur)])
    cmd.append(str(out_path))

    log.info(f"Rendering Viral Clip {clip_info['id']}: {clip_info['title']} -> {out_path.name}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        log.error(f"Render failed: {res.stderr[-500:]}")
        raise RuntimeError(f"FFmpeg failed with code {res.returncode}")

    # Generate custom thumbnail frame
    thumb_path = clip_info["thumb"]
    thumb_cmd = [
        "ffmpeg", "-y",
        "-ss", "10",
        "-i", str(out_path),
        "-vframes", "1",
        "-q:v", "2",
        str(thumb_path)
    ]
    subprocess.run(thumb_cmd, capture_output=True)

    log.info(f"Clip {clip_info['id']} rendered successfully! ({out_path.stat().st_size / 1e6:.2f} MB)")
    return out_path


def main():
    print("=== Rendering & Publishing Batch 3 (6 Clips across Channel 2 & Primary) ===")
    results = []

    for item in BATCH3_CLIPS:
        try:
            rendered_video = render_3tier_short(item)
            account_target = item["target_account"]
            print(f"\n--- Uploading Viral Clip {item['id']} (Target: {account_target}): {item['title']} ---")
            upload_res = publish_short(
                clip_path=rendered_video,
                caption=item["caption"],
                title=item["title"],
                tags=item["tags"],
                account=account_target,
            )
            print(f"Upload result for clip {item['id']}: {upload_res}")
            results.append({
                "id": item["id"],
                "title": item["title"],
                "file": str(rendered_video),
                "size_mb": round(rendered_video.stat().st_size / 1e6, 2),
                "target_account": account_target,
                "upload": upload_res,
            })
        except Exception as e:
            log.error(f"Error processing clip {item['id']}: {e}", exc_info=True)
            results.append({
                "id": item["id"],
                "title": item["title"],
                "error": str(e)
            })

    summary_file = DATA_DIR / "viral_uploads_batch3_summary.json"
    with open(summary_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n=== Completed Batch 3 ({len(results)}/6 Clips). Summary saved to {summary_file} ===")


if __name__ == "__main__":
    main()
