#!/usr/bin/env python3
"""Batch producer & uploader for YouTube's most viral GTA 6 clips.
Converts clips to the 3-tier viral streamer Shorts layout (GOwKsw3W7cQ style)
and publishes to YouTube Shorts with failover between Channel 1 and Channel 2.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

import static_ffmpeg
static_ffmpeg.add_paths()

from post_youtube import publish_short

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("viral_shorts")

OUT_DIR = Path("pipeline_data/viral_external_shorts")
OUT_DIR.mkdir(parents=True, exist_ok=True)
ARTWORK_PATH = Path("assets/gta6_bottom_artwork.png")

VIRAL_CLIPS = [
    {
        "id": 1,
        "src": Path("jet_engine.webm"),
        "ss": "00:00:00",
        "t": "48",
        "line1": "THROWS A GUY INTO",
        "line2": "A JET ENGINE?! 💀🔥",
        "title": "GTA 6: THROWS A GUY INTO A JET ENGINE?! 💀✈️ #shorts #gta6",
        "caption": "Speed discovers what happens when you push NPCs into airplane engines in GTA 6! 😭 #ishowspeed #gta6 #funny #gaming #shorts",
        "tags": ["GTA 6", "GTA VI", "IShowSpeed", "IShowSpeed GTA 6", "GTA 6 Jet Engine", "GTA 6 Viral", "GTA 6 Funny", "GTA 6 Shorts"],
    },
    {
        "id": 2,
        "src": Path("polar_bear.webm"),
        "ss": "00:00:54",
        "t": "50",
        "line1": "FREES POLAR BEAR",
        "line2": "(IMMEDIATELY REGRETS IT) 😭💀",
        "title": "GTA 6: FREES POLAR BEAR (IMMEDIATELY REGRETS IT) 😭💀 #shorts #gta6",
        "caption": "Speed tries to help animal activists liberate a polar bear and it instantly goes wrong! 💀 #ishowspeed #gta6 #fails #funny #shorts",
        "tags": ["GTA 6", "GTA VI", "IShowSpeed", "IShowSpeed GTA 6", "GTA 6 Polar Bear", "GTA 6 Animal Activists", "GTA 6 Funny", "GTA 6 Shorts"],
    },
    {
        "id": 3,
        "src": Path("scooter.webm"),
        "ss": "00:00:45",
        "t": "52",
        "line1": "STEALS AN OLD LADY’S",
        "line2": "MOBILITY SCOOTER! 😭🛵",
        "title": "GTA 6: STEALS AN OLD LADY'S SCOOTER! 😭🛵 #shorts #gta6",
        "caption": "Speed steals a grandma's scooter, instantly feels bad, then gets chased! 😂 #ishowspeed #gta6 #funny #gaming #shorts",
        "tags": ["GTA 6", "GTA VI", "IShowSpeed", "IShowSpeed GTA 6", "GTA 6 Mobility Scooter", "GTA 6 Funny Moments", "GTA 6 Viral", "GTA 6 Shorts"],
    },
    {
        "id": 4,
        "src": Path("hulk_monster.webm"),
        "ss": "00:00:05",
        "t": "50",
        "line1": "FINDS A HULK MONSTER",
        "line2": "IN GTA 6 SWAMP?! 😱🦍",
        "title": "GTA 6: FINDS A HULK MONSTER IN THE SWAMP?! 😱💀 #shorts #gta6",
        "caption": "Speed spots a terrifying Hulk-like beast wandering deep in the Vice City swamp! 🤯 #ishowspeed #gta6 #easteregg #gaming #shorts",
        "tags": ["GTA 6", "GTA VI", "IShowSpeed", "IShowSpeed GTA 6", "GTA 6 Hulk", "GTA 6 Swamp Monster", "GTA 6 Easter Egg", "GTA 6 Shorts"],
    },
    {
        "id": 5,
        "src": Path("breaks_setup.webm"),
        "ss": "00:00:15",
        "t": "50",
        "line1": "SPEED CRASHES OUT",
        "line2": "AFTER 50 HOURS! 🤬💥",
        "title": "GTA 6: SPEED CRASHES OUT AFTER 50 HOURS! 🤬💥 #shorts #gta6",
        "caption": "Speed completely loses his mind and smashes his streaming setup after 50 hours of GTA 6! 💀 #ishowspeed #speedrage #gta6 #viral #shorts",
        "tags": ["GTA 6", "GTA VI", "IShowSpeed", "IShowSpeed GTA 6", "IShowSpeed Rage", "IShowSpeed Breaks Setup", "GTA 6 50 Hours", "GTA 6 Shorts"],
    },
]

def render_viral_clip(item: dict) -> Path | None:
    src_video = item["src"]
    if not src_video.exists():
        log.warning("Source %s missing, skipping", src_video)
        return None

    cid = item["id"]
    out_file = OUT_DIR / f"viral_short_{cid:02d}.mp4"
    thumb_file = OUT_DIR / f"viral_short_{cid:02d}.jpg"

    l1 = item["line1"].replace("'", "’")
    l2 = item["line2"].replace("'", "’")

    filter_str = (
        "[0:v]split=2[v_for_cam][v_for_game];"
        "[v_for_cam]crop=579:312:3:669,split=2[cam_raw1][cam_raw2];"
        "[cam_raw1]scale=1080:792:flags=lanczos,boxblur=30:5[cam_bg];"
        "[cam_raw2]scale=1000:562:flags=lanczos[cam_sharp];"
        "[cam_bg][cam_sharp]overlay=x=40:y=185[top_part];"
        "[v_for_game]scale=1080:697:flags=lanczos[mid_part];"
        "[1:v]scale=1080:431:flags=lanczos[bot_part];"
        "[top_part][mid_part][bot_part]vstack=inputs=3,"
        f"drawtext=fontfile=/System/Library/Fonts/Supplemental/Impact.ttf:text='{l1}':fontcolor=white:fontsize=58:bordercolor=black:borderw=8:x=(w-text_w)/2:y=35,"
        f"drawtext=fontfile=/System/Library/Fonts/Supplemental/Impact.ttf:text='{l2}':fontcolor=white:fontsize=58:bordercolor=black:borderw=8:x=(w-text_w)/2:y=105[outv]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", item["ss"],
        "-i", str(src_video),
        "-t", item["t"],
        "-loop", "1", "-i", str(ARTWORK_PATH),
        "-filter_complex", filter_str,
        "-map", "[outv]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ac", "2",
        "-shortest",
        str(out_file)
    ]

    log.info("Rendering Viral Clip %d: %s -> %s", cid, item["title"], out_file.name)
    try:
        res = subprocess.run(cmd, check=True, capture_output=True, text=True)
        # Extract thumbnail
        subprocess.run(["ffmpeg", "-y", "-ss", "5", "-i", str(out_file), "-vframes", "1", "-q:v", "2", str(thumb_file)], capture_output=True)
        return out_file
    except subprocess.CalledProcessError as e:
        log.error("FFmpeg error on clip %d: %s\nStderr: %s", cid, e, e.stderr[-400:])
        return None

def main():
    print(f"=== Rendering & Publishing {len(VIRAL_CLIPS)} Most Viral GTA 6 YouTube Clips ===")
    results = []

    for item in VIRAL_CLIPS:
        out_path = render_viral_clip(item)
        if not out_path or not out_path.exists():
            log.error("Failed to render clip %d", item["id"])
            continue

        size_mb = out_path.stat().st_size / (1024 * 1024)
        log.info("Clip %d rendered successfully! (%.2f MB)", item["id"], size_mb)

        # Upload with automatic Channel 1 -> Channel 2 failover
        print(f"\n--- Uploading Viral Clip {item['id']}: {item['title']} ---")
        try:
            pub_res = publish_short(
                clip_path=out_path,
                caption=item["caption"],
                title=item["title"],
                tags=item["tags"],
                account="primary"  # Will try primary first, auto-failover to channel2 if uploadLimitExceeded
            )
            item_result = {
                "id": item["id"],
                "title": item["title"],
                "file": str(out_path),
                "size_mb": round(size_mb, 2),
                "upload": pub_res
            }
            results.append(item_result)
            print(f"Upload result for clip {item['id']}: {pub_res}")
        except Exception as e:
            log.error("Upload failed for clip %d: %s", item["id"], e, exc_info=True)
            results.append({
                "id": item["id"],
                "title": item["title"],
                "file": str(out_path),
                "size_mb": round(size_mb, 2),
                "error": str(e)
            })

    summary_file = OUT_DIR / "viral_uploads_summary.json"
    with open(summary_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n=== Completed {len(results)}/{len(VIRAL_CLIPS)} Clips. Summary saved to {summary_file} ===")

if __name__ == "__main__":
    main()
