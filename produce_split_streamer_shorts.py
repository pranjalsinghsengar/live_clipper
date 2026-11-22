"""Produce pure split-screen comparison videos with streamer-enhanced thumbnails (NO MEMES)."""
from __future__ import annotations

import json
from pathlib import Path
from compare_edit import render_comparison_clip
from thumbnail_designer import create_streamer_thumbnail
from post_youtube import extract_thumbnail

CLIPS_OUT_DIR = Path.home() / "clips_pipeline_data" / "clips"
CLIPS_OUT_DIR.mkdir(parents=True, exist_ok=True)

# Transcripts
with open("/Users/sengar/clips_pipeline_data/live_transcripts/stream_13.json") as f:
    data13 = json.load(f)
words13 = data13.get("words", [])

with open("/Users/sengar/clips_pipeline_data/live_transcripts/stream_15.json") as f:
    data15 = json.load(f)
words15 = data15.get("words", [])

gta6_stream13 = Path.home() / "clips_pipeline_data" / "streams" / "stream_13.mp4"
gta6_stream15 = Path.home() / "clips_pipeline_data" / "streams" / "stream_15.mp4"

VIDEOS = [
    {
        "id": "split_car_drift",
        "title": "GTA 5 vs GTA 6: Supercar Speed & Drift Physics! 🏎️💨 #shorts #gta6",
        "stream": gta6_stream13,
        "words": words13,
        "start": 2380.0,
        "end": 2415.0,
        "gta5": Path("assets/gta5/car_physics.mp4"),
        "streamer": "CarryMinati",
        "headline": "GTA 5 VS GTA 6",
        "subheadline": "CAR SPEED & DRIFT! 🏎️",
    },
    {
        "id": "split_police_chase",
        "title": "GTA 5 vs GTA 6: 5-Star Police Chase Comparison! 🚨🚓 #shorts #gta6",
        "stream": gta6_stream15,
        "words": words15,
        "start": 2180.0,
        "end": 2215.0,
        "gta5": Path("assets/gta5/police_chase.mp4"),
        "streamer": "CarryMinati",
        "headline": "GTA 5 VS GTA 6",
        "subheadline": "5-STAR POLICE CHASE! 🚨",
    },
    {
        "id": "split_water_physics",
        "title": "GTA 5 vs GTA 6: Water & Swimming Physics Test! 🌊🤯 #shorts #gta6",
        "stream": gta6_stream13,
        "words": words13,
        "start": 6640.0,
        "end": 6675.0,
        "gta5": Path("assets/gta5/water_physics.mp4"),
        "streamer": "CarryMinati",
        "headline": "GTA 5 VS GTA 6",
        "subheadline": "WATER & WAVE PHYSICS! 🌊",
    },
    {
        "id": "split_nextgen_graphics",
        "title": "GTA 5 vs GTA 6: Next-Gen Graphics Comparison! ⚡🤯 #shorts #gta6",
        "stream": gta6_stream15,
        "words": words15,
        "start": 3060.0,
        "end": 3095.0,
        "gta5": Path("assets/gta5/graphics.mp4"),
        "streamer": "CarryMinati",
        "headline": "GTA 5 VS GTA 6",
        "subheadline": "INSANE NEXT-GEN GRAPHICS! ⚡",
    },
]

def main():
    print(f"Producing {len(VIDEOS)} pure split-screen comparison videos with streamer thumbnails...")
    for idx, item in enumerate(VIDEOS, 1):
        out_clip = CLIPS_OUT_DIR / f"{item['id']}.mp4"
        out_thumb = CLIPS_OUT_DIR / f"{item['id']}_thumb.jpg"
        print(f"\n[{idx}/{len(VIDEOS)}] Rendering {item['id']} ({item['start']}s - {item['end']}s)...")

        # 1. Render pure split-screen video (no memes)
        render_comparison_clip(
            gta6_source=item["stream"],
            start=item["start"],
            end=item["end"],
            out_path=out_clip,
            words=item["words"],
            streamer_name=item["streamer"],
            gta5_source=item["gta5"],
            custom_title=item["title"],
        )

        # 2. Extract frame and generate streamer-enhanced thumbnail
        extract_thumbnail(out_clip, out_thumb)
        create_streamer_thumbnail(
            base_frame_path=out_thumb,
            out_thumb_path=out_thumb,
            streamer_name=item["streamer"],
            headline=item["headline"],
            subheadline=item["subheadline"],
        )
        print(f"DONE: Clip={out_clip.name} ({out_clip.stat().st_size / 1024 / 1024:.1f}MB), Thumb={out_thumb.name}")

if __name__ == "__main__":
    main()
