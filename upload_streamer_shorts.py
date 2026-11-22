#!/usr/bin/env python3
"""Upload 3-tier streamer layout clips to YouTube Shorts with Channel 1 -> Channel 2 failover."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from config import CONFIG
from post_youtube import publish_short

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("upload_streamer_shorts")

SHORTS_DIR = Path("pipeline_data/streamer_shorts")

SHORTS_QUEUE = [
    {
        "file": SHORTS_DIR / "speed_short_04.mp4",
        "title": "GTA 6 ENDING: PLAYED 52 HOURS & BOTH DIED?! 🤬😭",
        "caption": "Speed plays GTA 6 for 52 hours straight and this happens! 😭💀 #ishowspeed #gta6 #gta6ending #gaming #shorts",
        "tags": ["GTA 6 Ending", "GTA 6 Final Mission", "GTA 6 Ending Reaction", "IShowSpeed GTA 6 Ending", "Speed GTA 6 Ending", "GTA VI Ending"]
    },
    {
        "file": SHORTS_DIR / "speed_short_03.mp4",
        "title": "GTA 6 ENDING: SPEED IN TOTAL SHOCK... 💔😱",
        "caption": "The tragic GTA 6 ending cutscene that left Speed completely speechless... 💔 #ishowspeed #gta6 #gta6ending #gaming #shorts",
        "tags": ["GTA 6 Ending", "GTA 6 Final Mission", "GTA 6 Sad Ending", "IShowSpeed GTA 6", "Speed GTA 6 Ending", "GTA VI Ending"]
    },
    {
        "file": SHORTS_DIR / "speed_short_01.mp4",
        "title": "GTA 6: DIE TOGETHER LIKE BONNIE & CLYDE?! 💀",
        "caption": "Speed cannot believe Jason & Lucia are splitting up! 😭 #ishowspeed #speed #gta6 #funny #gaming #shorts",
        "tags": ["GTA 6 Final Mission", "GTA 6 Bonnie and Clyde", "IShowSpeed GTA 6", "Speed GTA 6", "GTA VI"]
    },
    {
        "file": SHORTS_DIR / "speed_short_02.mp4",
        "title": "GTA 6: SWIM FOR IT & MAKE BABIES! 😭🏊‍♂️",
        "caption": "Speed yelling at Jason & Lucia to escape the cops in the final mission! 😂 #ishowspeed #gta6 #speedstream #gaming #shorts",
        "tags": ["GTA 6 Ending", "GTA 6 Final Mission", "IShowSpeed Funniest Moments", "Speed GTA 6", "GTA VI"]
    },
    {
        "file": SHORTS_DIR / "speed_short_06.mp4",
        "title": "SPEED BEATS GTA 6 IN 52 HOURS! 🏆🎉",
        "caption": "Speed officially beats GTA 6 after 52 hours 31 minutes! 👑 #ishowspeed #gta6 #worldrecord #speed #shorts",
        "tags": ["Speed Beats GTA 6", "GTA 6 Completed", "IShowSpeed GTA 6 Story", "GTA 6 World Record", "GTA VI"]
    },
    {
        "file": SHORTS_DIR / "speed_short_05.mp4",
        "title": "GTA 6: I'M NOT TROLLING BRO! I SWEAR! 😭🔥",
        "caption": "Speed swears to God he cannot believe the ending! #ishowspeed #speed #gta6 #rage #shorts",
        "tags": ["GTA 6 Ending Reaction", "IShowSpeed GTA 6 Rage", "Speed GTA 6", "GTA VI Ending"]
    },
    {
        "file": SHORTS_DIR / "speed_short_07.mp4",
        "title": "GTA 6: PLEASE ONE MORE CHANCE! 😭🙏",
        "caption": "Speed begging for one more chance during the mission! 😂 #ishowspeed #funny #gta6 #fails #shorts",
        "tags": ["IShowSpeed Funny Moments", "Speed GTA 6 Fails", "GTA 6 Highlights", "GTA VI"]
    },
    {
        "file": SHORTS_DIR / "speed_short_08.mp4",
        "title": "GTA 6: BRO THIS IS ABOUT TO BE OVER! 🚨😱",
        "caption": "High tension as Speed tries to survive the final stretch! ⚡ #ishowspeed #gta6 #intense #shorts",
        "tags": ["GTA 6 Mission", "IShowSpeed GTA 6", "Speed Intense Moments", "GTA VI"]
    },
    {
        "file": SHORTS_DIR / "speed_short_09.mp4",
        "title": "GTA 6: CHAT CAN Y'ALL HEAR ME?! 🎤😡",
        "caption": "Speed interrogating chat to make sure everyone is listening! 😂 #ishowspeed #chat #speedclips #funny #shorts",
        "tags": ["IShowSpeed Chat", "Speed Funny Moments", "GTA 6 Speed", "GTA VI"]
    },
    {
        "file": SHORTS_DIR / "speed_short_10.mp4",
        "title": "GTA 6: YOU KEEP MESSING ME UP BRO! 💥🚗",
        "caption": "Speed losing patience with NPC driving in Vice City! 💀 #ishowspeed #ragemoment #gta6 #shorts",
        "tags": ["GTA 6 NPC Fails", "IShowSpeed Rage", "Speed Car Crash", "GTA VI"]
    },
    {
        "file": SHORTS_DIR / "speed_short_11.mp4",
        "title": "GTA 6: 50 HOURS WITH CHAT... 🥺❤️",
        "caption": "Speed gets emotional reflecting on 50 hours of non-stop streaming. #ishowspeed #wholesome #gta6 #shorts",
        "tags": ["IShowSpeed Wholesome", "Speed 50 Hours", "GTA 6 Marathon", "GTA VI"]
    },
    {
        "file": SHORTS_DIR / "speed_short_12.mp4",
        "title": "GTA 6: HAVEN'T SHOWERED IN 3 DAYS?! 🚿💀",
        "caption": "The reality of the 52-hour grind catches up to Speed! 😂 #ishowspeed #gaminggrind #funny #shorts",
        "tags": ["IShowSpeed Funny", "Speed Stream Confessions", "GTA 6 Grind", "GTA VI"]
    },
]

def main():
    print("=== Uploading Streamer Shorts: Channel 1 -> Failover to Channel 2 ===")
    results = []

    for idx, item in enumerate(SHORTS_QUEUE, 1):
        clip_path = item["file"]
        if not clip_path.exists():
            log.warning("Clip %s does not exist, skipping.", clip_path.name)
            continue

        print(f"\n[{idx}/{len(SHORTS_QUEUE)}] Uploading: {item['title']} ({clip_path.name})...")
        # preferred_account="primary" ensures Channel 1 is used first until its quota/limit is done, then channel 2
        res = publish_short(
            clip_path=clip_path,
            caption=item["caption"],
            title=item["title"],
            tags=item["tags"],
            account="primary"
        )
        print("Result:", res)
        results.append({
            "title": item["title"],
            "clip": clip_path.name,
            "result": res
        })

        yt_res = res.get("youtube", {})
        if yt_res.get("error") == "uploadLimitExceeded":
            print("\nAll connected accounts have reached their daily limit.")
            break

    out_file = SHORTS_DIR / "upload_streamer_results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nUpload run finished! Summary saved to {out_file}")

if __name__ == "__main__":
    main()
