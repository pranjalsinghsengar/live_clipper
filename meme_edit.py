"""Meme-Infused Video Producer for YouTube Shorts & Reels.

Generates viral 9:16 vertical videos with iconic meme reaction cuts:
- Option 1: GTA 5 vs GTA 6 split-screen comparison + meme reaction insert
- Option 2: Full-screen GTA 6 gameplay highlight + kinetic subtitles + meme reaction cut
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from config import CONFIG
from compare_edit import render_comparison_clip, classify_action, build_comparison_ass
from captions import build_ass, _fmt_time

log = logging.getLogger("meme_edit")

MEMES_DIR = Path(__file__).parent / "assets" / "memes" / "ready"


def get_meme_clip(meme_name: str) -> Path:
    """Return path to standardized 720x1280 60fps meme reaction clip."""
    clip_path = MEMES_DIR / f"{meme_name}.mp4"
    if not clip_path.exists():
        # Fallback to the rock if requested meme is not found
        fallback = MEMES_DIR / "the_rock.mp4"
        if fallback.exists():
            return fallback
        raise FileNotFoundError(f"Meme clip {meme_name} not found in {MEMES_DIR}")
    return clip_path


def _concat_videos(segments: list[Path], out_path: Path) -> Path:
    """Concatenate 720x1280 60fps video files seamlessly."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = out_path.with_suffix(".concat.txt")

    lines = [f"file '{str(p.resolve())}'" for p in segments]
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    cmd = [
        CONFIG.ffmpeg_path or "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-c:v", "h264_videotoolbox",
        "-b:v", "6M",
        "-c:a", "aac",
        "-b:a", "192k",
        "-r", "60",
        "-movflags", "+faststart",
        str(out_path),
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if list_file.exists():
        list_file.unlink()

    if res.returncode != 0:
        log.error("Concat failed: %s", res.stderr)
        raise RuntimeError(f"Concat failed: {res.stderr[:200]}")

    return out_path


def render_comparison_with_meme(
    gta6_source: Path,
    start: float,
    end: float,
    out_path: Path,
    meme_name: str = "the_rock",
    mid_offset: float | None = None,
    words: list[dict[str, Any]] | None = None,
    streamer_name: str = "CarryMinati",
    gta5_source: Path | None = None,
    custom_title: str | None = None,
) -> tuple[Path, float]:
    """Render a GTA 5 vs GTA 6 split-screen comparison with a meme reaction cut inserted at the midpoint."""
    duration = end - start
    if mid_offset is None:
        mid_offset = duration * 0.55  # Insert slightly after halfway for build-up

    t_mid = start + mid_offset
    part1_out = out_path.with_name(f"{out_path.stem}_part1.mp4")
    part2_out = out_path.with_name(f"{out_path.stem}_part2.mp4")

    # Render Part 1
    render_comparison_clip(
        gta6_source=gta6_source,
        start=start,
        end=t_mid,
        out_path=part1_out,
        words=words,
        streamer_name=streamer_name,
        gta5_source=gta5_source,
        custom_title=custom_title,
    )

    # Render Part 2
    render_comparison_clip(
        gta6_source=gta6_source,
        start=t_mid,
        end=end,
        out_path=part2_out,
        words=words,
        streamer_name=streamer_name,
        gta5_source=gta5_source,
        custom_title=custom_title,
    )

    meme_path = get_meme_clip(meme_name)

    # Stitch Part 1 + Meme + Part 2
    _concat_videos([part1_out, meme_path, part2_out], out_path)

    # Clean intermediate parts
    for p in [part1_out, part2_out, part1_out.with_suffix(".ass"), part2_out.with_suffix(".ass")]:
        if p.exists():
            p.unlink()

    # Get final duration
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(out_path)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    final_dur = float(res.stdout.strip()) if res.returncode == 0 else duration + 2.0

    log.info("Rendered comparison with meme (%s) -> %s (%.1fs)", meme_name, out_path.name, final_dur)
    return out_path, final_dur


def render_highlight_with_meme(
    source_video: Path,
    start: float,
    end: float,
    out_path: Path,
    meme_name: str = "the_rock",
    mid_offset: float | None = None,
    words: list[dict[str, Any]] | None = None,
    streamer_name: str = "CarryMinati",
    title_text: str = "CARRYMINATI GTA 6 MOMENT! 😱",
) -> tuple[Path, float]:
    """Render a full-screen vertical 9:16 highlight Short with kinetic subtitles and a meme reaction cut."""
    duration = end - start
    if mid_offset is None:
        mid_offset = duration * 0.55

    t_mid = start + mid_offset
    part1_out = out_path.with_name(f"{out_path.stem}_hpart1.mp4")
    part2_out = out_path.with_name(f"{out_path.stem}_hpart2.mp4")

    def _render_hpart(s_time: float, e_time: float, p_out: Path):
        dur = e_time - s_time
        ass_path = p_out.with_suffix(".ass")
        build_ass(
            words=words or [],
            clip_start=s_time,
            clip_end=e_time,
            out_path=ass_path,
            hook_banner=title_text,
        )
        ass_escaped = str(ass_path).replace("\\", "/").replace(":", r"\:")

        vf = (
            f"crop=ih*9/16:ih,scale=720:1280:flags=lanczos,setsar=1,"
            f"ass='{ass_escaped}'"
        )
        cmd = [
            CONFIG.ffmpeg_path or "ffmpeg",
            "-y",
            "-ss", f"{s_time:.3f}",
            "-to", f"{e_time:.3f}",
            "-i", str(source_video),
            "-vf", vf,
            "-c:v", "h264_videotoolbox",
            "-b:v", "6M",
            "-r", "60",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-ac", "2",
            "-t", f"{dur:.3f}",
            str(p_out),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Part render failed: {res.stderr[:200]}")

    _render_hpart(start, t_mid, part1_out)
    _render_hpart(t_mid, end, part2_out)

    meme_path = get_meme_clip(meme_name)

    _concat_videos([part1_out, meme_path, part2_out], out_path)

    for p in [part1_out, part2_out, part1_out.with_suffix(".ass"), part2_out.with_suffix(".ass")]:
        if p.exists():
            p.unlink()

    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(out_path)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    final_dur = float(res.stdout.strip()) if res.returncode == 0 else duration + 2.0

    log.info("Rendered highlight with meme (%s) -> %s (%.1fs)", meme_name, out_path.name, final_dur)
    return out_path, final_dur
