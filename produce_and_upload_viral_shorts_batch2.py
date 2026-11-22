#!/usr/bin/env python3
"""Batch 2 producer & uploader for YouTube's most viral GTA 6 clips.
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
log = logging.getLogger("viral_shorts_batch2")

OUT_DIR = Path("pipeline_data/viral_external_shorts")
OUT_DIR.mkdir(parents=True, exist_ok=True)
ARTWORK_PATH = Path("assets/gta6_bottom_artwork.png")

VIRAL_CLIPS = [
    {
        "id": 6,
        "src": Path("alligator.webm"),
        "ss": "00:00:10",
        "t": "50",
        "line1": "GETS BITTEN BY AN",
        "line2": "ALLIGATOR IN GTA 6! 🐊💀",
        "title": "GTA 6: GETS BITTEN BY AN ALLIGATOR! 😭🐊 #shorts #gta6",
        "caption": "Speed wanders into the Vice City swamp and gets attacked by an alligator! 😂 #ishowspeed #gta6 #funny #gaming #shorts",
        "tags": ["GTA 6", "GTA VI", "IShowSpeed", "IShowSpeed GTA 6", "GTA 6 Alligator", "GTA 6 Swamp", "GTA 6 Funny", "GTA 6 Shorts"],
    },
    {
        "id": 7,
        "src": Path("iguana.webm"),
        "ss": "00:00:00",
        "t": "49",
        "line1": "THROWS ROADKILL IGUANA",
        "line2": "AT AN NPC IN GTA 6! 🦎💀",
        "title": "GTA 6: THROWS ROADKILL IGUANA AT AN NPC! 🦎💀 #shorts #gta6",
        "caption": "Speed cannot believe the wildlife physics in GTA 6! 😭 #ishowspeed #gta6 #funny #fails #shorts",
        "tags": ["GTA 6", "GTA VI", "IShowSpeed", "IShowSpeed GTA 6", "GTA 6 Iguana", "GTA 6 Wildlife", "GTA 6 Funny", "GTA 6 Shorts"],
    },
    {
        "id": 8,
        "src": Path("karen.webm"),
        "ss": "00:00:05",
        "t": "50",
        "line1": "RUNS INTO A CRAZY",
        "line2": "KAREN IN GTA 6! 😭👵",
        "title": "GTA 6: RUNS INTO A CRAZY KAREN NPC! 😭👵 #shorts #gta6",
        "caption": "Speed discovers GTA 6 has realistic Karen NPCs in Vice City! 💀 #ishowspeed #gta6 #funny #ragemoment #shorts",
        "tags": ["GTA 6", "GTA VI", "IShowSpeed", "IShowSpeed GTA 6", "GTA 6 Karen", "GTA 6 NPC Interaction", "GTA 6 Funny", "GTA 6 Shorts"],
    },
    {
        "id": 9,
        "src": Path("deleted_save.webm"),
        "ss": "00:00:10",
        "t": "52",
        "line1": "DELETES 48-HR SAVE FILE",
        "line2": "AFTER 2 DAYS OF NO SLEEP! 😱❌",
        "title": "GTA 6: DELETES 48-HOUR SAVE FILE ON ACCIDENT! 😱💔 #shorts #gta6",
        "caption": "Speed accidentally overwrites his entire 48-hour marathon save file! 😭 #ishowspeed #gta6 #tragic #fail #shorts",
        "tags": ["GTA 6", "GTA VI", "IShowSpeed", "IShowSpeed GTA 6", "IShowSpeed Deleted Save", "GTA 6 48 Hours", "GTA 6 Rage", "GTA 6 Shorts"],
    },
    {
        "id": 10,
        "src": Path("crying_ending.webm"),
        "ss": "00:00:05",
        "t": "50",
        "line1": "SPEED IN TEARS AT",
        "line2": "THE GTA 6 ENDING... 💔😭",
        "title": "GTA 6: SPEED IN TEARS AT THE TRAGIC ENDING... 💔😭 #shorts #gta6",
        "caption": "Speed cannot hold back tears after 52 hours of playing GTA 6... 🥺 #ishowspeed #gta6 #emotional #gaming #shorts",
        "tags": ["GTA 6", "GTA VI", "IShowSpeed", "IShowSpeed GTA 6", "GTA 6 Ending", "IShowSpeed Crying", "GTA 6 Ending Reaction", "GTA 6 Shorts"],
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
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        # Extract thumbnail
        subprocess.run(["ffmpeg", "-y", "-ss", "5", "-i", str(out_file), "-vframes", "1", "-q:v", "2", str(thumb_file)], capture_output=True)
        return out_file
    except subprocess.CalledProcessError as e:
        log.error("FFmpeg error on clip %d: %s\nStderr: %s", cid, e, e.stderr[-400:])
        return None

def main():
    print(f"=== Rendering & Publishing Batch 2 ({len(VIRAL_CLIPS)} Clips) ===")
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
                account="primary"  # Will try primary first, auto-failover to channel2 if upload limit/quota reached
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

    summary_file = OUT_DIR / "viral_uploads_batch2_summary.json"
    with open(summary_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n=== Completed Batch 2 ({len(results)}/{len(VIRAL_CLIPS)} Clips). Summary saved to {summary_file} ===")

if __name__ == "__main__":
    main()
