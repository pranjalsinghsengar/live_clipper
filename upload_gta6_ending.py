#!/usr/bin/env python3
"""Upload GTA 6 Ending viral clips to YouTube Shorts."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from config import CONFIG
from post_youtube import publish_short

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("upload_ending")

ENDING_CLIPS = [
    {
        "clip_file": Path("pipeline_data/clips/speed_gta6_clip_04.mp4"),
        "title": "GTA 6 ENDING: PLAYED 52 HOURS & BOTH DIED?! 🤬😭",
        "caption": "Speed plays GTA 6 for 52 hours straight and this is how it ends! 😭💀 #ishowspeed #gta6 #gta6ending #viral #gaming",
        "tags": [
            "GTA 6 Ending",
            "GTA 6 Final Mission",
            "GTA 6 Ending Reaction",
            "IShowSpeed GTA 6 Ending",
            "Speed GTA 6 Ending",
            "GTA 6 Ending Scene",
            "GTA 6 Secret Ending",
            "GTA 6 Jason and Lucia Death",
            "GTA 6 Ending Explained",
            "Grand Theft Auto 6 Ending",
            "GTA VI Ending",
            "Speed Rage GTA 6"
        ]
    },
    {
        "clip_file": Path("pipeline_data/clips/speed_gta6_clip_03.mp4"),
        "title": "GTA 6 ENDING: SPEED IN TOTAL SHOCK... 💔😱",
        "caption": "The tragic GTA 6 ending that left Speed completely speechless... 💔 #ishowspeed #gta6 #gta6ending #gaming #emotional",
        "tags": [
            "GTA 6 Ending",
            "GTA 6 Final Mission",
            "GTA 6 Ending Cutscene",
            "IShowSpeed GTA 6",
            "Speed GTA 6 Ending",
            "GTA VI Ending Cutscene",
            "GTA 6 Story Ending",
            "Grand Theft Auto 6 Ending",
            "GTA 6 Sad Ending"
        ]
    },
    {
        "clip_file": Path("pipeline_data/clips/speed_gta6_clip_01.mp4"),
        "title": "GTA 6 ENDING: DIE LIKE BONNIE & CLYDE?! 💀",
        "caption": "Speed cannot believe Jason and Lucia are splitting up at the end! 😭 #ishowspeed #gta6 #gta6ending #funny #viral",
        "tags": [
            "GTA 6 Ending",
            "GTA 6 Final Mission",
            "GTA 6 Bonnie and Clyde",
            "IShowSpeed GTA 6 Ending",
            "Speed GTA 6",
            "GTA VI Ending",
            "Grand Theft Auto 6 Final Mission"
        ]
    },
    {
        "clip_file": Path("pipeline_data/clips/speed_gta6_clip_02.mp4"),
        "title": "GTA 6 ENDING: SWIM FOR IT & MAKE BABIES! 😭🏊‍♂️",
        "caption": "Speed screaming at Jason & Lucia to escape the cops in the final mission! 😂 #ishowspeed #gta6 #gta6ending #speedstream #gaming",
        "tags": [
            "GTA 6 Ending",
            "GTA 6 Final Mission",
            "Speed GTA 6 Final Mission",
            "IShowSpeed Funniest Moments",
            "GTA 6 Ending Escape",
            "GTA VI Ending"
        ]
    }
]

def main():
    print("=== Uploading GTA 6 Ending Clips to YouTube Shorts ===")
    results = []

    for item in ENDING_CLIPS:
        clip_path = item["clip_file"]
        if not clip_path.exists():
            log.warning("Clip %s does not exist, skipping.", clip_path)
            continue

        print(f"\nUploading: {item['title']} ({clip_path.name})...")
        # Put GTA 6 ending tags first
        ending_tags = [
            "GTA 6 Ending",
            "GTA 6 Ending Reaction",
            "GTA 6 Final Mission",
            "IShowSpeed GTA 6 Ending",
            "Speed GTA 6 Ending",
            "GTA VI Ending",
            "Grand Theft Auto 6 Ending",
            "GTA 6 Ending Scene"
        ]
        res = publish_short(
            clip_path=clip_path,
            caption=item["caption"],
            title=item["title"],
            tags=ending_tags,
        )
        print("Result:", res)
        results.append({"title": item["title"], "clip": str(clip_path), "result": res})

        # If quota limit reached, break
        yt_res = res.get("youtube", {})
        if yt_res.get("error") == "uploadLimitExceeded":
            print("\nDaily upload limit reached on YouTube accounts.")
            break

    print("\n=== Finished Upload Run ===")
    out_file = Path("pipeline_data/clips/upload_results.json")
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {out_file}")

if __name__ == "__main__":
    main()
