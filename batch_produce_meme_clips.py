"""Batch producer for meme-infused comparison videos and highlight clips."""
from __future__ import annotations

import json
from pathlib import Path
from meme_edit import render_comparison_with_meme, render_highlight_with_meme

CLIPS_OUT_DIR = Path.home() / "clips_pipeline_data" / "clips"
CLIPS_OUT_DIR.mkdir(parents=True, exist_ok=True)

# Load transcripts
with open("/Users/sengar/clips_pipeline_data/live_transcripts/stream_13.json") as f:
    data13 = json.load(f)
words13 = data13.get("words", [])

with open("/Users/sengar/clips_pipeline_data/live_transcripts/stream_15.json") as f:
    data15 = json.load(f)
words15 = data15.get("words", [])

gta6_stream13 = Path.home() / "clips_pipeline_data" / "streams" / "stream_13.mp4"
gta6_stream15 = Path.home() / "clips_pipeline_data" / "streams" / "stream_15.mp4"

TASKS = [
    # 1. Police Chase Comparison
    {
        "type": "compare",
        "stream": gta6_stream15,
        "words": words15,
        "start": 2185.0,
        "end": 2215.0,
        "meme": "the_rock",
        "out": CLIPS_OUT_DIR / "compare_police_meme_the_rock.mp4",
        "title": "GTA 5 vs GTA 6: 5-Star Police Chase! 🚨🚓",
        "cat": "police_chase",
        "gta5": Path("assets/gta5/police_chase.mp4"),
    },
    # 2. Graphics Comparison
    {
        "type": "compare",
        "stream": gta6_stream15,
        "words": words15,
        "start": 3065.0,
        "end": 3095.0,
        "meme": "shocked_cat",
        "out": CLIPS_OUT_DIR / "compare_graphics_meme_shocked_cat.mp4",
        "title": "GTA 5 vs GTA 6: Insane Next-Gen Graphics! 🤯⚡",
        "cat": "graphics",
        "gta5": Path("assets/gta5/graphics.mp4"),
    },
    # 3. Bike Crash / Ragdoll Physics Comparison
    {
        "type": "compare",
        "stream": gta6_stream13,
        "words": words13,
        "start": 4660.0,
        "end": 4690.0,
        "meme": "walter_white",
        "out": CLIPS_OUT_DIR / "compare_bike_ragdoll_meme_walter.mp4",
        "title": "GTA 5 vs GTA 6: Bike Crash & Ragdoll Physics! 😂💀",
        "cat": "car_physics",
        "gta5": Path("assets/gta5/car_physics.mp4"),
    },
    # 4. Vice City Nightlife / Neon Details
    {
        "type": "compare",
        "stream": gta6_stream13,
        "words": words13,
        "start": 5325.0,
        "end": 5355.0,
        "meme": "emotional_damage",
        "out": CLIPS_OUT_DIR / "compare_nightlife_meme_damage.mp4",
        "title": "GTA 5 vs GTA 6: Vice City Nightlife Details! 🌴✨",
        "cat": "graphics",
        "gta5": Path("assets/gta5/graphics.mp4"),
    },
    # 5. Standalone Highlight 1
    {
        "type": "highlight",
        "stream": gta6_stream13,
        "words": words13,
        "start": 985.0,
        "end": 1015.0,
        "meme": "the_rock",
        "out": CLIPS_OUT_DIR / "highlight_carry_mission_meme.mp4",
        "title": "CARRYMINATI VICE CITY MISSION! 😂",
    },
    # 6. Standalone Highlight 2
    {
        "type": "highlight",
        "stream": gta6_stream15,
        "words": words15,
        "start": 1595.0,
        "end": 1625.0,
        "meme": "emotional_damage",
        "out": CLIPS_OUT_DIR / "highlight_carry_police_meme.mp4",
        "title": "CARRYMINATI 5-STAR COP ESCAPE! 🚨💀",
    },
    # 7. Standalone Highlight 3
    {
        "type": "highlight",
        "stream": gta6_stream15,
        "words": words15,
        "start": 3925.0,
        "end": 3955.0,
        "meme": "shocked_cat",
        "out": CLIPS_OUT_DIR / "highlight_carry_secret_building_meme.mp4",
        "title": "CARRYMINATI SECRET BUILDING IN GTA 6! 😱",
    },
]

def main():
    print(f"Starting batch production of {len(TASKS)} meme-infused videos...")
    completed = []
    for idx, t in enumerate(TASKS, 1):
        if t["out"].exists() and t["out"].stat().st_size > 1000:
            print(f"Skipping existing: {t['out'].name}")
            completed.append((t, t["out"], 32.0))
            continue
        print(f"\n--- [{idx}/{len(TASKS)}] Producing: {t['title']} ({t['meme']}) ---")
        try:
            if t["type"] == "compare":
                p, dur = render_comparison_with_meme(
                    gta6_source=t["stream"],
                    start=t["start"],
                    end=t["end"],
                    out_path=t["out"],
                    meme_name=t["meme"],
                    words=t["words"],
                    streamer_name="CarryMinati",
                    gta5_source=t.get("gta5"),
                    custom_title=t["title"],
                )
            else:
                p, dur = render_highlight_with_meme(
                    source_video=t["stream"],
                    start=t["start"],
                    end=t["end"],
                    out_path=t["out"],
                    meme_name=t["meme"],
                    words=t["words"],
                    streamer_name="CarryMinati",
                    title_text=t["title"],
                )
            print(f"SUCCESS: {p.name} (duration={dur:.1f}s, size={p.stat().st_size / 1024 / 1024:.1f}MB)")
            completed.append((t, p, dur))
        except Exception as e:
            print(f"ERROR on {t['title']}: {e}")

    print(f"\nBatch complete! Produced {len(completed)} / {len(TASKS)} videos.")

if __name__ == "__main__":
    main()
