"""GTA 5 vs GTA 6 Split-Screen Comparison Video Producer.

Creates ultra-high retention YouTube Shorts / TikTok comparison videos:
- Top 50%: GTA V (2013) comparison gameplay with branded badge
- Divider: Glowing neon 4px cyan border + '⚡ VS ⚡' badge
- Bottom 50%: GTA VI (2025) live streamer gameplay (Carry, Speed, Techno, etc.)
- Top Sticky Header: '🔴 GTA 5 VS GTA 6: [ACTION]! 😱'
- Kinetic Karaoke Subtitles: Highlights streamer's dialogue in the bottom half.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from config import CONFIG
from captions import build_ass, _fmt_time

def _escape_ass(text: str) -> str:
    return text.replace("\\", "").replace("{", "").replace("}", "")

log = logging.getLogger("compare_edit")

GTA5_ASSETS_DIR = Path(__file__).parent / "assets" / "gta5"

CATEGORIES = {
    "car_physics": {
        "keywords": ["car", "gaadi", "drive", "driving", "crash", "drift", "speed", "fast",
                     "lamborghini", "ferrari", "supercar", "racing", "vehicle", "bike", "motorcycle", "gaddi"],
        "title": "GTA 5 vs GTA 6: Car Crash Physics! 🚗💥",
        "hook_banner": "GTA 5 VS GTA 6: CAR CRASH PHYSICS",
    },
    "police_chase": {
        "keywords": ["police", "cop", "cops", "stars", "wanted", "chase", "siren", "arrest",
                     "busted", "jail", "helicopter", "patrol"],
        "title": "GTA 5 vs GTA 6: 5-Star Police Chase! 🚨🚓",
        "hook_banner": "GTA 5 VS GTA 6: 5-STAR POLICE CHASE",
    },
    "water_physics": {
        "keywords": ["water", "ocean", "swim", "swimming", "beach", "sea", "boat", "waves", "river", "dive"],
        "title": "GTA 5 vs GTA 6: Water & Wave Physics! 🌊🤯",
        "hook_banner": "GTA 5 VS GTA 6: WATER GRAPHICS",
    },
    "graphics": {
        "keywords": ["graphics", "rtx", "real", "lighting", "night", "rain", "reflection", "unreal",
                     "4k", "details", "look", "city", "sunset"],
        "title": "GTA 5 vs GTA 6: Insane Next-Gen Graphics! 🤯⚡",
        "hook_banner": "GTA 5 VS GTA 6: GRAPHICS COMPARISON",
    },
    "npc_reactions": {
        "keywords": ["npc", "punch", "fight", "hit", "pedestrian", "people", "laugh", "funny",
                     "fail", "reaction", "ragdoll", "knockout"],
        "title": "GTA 5 vs GTA 6: NPC Ragdoll & Physics! 😂💀",
        "hook_banner": "GTA 5 VS GTA 6: NPC RAGDOLL PHYSICS",
    },
}


def classify_action(words: list[dict[str, Any]] | None = None, title: str = "") -> dict[str, str]:
    """Classify the gameplay moment into a comparison category based on
    dialogue and title keywords."""
    combined_text = (title + " " + " ".join(w.get("word", "") for w in (words or []))).lower()

    best_cat = "car_physics"
    best_score = 0
    for cat_name, cat_data in CATEGORIES.items():
        score = sum(1 for kw in cat_data["keywords"] if kw in combined_text)
        if score > best_score:
            best_score = score
            best_cat = cat_name

    meta = CATEGORIES[best_cat]
    return {
        "category": best_cat,
        "title": meta["title"],
        "hook_banner": meta["hook_banner"],
    }


def get_or_create_gta5_reference(category: str, duration: float) -> Path:
    """Return path to GTA 5 footage for this category. If none found in
    assets/gta5/, generate a high-quality comparison loop."""
    GTA5_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Exact category file (e.g. assets/gta5/car_physics.mp4)
    cat_file = GTA5_ASSETS_DIR / f"{category}.mp4"
    if cat_file.exists() and cat_file.stat().st_size > 1000:
        return cat_file

    # 2. Any .mp4 in assets/gta5/
    any_files = list(GTA5_ASSETS_DIR.glob("*.mp4"))
    if any_files:
        return any_files[0]

    # 3. Create a clean 720p animated reference loop
    fallback_path = GTA5_ASSETS_DIR / f"reference_{category}.mp4"
    if not fallback_path.exists() or fallback_path.stat().st_size < 1000:
        log.info("Generating placeholder GTA 5 reference clip at %s", fallback_path)
        cmd = [
            CONFIG.ffmpeg_path or "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x1a2332:s=1280x720:d={max(5, int(duration) + 1)}:r=30",
            "-vf", "noise=c1s=8:c0f=u",
            "-c:v", "h264_videotoolbox",
            "-b:v", "4M",
            str(fallback_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=15)
        except Exception as e:
            log.warning("Could not create fallback reference: %s", e)
    return fallback_path


def build_comparison_ass(
    words: list[dict[str, Any]],
    start: float,
    end: float,
    ass_path: Path,
    streamer_name: str,
    hook_banner: str,
    top_label: str = "GTA V (2013)",
    bottom_label: str = "GTA VI (2025)",
) -> None:
    """Generate ASS subtitle file with:
    - Top sticky comparison header (e.g. 🔴 GTA 5 VS GTA 6: CAR PHYSICS! 😱)
    - Top video badge: 'GTA V (2013)'
    - Center divider badge: '⚡ VS ⚡'
    - Bottom video badge: 'GTA VI (2025) • {STREAMER}'
    - Kinetic word-by-word karaoke subtitles for streamer speech in the bottom half.
    """
    ass_path.parent.mkdir(parents=True, exist_ok=True)
    duration = end - start

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CompareHeader, Arial Black, 28, &H00FFFFFF, &H000000FF, &H00000000, &H95000000, 1, 0, 0, 0, 100, 100, 0, 0, 3, 3, 0, 8, 15, 15, 20, 1
Style: TopBadge, Arial Black, 22, &H0000FFFF, &H000000FF, &H00000000, &HB0000000, 1, 0, 0, 0, 100, 100, 0, 0, 3, 2, 0, 7, 20, 20, 75, 1
Style: VSBadge, Arial Black, 26, &H0000FFFF, &H000000FF, &H00000000, &HE0000000, 1, 0, 0, 0, 100, 100, 0, 0, 3, 3, 0, 5, 20, 20, 0, 1
Style: BottomBadge, Arial Black, 22, &H0033FF00, &H000000FF, &H00000000, &HB0000000, 1, 0, 0, 0, 100, 100, 0, 0, 3, 2, 0, 7, 20, 20, 655, 1
Style: Subtitle, Arial Black, 32, &H00FFFFFF, &H000000FF, &H00000000, &H80000000, 1, 0, 0, 0, 100, 100, 0, 0, 1, 3, 2, 2, 25, 25, 95, 1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    streamer_display = streamer_name.upper() if streamer_name else "CREATOR"
    full_bottom_badge = f"{bottom_label} • {streamer_display}"
    t_end = _fmt_time(duration)

    events = [
        f"Dialogue: 0,0:00:00.00,{t_end},CompareHeader,,0,0,0,,{_escape_ass(hook_banner)}",
        f"Dialogue: 0,0:00:00.00,{t_end},TopBadge,,0,0,0,,{_escape_ass(top_label)}",
        f"Dialogue: 0,0:00:00.00,{t_end},VSBadge,,0,0,0,,{{\\pos(360,640)}}VS",
        f"Dialogue: 0,0:00:00.00,{t_end},BottomBadge,,0,0,0,,{_escape_ass(full_bottom_badge)}",
    ]

    # Generate karaoke subtitles on streamer speech
    clip_words = [w for w in (words or []) if float(w.get("end", 0)) > start and float(w.get("start", 0)) < end]
    if clip_words:
        # Group into 4-word chunks
        chunk_size = 4
        for idx in range(0, len(clip_words), chunk_size):
            chunk = clip_words[idx : idx + chunk_size]
            c_start = max(0.0, float(chunk[0]["start"]) - start)
            c_end = min(duration, float(chunk[-1]["end"]) - start)
            if c_end <= c_start:
                continue

            k_parts = []
            for w in chunk:
                w_start = max(0.0, float(w["start"]) - start)
                w_end = min(duration, float(w["end"]) - start)
                cs = max(5, int((w_end - w_start) * 100))
                word_clean = _escape_ass(w.get("word", "").strip())
                w_lower = word_clean.lower()

                # Highlight colors
                if any(k in w_lower for k in ["gta", "car", "bhai", "insane", "bro", "crash"]):
                    k_parts.append(f"{{\\c&H0000FFFF&\\k{cs}}}{word_clean}{{\\c&H00FFFFFF&}}")
                elif any(k in w_lower for k in ["kill", "die", "wasted", "police", "fail"]):
                    k_parts.append(f"{{\\c&H001E1EFF&\\k{cs}}}{word_clean}{{\\c&H00FFFFFF&}}")
                elif any(k in w_lower for k in ["win", "secret", "gta6", "omg", "best"]):
                    k_parts.append(f"{{\\c&H0033FF00&\\k{cs}}}{word_clean}{{\\c&H00FFFFFF&}}")
                else:
                    k_parts.append(f"{{\\k{cs}}}{word_clean}")

            events.append(
                f"Dialogue: 1,{_fmt_time(c_start)},{_fmt_time(c_end)},Subtitle,,0,0,0,,{' '.join(k_parts)}"
            )

    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def render_comparison_clip(
    gta6_source: Path,
    start: float,
    end: float,
    out_path: Path,
    words: list[dict[str, Any]] | None = None,
    streamer_name: str = "Gamer",
    gta5_source: Path | None = None,
    custom_title: str | None = None,
) -> tuple[Path, float]:
    """Render a 720x1280 60fps split-screen GTA 5 vs GTA 6 comparison video."""
    duration = end - start
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ass_path = out_path.with_suffix(".ass")

    classification = classify_action(words, title=custom_title or "")
    hook_banner = classification["hook_banner"]

    build_comparison_ass(
        words=words or [],
        start=start,
        end=end,
        ass_path=ass_path,
        streamer_name=streamer_name,
        hook_banner=hook_banner,
    )

    if not gta5_source or not gta5_source.exists():
        gta5_source = get_or_create_gta5_reference(classification["category"], duration)

    ass_filter_path = str(ass_path).replace("\\", "/").replace(":", r"\:")

    filter_complex = (
        f"[1:v]crop=ih*9/8:ih,scale=720:640:flags=lanczos,setsar=1[top];"
        f"[0:v]crop=ih*9/8:ih,scale=720:640:flags=lanczos,setsar=1[bottom];"
        f"[top][bottom]vstack=inputs=2[stacked];"
        f"[stacked]drawbox=y=638:h=4:color=0x00FFFF@0.9:t=fill,ass='{ass_filter_path}'[outv]"
    )

    cmd = [
        CONFIG.ffmpeg_path or "ffmpeg",
        "-y",
        "-ss", f"{start:.3f}",
        "-to", f"{end:.3f}",
        "-i", str(gta6_source),
        "-stream_loop", "-1",
        "-i", str(gta5_source),
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "0:a",
        "-c:v", "h264_videotoolbox",
        "-b:v", "6M",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", f"{duration:.3f}",
        "-movflags", "+faststart",
        str(out_path),
    ]

    log.info("Rendering GTA 5 vs GTA 6 comparison edit -> %s (%.1fs)", out_path.name, duration)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        log.error("FFmpeg comparison render failed: %s", res.stderr)
        raise RuntimeError(f"FFmpeg render error: {res.stderr[:200]}")

    return out_path, duration
