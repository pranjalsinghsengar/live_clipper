#!/usr/bin/env python3
"""Batch downloader and producer for IShowSpeed GTA 6 clips."""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

import static_ffmpeg
static_ffmpeg.add_paths()

from config import CONFIG
from captions import build_ass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("cut_speed")

YOUTUBE_URL = "https://www.youtube.com/watch?v=OIeLbmyraRQ"
CLIPS_DIR = Path("pipeline_data") / "clips"
SECTIONS_DIR = Path("pipeline_data") / "raw_sections"

CLIPS_DIR.mkdir(parents=True, exist_ok=True)
SECTIONS_DIR.mkdir(parents=True, exist_ok=True)

# 12 Curated viral clips
CLIPS_METADATA = [
    {
        "id": 1,
        "start": 18660.0,
        "end": 18705.0,
        "title": "DIE TOGETHER LIKE BONNIE & CLYDE?! 💀",
        "hook_banner": "DIE TOGETHER LIKE BONNIE & CLYDE?! 💀",
        "caption": "Speed cannot believe Jason and Lucia are splitting up! 😭 #ishowspeed #speed #gta6 #viral #funny",
        "reason": "Peak viral moment at 05:11 where Speed screams at the characters splitting up.",
    },
    {
        "id": 2,
        "start": 18710.0,
        "end": 18760.0,
        "title": "SWIM FOR IT! MAKE BABIES! 😭",
        "hook_banner": "SWIM FOR IT! MAKE BABIES! 😭",
        "caption": "Speed refuses to let them surrender! 'We gotta swim for it bro!' 🏊‍♂️💨 #ishowspeed #speedstream #gta6 #fyp",
        "reason": "Hilarious desperate screaming from Speed at 05:12.",
    },
    {
        "id": 3,
        "start": 18765.0,
        "end": 18810.0,
        "title": "SPEED IN TOTAL SHOCK... 💔😱",
        "hook_banner": "SPEED IN TOTAL SHOCK... 💔😱",
        "caption": "The moment the tragic climax happens and Speed is left completely speechless... #ishowspeed #speed #gta6 #emotional",
        "reason": "The exact climax ending at 05:13 leading into utter shock.",
    },
    {
        "id": 4,
        "start": 18855.0,
        "end": 18910.0,
        "title": "PLAYED FOR 52 HOURS & BOTH DIED?! 🤬😭",
        "hook_banner": "PLAYED FOR 52 HOURS & BOTH DIED?! 🤬",
        "caption": "Speed completely breaks down and loses his mind after 52 hours of grinding! 💀 #ishowspeed #speedrage #gta6 #gaming",
        "reason": "The most iconic rage breakdown of the whole stream (05:14:15 - 05:15:10).",
    },
    {
        "id": 5,
        "start": 18975.0,
        "end": 19025.0,
        "title": "I'M NOT TROLLING BRO! I SWEAR! 😭🔥",
        "hook_banner": "I'M NOT TROLLING BRO! 😭",
        "caption": "Speed swears to God he cannot believe the ending after 52 hours! #ishowspeed #speed #gta6 #rage",
        "reason": "Post-ending raw venting to chat.",
    },
    {
        "id": 6,
        "start": 21100.0,
        "end": 21155.0,
        "title": "SPEED BEATS GTA 6 IN 52 HOURS! 🏆🎉",
        "hook_banner": "BEAT GTA 6 IN 52 HOURS! 🏆",
        "caption": "Speed officially stops the stream timer at 52h 31m after completing the game! 👑 #ishowspeed #gta6 #worldrecord #speed",
        "reason": "The monumental 52-hour completion moment.",
    },
    {
        "id": 7,
        "start": 6180.0,
        "end": 6230.0,
        "title": "PLEASE ONE MORE CHANCE! 😭🙏",
        "hook_banner": "PLEASE ONE MORE CHANCE! 😭🙏",
        "caption": "Speed in pure panic begging for one more chance during the mission! 😂 #ishowspeed #funny #gta6 #fails",
        "reason": "Classic Speed desperation and panic.",
    },
    {
        "id": 8,
        "start": 6285.0,
        "end": 6335.0,
        "title": "THIS IS REALLY ABOUT TO BE OVER! 🚨😱",
        "hook_banner": "THIS IS ABOUT TO BE OVER! 🚨",
        "caption": "The tension is at maximum level as Speed tries to survive the final stretch! ⚡ #ishowspeed #gta6 #intense #gaming",
        "reason": "High-intensity screams and mission suspense.",
    },
    {
        "id": 9,
        "start": 7455.0,
        "end": 7500.0,
        "title": "CHAT CAN Y'ALL HEAR ME?! 🎤😡",
        "hook_banner": "CHAT CAN Y'ALL HEAR ME?! 🎤",
        "caption": "Speed interrogating his chat to make sure everyone is listening to him! 😂 #ishowspeed #chat #speedclips #funny",
        "reason": "Classic streamer-chat interactive comedy.",
    },
    {
        "id": 10,
        "start": 12165.0,
        "end": 12215.0,
        "title": "YOU KEEP MESSING ME UP BRO! 💥🚗",
        "hook_banner": "YOU KEEP MESSING ME UP BRO! 💥",
        "caption": "Speed losing patience with NPC timing during the mission! 💀 #ishowspeed #ragemoment #gta6 #streamer",
        "reason": "Hilarious NPC frustration crash.",
    },
    {
        "id": 11,
        "start": 12630.0,
        "end": 12680.0,
        "title": "50 HOURS WITH CHAT... 🥺❤️",
        "hook_banner": "50 HOURS WITH CHAT... 🥺❤️",
        "caption": "Speed gets emotional realizing he has been streaming for 50 straight hours with chat. #ishowspeed #wholesome #gta6 #speed",
        "reason": "Wholesome reflection on the 50h stream marathon.",
    },
    {
        "id": 12,
        "start": 20070.0,
        "end": 20115.0,
        "title": "HAVEN'T SHOWERED IN 3 DAYS?! 🚿💀",
        "hook_banner": "NO SHOWER IN 3 DAYS?! 💀",
        "caption": "The reality of the 52-hour non-stop gaming marathon catches up to Speed! 😂 #ishowspeed #gaminggrind #gta6 #funny",
        "reason": "Hilarious post-game exhaustion confession.",
    },
]

def load_words() -> list[dict[str, Any]]:
    words_file = Path("speed_words.json")
    if not words_file.exists():
        log.error("speed_words.json not found!")
        return []
    with open(words_file) as f:
        return json.load(f)

def download_section(start: float, end: float, out_file: Path) -> bool:
    if out_file.exists() and out_file.stat().st_size > 1_000_000:
        log.info("Raw section %s already downloaded (%d bytes)", out_file.name, out_file.stat().st_size)
        return True

    # Padding 1s on each side to ensure smooth keyframes
    pad_start = max(0.0, start - 1.0)
    pad_end = end + 1.0
    time_range = f"*{int(pad_start)}-{int(pad_end)}"

    cmd = [
        "yt-dlp",
        "--download-sections", time_range,
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]",
        "--force-keyframes-at-cuts",
        "-o", str(out_file),
        YOUTUBE_URL,
    ]
    log.info("Downloading section %s: %s", out_file.name, time_range)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if res.returncode != 0:
            log.error("yt-dlp download failed: %s", res.stderr[-400:])
            return False
        return True
    except Exception as e:
        log.exception("Download exception for %s: %s", out_file.name, e)
        return False

def render_clip(raw_video: Path, clip_spec: dict[str, Any], all_words: list[dict[str, Any]]) -> Path | None:
    clip_id = clip_spec["id"]
    start = clip_spec["start"]
    end = clip_spec["end"]
    duration = end - start

    out_clip = CLIPS_DIR / f"speed_gta6_clip_{clip_id:02d}.mp4"
    ass_path = CLIPS_DIR / f"speed_gta6_clip_{clip_id:02d}.ass"

    # Filter words relative to raw_video (pad_start was start - 1.0)
    pad_start = max(0.0, start - 1.0)
    rel_start = start - pad_start
    rel_end = rel_start + duration

    clip_words = []
    for w in all_words:
        w_start = w["start"]
        if start <= w_start <= end:
            clip_words.append({
                "start": round(w_start - start, 2),
                "end": round(w_start - start + 0.35, 2),
                "word": w["word"]
            })

    hook_banner = clip_spec.get("hook_banner") or clip_spec.get("title") or ""
    build_ass(clip_words, 0.0, duration, ass_path, hook_banner=hook_banner)

    ass_filter_path = str(ass_path).replace("\\", "/").replace(":", r"\:")
    video_filter = f"crop=ih*9/16:ih,scale=720:1280:flags=lanczos,setsar=1,ass='{ass_filter_path}'"

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{rel_start:.3f}",
        "-to", f"{rel_end:.3f}",
        "-i", str(raw_video),
        "-vf", video_filter,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ac", "2",
        "-movflags", "+faststart",
        str(out_clip)
    ]
    log.info("Rendering clip %d (%s) -> %s", clip_id, clip_spec["title"], out_clip.name)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return out_clip
    except subprocess.CalledProcessError as e:
        log.error("ffmpeg failed for clip %d: %s\nStderr: %s", clip_id, e, e.stderr[-400:])
        return None

def main():
    words = load_words()
    results = []

    print(f"=== Starting Production of {len(CLIPS_METADATA)} IShowSpeed Clips ===")
    for spec in CLIPS_METADATA:
        cid = spec["id"]
        raw_path = SECTIONS_DIR / f"raw_section_{cid:02d}.mp4"

        # Check special case for clip 1 (test_section already downloaded)
        if cid == 1 and Path("test_section.mp4").exists():
            raw_path = Path("test_section.mp4")

        # 1. Download section if needed
        success = download_section(spec["start"], spec["end"], raw_path)
        if not success:
            log.warning("Skipping clip %d due to download failure", cid)
            continue

        # 2. Render 9:16 vertical clip with karaoke captions & hook banner
        out_clip = render_clip(raw_path, spec, words)
        if out_clip and out_clip.exists():
            size_mb = out_clip.stat().st_size / (1024 * 1024)
            log.info("Clip %d rendered successfully! Size: %.2f MB", cid, size_mb)
            results.append({
                "id": cid,
                "title": spec["title"],
                "file": str(out_clip),
                "size_mb": round(size_mb, 2),
                "duration": round(spec["end"] - spec["start"], 1),
                "caption": spec["caption"]
            })

    print(f"\n=== Successfully Produced {len(results)}/{len(CLIPS_METADATA)} Clips ===")
    summary_path = CLIPS_DIR / "clips_summary.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Summary saved to: {summary_path}")

if __name__ == "__main__":
    main()
