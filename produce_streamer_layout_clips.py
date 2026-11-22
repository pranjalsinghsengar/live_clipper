#!/usr/bin/env python3
"""Batch producer for 3-tier streamer layout clips matching YouTube Shorts reference GOwKsw3W7cQ."""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

import static_ffmpeg
static_ffmpeg.add_paths()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("streamer_clips")

SECTIONS_DIR = Path("pipeline_data/raw_sections")
OUT_DIR = Path("pipeline_data/streamer_shorts")
OUT_DIR.mkdir(parents=True, exist_ok=True)
ARTWORK_PATH = Path("assets/gta6_bottom_artwork.png")

CLIPS = [
    {
        "id": 1,
        "line1": "DIE TOGETHER LIKE",
        "line2": "BONNIE & CLYDE?!",
        "title": "GTA 6: DIE TOGETHER LIKE BONNIE & CLYDE?! 💀 #shorts #gta6",
        "caption": "Speed cannot believe Jason & Lucia are splitting up! 😭 #ishowspeed #speed #gta6 #funny #gaming",
        "raw": SECTIONS_DIR / "raw_section_01.mp4",
    },
    {
        "id": 2,
        "line1": "SWIM FOR IT!",
        "line2": "MAKE BABIES! 😭",
        "title": "GTA 6: SWIM FOR IT & MAKE BABIES! 😭🏊‍♂️ #shorts #gta6",
        "caption": "Speed yelling at them to escape the cops in the final mission! 😂 #ishowspeed #gta6 #funny #speedstream",
        "raw": SECTIONS_DIR / "raw_section_02.mp4",
    },
    {
        "id": 3,
        "line1": "SPEED IN",
        "line2": "TOTAL SHOCK... 💔",
        "title": "GTA 6: SPEED IN TOTAL SHOCK... 💔😱 #shorts #gta6",
        "caption": "The tragic ending that left Speed completely speechless... 💔 #ishowspeed #gta6 #emotional #gaming",
        "raw": SECTIONS_DIR / "raw_section_03.mp4",
    },
    {
        "id": 4,
        "line1": "PLAYED FOR 52 HOURS",
        "line2": "& BOTH DIED?! 🤬",
        "title": "GTA 6: PLAYED 52 HOURS & BOTH DIED?! 🤬😭 #shorts #gta6",
        "caption": "Speed completely loses his mind after playing for 52 hours straight! 💀 #ishowspeed #speedrage #gta6",
        "raw": SECTIONS_DIR / "raw_section_04.mp4",
    },
    {
        "id": 5,
        "line1": "I'M NOT TROLLING BRO",
        "line2": "I SWEAR TO GOD! 😭",
        "title": "GTA 6: I'M NOT TROLLING BRO! I SWEAR! 😭🔥 #shorts #gta6",
        "caption": "Speed swearing to chat that he can't believe the ending! #ishowspeed #speed #gta6 #rage",
        "raw": SECTIONS_DIR / "raw_section_05.mp4",
    },
    {
        "id": 6,
        "line1": "SPEED BEATS GTA 6",
        "line2": "IN 52 HOURS! 🏆",
        "title": "SPEED BEATS GTA 6 IN 52 HOURS! 🏆🎉 #shorts #gta6",
        "caption": "Speed officially completes the 52 hour story marathon! 👑 #ishowspeed #gta6 #worldrecord",
        "raw": SECTIONS_DIR / "raw_section_06.mp4",
    },
    {
        "id": 7,
        "line1": "PLEASE JUST",
        "line2": "ONE MORE CHANCE! 😭",
        "title": "GTA 6: PLEASE ONE MORE CHANCE! 😭🙏 #shorts #gta6",
        "caption": "Speed begging for his life during the mission! 😂 #ishowspeed #funny #gta6 #fails",
        "raw": SECTIONS_DIR / "raw_section_07.mp4",
    },
    {
        "id": 8,
        "line1": "BRO THIS IS",
        "line2": "ABOUT TO BE OVER! 🚨",
        "title": "GTA 6: BRO THIS IS ABOUT TO BE OVER! 🚨😱 #shorts #gta6",
        "caption": "The final tension is real as Speed tries to survive! ⚡ #ishowspeed #gta6 #intense",
        "raw": SECTIONS_DIR / "raw_section_08.mp4",
    },
    {
        "id": 9,
        "line1": "CHAT CAN Y'ALL",
        "line2": "HEAR ME?! 🎤😡",
        "title": "GTA 6: CHAT CAN Y'ALL HEAR ME?! 🎤😡 #shorts #gta6",
        "caption": "Speed yelling at chat to make sure everyone is listening! 😂 #ishowspeed #chat #funny",
        "raw": SECTIONS_DIR / "raw_section_09.mp4",
    },
    {
        "id": 10,
        "line1": "YOU KEEP",
        "line2": "MESSING ME UP BRO! 💥",
        "title": "GTA 6: YOU KEEP MESSING ME UP BRO! 💥🚗 #shorts #gta6",
        "caption": "Speed losing patience with NPC driving in Vice City! 💀 #ishowspeed #ragemoment #gta6",
        "raw": SECTIONS_DIR / "raw_section_10.mp4",
    },
    {
        "id": 11,
        "line1": "50 HOURS",
        "line2": "WITH CHAT... 🥺❤️",
        "title": "GTA 6: 50 HOURS WITH CHAT... 🥺❤️ #shorts #gta6",
        "caption": "Speed gets emotional reflecting on 50 hours of non-stop streaming. #ishowspeed #wholesome #gta6",
        "raw": SECTIONS_DIR / "raw_section_11.mp4",
    },
    {
        "id": 12,
        "line1": "HAVEN'T SHOWERED",
        "line2": "IN 3 DAYS?! 🚿💀",
        "title": "GTA 6: HAVEN'T SHOWERED IN 3 DAYS?! 🚿💀 #shorts #gta6",
        "caption": "The reality of the 52-hour grind catches up to Speed! 😂 #ishowspeed #gaminggrind #funny",
        "raw": SECTIONS_DIR / "raw_section_12.mp4",
    },
]

def render_streamer_clip(item: dict) -> Path | None:
    raw_video = item["raw"]
    if not raw_video.exists():
        log.warning("Raw video %s missing, skipping", raw_video)
        return None

    cid = item["id"]
    out_file = OUT_DIR / f"speed_short_{cid:02d}.mp4"
    thumb_file = OUT_DIR / f"speed_short_{cid:02d}.jpg"

    l1 = item["line1"].replace("'", "’")
    l2 = item["line2"].replace("'", "’")

    # Filter complex
    filter_str = (
        "[0:v]split=2[v_for_cam][v_for_game];"
        "[v_for_cam]crop=386:208:2:446,split=2[cam_raw1][cam_raw2];"
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
        "-i", str(raw_video),
        "-loop", "1", "-i", str(ARTWORK_PATH),
        "-filter_complex", filter_str,
        "-map", "[outv]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ac", "2",
        "-shortest",
        str(out_file)
    ]

    log.info("Rendering Clip %d: %s -> %s", cid, item["title"], out_file.name)
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        # Extract thumbnail
        subprocess.run(["ffmpeg", "-y", "-ss", "5", "-i", str(out_file), "-vframes", "1", "-q:v", "2", str(thumb_file)], capture_output=True)
        return out_file
    except subprocess.CalledProcessError as e:
        log.error("FFmpeg error on clip %d: %s\nStderr: %s", cid, e, e.stderr[-400:])
        return None

def main():
    print(f"=== Rendering {len(CLIPS)} Clips in 3-Tier Streamer Shorts Layout ===")
    results = []
    for c in CLIPS:
        out = render_streamer_clip(c)
        if out and out.exists():
            size_mb = out.stat().st_size / (1024 * 1024)
            log.info("Clip %d rendered successfully! (%.2f MB)", c["id"], size_mb)
            results.append({
                "id": c["id"],
                "title": c["title"],
                "file": str(out),
                "size_mb": round(size_mb, 2),
                "caption": c["caption"]
            })

    print(f"\n=== Successfully Finished Rendering {len(results)}/{len(CLIPS)} Clips ===")
    with open(OUT_DIR / "shorts_summary.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
