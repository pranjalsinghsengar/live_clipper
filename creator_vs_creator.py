"""Creator vs Creator (Techno Gamerz vs CarryMinati) Split-Screen Producer & Dual Thumbnail Engine."""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance

from config import CONFIG
from captions import _fmt_time

log = logging.getLogger("creator_vs_creator")

STREAMERS_DIR = Path(__file__).parent / "assets" / "streamers"

def _escape_ass(text: str) -> str:
    return text.replace("\\", "").replace("{", "").replace("}", "")

def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_paths = [
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for fp in font_paths:
        if Path(fp).exists():
            try:
                return ImageFont.truetype(fp, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def build_dual_streamer_ass(
    techno_words: list[dict[str, Any]],
    carry_words: list[dict[str, Any]],
    start_t: float,
    start_c: float,
    duration: float,
    ass_path: Path,
    hook_banner: str = "TECHNO GAMERZ VS CARRYMINATI",
    top_label: str = "TECHNO GAMERZ (39M)",
    bottom_label: str = "CARRYMINATI (44M)",
) -> None:
    """Generate ASS subtitle file tailored for dual creator showdown."""
    ass_path.parent.mkdir(parents=True, exist_ok=True)
    t_end = _fmt_time(duration)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Header, Arial Black, 26, &H00FFFFFF, &H000000FF, &H00000000, &HA0000000, 1, 0, 0, 0, 100, 100, 0, 0, 3, 3, 0, 8, 15, 15, 20, 1
Style: TopBadge, Arial Black, 22, &H0000FFFF, &H000000FF, &H00000000, &HB0000000, 1, 0, 0, 0, 100, 100, 0, 0, 3, 2, 0, 7, 20, 20, 75, 1
Style: VSBadge, Arial Black, 28, &H0000E5FF, &H000000FF, &H00000000, &HE0000000, 1, 0, 0, 0, 100, 100, 0, 0, 3, 3, 0, 5, 20, 20, 0, 1
Style: BottomBadge, Arial Black, 22, &H0033FF00, &H000000FF, &H00000000, &HB0000000, 1, 0, 0, 0, 100, 100, 0, 0, 3, 2, 0, 7, 20, 20, 655, 1
Style: TechnoSubtitle, Arial Black, 30, &H0000FFFF, &H000000FF, &H00000000, &H80000000, 1, 0, 0, 0, 100, 100, 0, 0, 1, 3, 2, 2, 25, 25, 680, 1
Style: CarrySubtitle, Arial Black, 30, &H0033FF00, &H000000FF, &H00000000, &H80000000, 1, 0, 0, 0, 100, 100, 0, 0, 1, 3, 2, 2, 25, 25, 80, 1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,{t_end},Header,,0,0,0,,{_escape_ass(hook_banner)}
Dialogue: 0,0:00:00.00,{t_end},TopBadge,,0,0,0,,{_escape_ass(top_label)}
Dialogue: 0,0:00:00.00,{t_end},VSBadge,,0,0,0,,{{\\pos(360,640)}}⚡ VS ⚡
Dialogue: 0,0:00:00.00,{t_end},BottomBadge,,0,0,0,,{_escape_ass(bottom_label)}
"""
    ass_path.write_text(header, encoding="utf-8")


def render_dual_creator_clip(
    techno_video: Path,
    carry_video: Path,
    techno_start: float,
    carry_start: float,
    duration: float,
    out_path: Path,
    hook_banner: str = "TECHNO GAMERZ VS CARRYMINATI! ⚡",
    top_label: str = "TECHNO GAMERZ • GTA 6",
    bottom_label: str = "CARRYMINATI • GTA 6",
) -> Path:
    """Render a 720x1280 60fps vertical split-screen comparison between Techno Gamerz and CarryMinati."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ass_path = out_path.with_suffix(".ass")

    build_dual_streamer_ass(
        techno_words=[],
        carry_words=[],
        start_t=techno_start,
        start_c=carry_start,
        duration=duration,
        ass_path=ass_path,
        hook_banner=hook_banner,
        top_label=top_label,
        bottom_label=bottom_label,
    )

    ass_filter_path = str(ass_path).replace("\\", "/").replace(":", r"\:")

    # Audio alternating: first half Techno Gamerz audio, second half CarryMinati audio!
    half = duration / 2.0
    filter_complex = (
        f"[0:v]crop=ih*9/8:ih,scale=720:640:flags=lanczos,setsar=1[top];"
        f"[1:v]crop=ih*9/8:ih,scale=720:640:flags=lanczos,setsar=1[bottom];"
        f"[top][bottom]vstack=inputs=2[stacked];"
        f"[stacked]drawbox=y=638:h=4:color=0x00FFFF@0.9:t=fill,ass='{ass_filter_path}'[outv];"
        f"[0:a]atrim=0:{half:.3f},asetpts=PTS-STARTPTS[a_top];"
        f"[1:a]atrim={half:.3f}:{duration:.3f},asetpts=PTS-STARTPTS[a_bottom];"
        f"[a_top][a_bottom]concat=n=2:v=0:a=1[outa]"
    )

    cmd = [
        CONFIG.ffmpeg_path or "ffmpeg",
        "-y",
        "-ss", f"{techno_start:.3f}",
        "-t", f"{duration:.3f}",
        "-i", str(techno_video),
        "-ss", f"{carry_start:.3f}",
        "-t", f"{duration:.3f}",
        "-i", str(carry_video),
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "[outa]",
        "-c:v", "h264_videotoolbox",
        "-b:v", "6M",
        "-r", "60",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-ac", "2",
        "-t", f"{duration:.3f}",
        "-movflags", "+faststart",
        str(out_path),
    ]

    log.info("Rendering Dual Creator Showdown -> %s (%.1fs)", out_path.name, duration)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        log.error("FFmpeg render failed: %s", res.stderr)
        raise RuntimeError(f"FFmpeg error: {res.stderr[:200]}")

    return out_path


def create_dual_streamer_thumbnail(
    base_frame_path: Path,
    out_thumb_path: Path,
    headline: str = "TECHNO VS CARRYMINATI",
    subheadline: str = "WHO PLAYED GTA 6 BETTER?! 😱",
    streamer_left: str = "techno_gamerz",
    streamer_right: str = "carryminati",
) -> Path:
    """Design a high-CTR dual streamer showdown thumbnail featuring both creators."""
    out_thumb_path.parent.mkdir(parents=True, exist_ok=True)
    base = Image.open(base_frame_path).convert("RGBA")
    if base.size != (720, 1280):
        base = base.resize((720, 1280), Image.Resampling.LANCZOS)

    base = ImageEnhance.Color(base).enhance(1.3)
    base = ImageEnhance.Contrast(base).enhance(1.2)
    draw = ImageDraw.Draw(base)

    # Top overlay
    top_overlay = Image.new("RGBA", (720, 260), (0, 0, 0, 190))
    base.paste(top_overlay, (0, 0), top_overlay)
    draw.rectangle([0, 0, 720, 12], fill=(255, 30, 30, 255))

    font_head = _get_font(46)
    font_sub = _get_font(32)

    def draw_text_with_outline(text, x, y, font, fill_color, outline_color=(0, 0, 0), stroke_width=6):
        for dx in range(-stroke_width, stroke_width + 1):
            for dy in range(-stroke_width, stroke_width + 1):
                if dx * dx + dy * dy <= stroke_width * stroke_width:
                    draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
        draw.text((x, y), text, font=font, fill=fill_color)

    head_bbox = draw.textbbox((0, 0), headline, font=font_head)
    head_w = head_bbox[2] - head_bbox[0]
    head_x = (720 - head_w) // 2
    draw_text_with_outline(headline, head_x, 40, font_head, (255, 230, 0), (0, 0, 0), stroke_width=6)

    sub_bbox = draw.textbbox((0, 0), subheadline, font=font_sub)
    sub_w = sub_bbox[2] - sub_bbox[0]
    sub_x = (720 - sub_w) // 2
    draw.rounded_rectangle([sub_x - 18, 115 - 6, sub_x + sub_w + 18, 115 + (sub_bbox[3] - sub_bbox[1]) + 8], radius=10, fill=(255, 255, 255, 240), outline=(0, 0, 0), width=3)
    draw.text((sub_x, 115), subheadline, font=font_sub, fill=(200, 0, 0))

    # Add both creator circular stickers on bottom left and bottom right!
    def make_circular_badge(img_path: Path, size: int, border_color: tuple[int, int, int, int]) -> Image.Image:
        im = Image.open(img_path).convert("RGBA")
        im = ImageOps.fit(im, (size, size), centering=(0.5, 0.5))
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)

        b_size = size + 20
        out = Image.new("RGBA", (b_size, b_size), (0, 0, 0, 0))
        d = ImageDraw.Draw(out)
        d.ellipse((3, 3, b_size - 3, b_size - 3), fill=(0, 0, 0, 160))
        d.ellipse((2, 2, b_size - 2, b_size - 2), outline=border_color, width=8)

        circle_im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        circle_im.paste(im, (0, 0), mask=mask)
        out.paste(circle_im, (10, 10), mask=circle_im)
        return out

    st_size = 190
    left_path = STREAMERS_DIR / f"{streamer_left}.jpg"
    right_path = STREAMERS_DIR / f"{streamer_right}.jpg"
    if not left_path.exists():
        left_path = STREAMERS_DIR / "techno_gamerz.jpg"
    if not right_path.exists():
        right_path = STREAMERS_DIR / "carryminati.jpg"

    left_badge = make_circular_badge(left_path, st_size, (0, 255, 255, 255))
    right_badge = make_circular_badge(right_path, st_size, (255, 230, 0, 255))

    b_size = st_size + 20
    base.paste(left_badge, (30, 1280 - b_size - 40), mask=left_badge)
    base.paste(right_badge, (720 - b_size - 30, 1280 - b_size - 40), mask=right_badge)

    # Center VS Badge between stickers
    font_vs = _get_font(42)
    vs_text = "VS"
    vs_bbox = draw.textbbox((0, 0), vs_text, font=font_vs)
    vs_w = vs_bbox[2] - vs_bbox[0]
    vs_x = (720 - vs_w) // 2
    vs_y = 1280 - b_size + 30
    draw.ellipse([vs_x - 16, vs_y - 12, vs_x + vs_w + 16, vs_y + 45], fill=(220, 20, 20, 250), outline=(255, 255, 255), width=3)
    draw.text((vs_x, vs_y - 6), vs_text, font=font_vs, fill=(255, 255, 255))

    rgb_thumb = base.convert("RGB")
    rgb_thumb.save(out_thumb_path, "JPEG", quality=95)
    return out_thumb_path
