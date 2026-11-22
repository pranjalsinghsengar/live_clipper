"""Produce 3 viral split comparison shorts and upload directly to channel2."""
from __future__ import annotations

import json
from pathlib import Path
from creator_vs_creator import render_dual_creator_clip, create_dual_streamer_thumbnail
from thumbnail_designer import create_streamer_thumbnail
from compare_edit import render_comparison_clip
from post_youtube import extract_thumbnail, publish_short

CLIPS_OUT_DIR = Path.home() / "clips_pipeline_data" / "clips"
CLIPS_OUT_DIR.mkdir(parents=True, exist_ok=True)

# Sources
speed_src = Path("/Users/sengar/clips_pipeline_data/streams/stream_184.mp4")
carry_src13 = Path("/Users/sengar/clips_pipeline_data/streams/stream_13.mp4")
carry_src15 = Path("/Users/sengar/clips_pipeline_data/streams/stream_15.mp4")
techno_src = Path("/Users/sengar/clips_pipeline_data/downloads/techno_gta6.mp4")
gta5_graphics = Path("assets/gta5/graphics.mp4")

VIDEOS = [
    # 1. Speed vs CarryMinati
    {
        "id": "speed_vs_carry_driving",
        "title": "IShowSpeed vs CarryMinati: GTA 6 Driving Showdown! 🏎️💥 #shorts #gta6",
        "type": "dual",
        "top_src": speed_src,
        "bottom_src": carry_src13,
        "top_start": 1210.0,
        "bottom_start": 2380.0,
        "duration": 32.0,
        "hook_banner": "SPEED VS CARRY: GTA 6 DRIVING! 🏎️",
        "top_label": "IShowSpeed (34M)",
        "bottom_label": "CARRYMINATI (44M)",
        "headline": "SPEED VS CARRYMINATI",
        "subheadline": "WHO DRIVES WORSE IN GTA 6?! 😂",
        "streamer_left": "ishowspeed",
        "streamer_right": "carryminati",
    },
    # 2. Techno Gamerz vs GTA 5 Graphics
    {
        "id": "techno_vs_gta5_graphics_test",
        "title": "Techno Gamerz: GTA 5 vs GTA 6 Graphics Reaction! ⚡🤯 #shorts #gta6",
        "type": "single",
        "top_src": gta5_graphics,
        "bottom_src": techno_src,
        "top_start": 0.0,
        "bottom_start": 33.0,
        "duration": 32.0,
        "hook_banner": "GTA 5 VS GTA 6: GRAPHICS TEST! ⚡",
        "top_label": "GTA V (2013)",
        "bottom_label": "GTA VI (2025) • TECHNO",
        "headline": "GTA 5 VS GTA 6",
        "subheadline": "TECHNO GRAPHICS TEST! 🔥",
        "streamer": "Techno Gamerz",
    },
    # 3. Techno vs Carry: 5-Star Police Chase
    {
        "id": "techno_vs_carry_police_showdown",
        "title": "Techno Gamerz vs CarryMinati: 5-Star Police Chase! 🚨🚓 #shorts #gta6",
        "type": "dual",
        "top_src": techno_src,
        "bottom_src": carry_src15,
        "top_start": 150.0,
        "bottom_start": 2180.0,
        "duration": 32.0,
        "hook_banner": "5-STAR POLICE CHASE SHOWDOWN! 🚨",
        "top_label": "TECHNO GAMERZ (39M)",
        "bottom_label": "CARRYMINATI (44M)",
        "headline": "TECHNO VS CARRYMINATI",
        "subheadline": "5-STAR POLICE ESCAPE! 🚨🚓",
        "streamer_left": "techno_gamerz",
        "streamer_right": "carryminati",
    },
]

def main():
    print(f"=== Producing and Uploading {len(VIDEOS)} Videos to Channel 2 ===")
    results = []

    for idx, item in enumerate(VIDEOS, 1):
        out_clip = CLIPS_OUT_DIR / f"{item['id']}.mp4"
        out_thumb = CLIPS_OUT_DIR / f"{item['id']}_thumb.jpg"
        print(f"\n[{idx}/{len(VIDEOS)}] Rendering {item['id']}...")

        if item["type"] == "dual":
            render_dual_creator_clip(
                techno_video=item["top_src"],
                carry_video=item["bottom_src"],
                techno_start=item["top_start"],
                carry_start=item["bottom_start"],
                duration=item["duration"],
                out_path=out_clip,
                hook_banner=item["hook_banner"],
                top_label=item["top_label"],
                bottom_label=item["bottom_label"],
            )
            extract_thumbnail(out_clip, out_thumb)
            create_dual_streamer_thumbnail(
                base_frame_path=out_thumb,
                out_thumb_path=out_thumb,
                headline=item["headline"],
                subheadline=item["subheadline"],
                streamer_left=item["streamer_left"],
                streamer_right=item["streamer_right"],
            )
        else:
            render_comparison_clip(
                gta6_source=item["bottom_src"],
                start=item["bottom_start"],
                end=item["bottom_start"] + item["duration"],
                out_path=out_clip,
                streamer_name=item["streamer"],
                gta5_source=item["top_src"],
                custom_title=item["title"],
            )
            extract_thumbnail(out_clip, out_thumb)
            create_streamer_thumbnail(
                base_frame_path=out_thumb,
                out_thumb_path=out_thumb,
                streamer_name=item["streamer"],
                headline=item["headline"],
                subheadline=item["subheadline"],
            )

        print(f"RENDER COMPLETE: {out_clip.name} ({out_clip.stat().st_size / 1024 / 1024:.1f}MB)")

        # Upload targeting channel 2
        print(f"UPLOADING to channel2: {item['title']}...")
        upload_res = publish_short(
            clip_path=out_clip,
            caption=f"{item['title']} GTA 6 Vice City gameplay! #shorts #gta6 #gaming",
            title=item["title"],
            tags=["shorts", "gta6", "gaming", "funny"],
            account="channel2",
        )
        print(f"UPLOAD RESULT: {upload_res}")
        results.append((item, out_clip, out_thumb, upload_res))

    print("\n=== ALL 3 VIDEOS PROCESSED ===")
    for item, out_clip, out_thumb, res in results:
        yt = res.get("youtube", {})
        print(f"- {item['title']}: {yt.get('url')} (account: {yt.get('account')})")

if __name__ == "__main__":
    main()
