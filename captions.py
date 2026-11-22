"""Generate an ASS subtitle file with karaoke-style word-by-word highlighting.
Used by ffmpeg to burn captions into the clip.

ASS was chosen over SRT because:
- SRT can only show a phrase at a time. ASS supports per-character color
  overrides via the karaoke \\k tag, which is the look Opus Clip / CapCut
  popularised.
- ffmpeg's `ass` filter is reliable and dependency-free.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from config import CONFIG

# High-energy triggers for kinetic word coloring
TRIGGER_WORDS_RED = {
    "kill", "die", "wasted", "busted", "crash", "dead", "run", "stop", "police",
    "mar", "khatam", "police",
}

TRIGGER_WORDS_GREEN = {
    "money", "win", "secret", "gta6", "fast", "unreal", "chalo", "paisa",
}

TRIGGER_WORDS_YELLOW = {
    "gta", "bhai", "car", "gaadi", "insane", "omg", "bruh", "bro", "look",
    "wait", "what", "no", "yes", "caught", "help", "fail", "crazy", "dekho",
    "shala", "mission", "first", "vice", "city", "speed", "level", "five",
}


def _get_ass_header(w: int, h: int) -> str:
    fontsize = max(24, int(round(44 * (h / 1280))))
    outline = max(3, int(round(6 * (h / 1280))))
    margin_v = max(100, int(round(280 * (h / 1280))))
    margin_lr = max(20, int(round(40 * (w / 720))))

    banner_fontsize = max(20, int(round(28 * (h / 1280))))
    banner_outline = max(6, int(round(12 * (h / 1280))))
    banner_margin_top = max(40, int(round(70 * (h / 1280))))
    banner_margin_lr = max(20, int(round(35 * (w / 720))))

    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: HeaderBanner,Arial Black,{banner_fontsize},&H0000FFFF,&H00FFFFFF,&H00000000,&H95000000,-1,0,0,0,100,100,0,0,3,{banner_outline},1,8,{banner_margin_lr},{banner_margin_lr},{banner_margin_top},1
Style: Karaoke,Arial Black,{fontsize},&H00FFFFFF,&H0000F5FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,{outline},2,2,{margin_lr},{margin_lr},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _fmt_time(seconds: float) -> str:
    """ASS time: H:MM:SS.cs (centiseconds, not ms)."""
    if seconds < 0:
        seconds = 0
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _split_into_lines(words: list[dict[str, Any]], max_chars: int = 28) -> list[list[dict[str, Any]]]:
    """Pack words into display lines of roughly max_chars chars. Each line is
    a separate ASS dialogue entry so the highlight resets per phrase."""
    lines: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    cur_len = 0
    for w in words:
        word = w["word"]
        addition = len(word) + (1 if cur else 0)
        if cur and cur_len + addition > max_chars:
            lines.append(cur)
            cur = []
            cur_len = 0
        cur.append(w)
        cur_len += addition
    if cur:
        lines.append(cur)
    return lines


def build_ass(words: list[dict[str, Any]], clip_start: float, clip_end: float, out_path: Path,
              hook_banner: str | None = None) -> Path:
    """Write an ASS file covering [clip_start, clip_end] of the source video.

    `words` is the full transcript word list; we slice it to the clip window
    and shift timestamps to be relative to the clip start.
    `hook_banner` adds an attention-grabbing sticky header at the top.
    """
    dur_total = max(1.0, clip_end - clip_start)
    events: list[str] = []

    # 1. Add sticky hook banner if provided
    if hook_banner and hook_banner.strip():
        banner_clean = hook_banner.strip().replace("{", "(").replace("}", ")")
        events.append(
            f"Dialogue: 1,0:00:00.00,{_fmt_time(dur_total)},HeaderBanner,,0,0,0,,{banner_clean}"
        )

    relevant = [w for w in words if w["start"] >= clip_start and w["end"] <= clip_end]
    if not relevant:
        body = _get_ass_header(CONFIG.output_width, CONFIG.output_height)
        if events:
            body += "\n".join(events) + "\n"
        out_path.write_text(body, encoding="utf-8")
        return out_path

    # Filter out Whisper hallucinated loops (consecutive identical words > 2 times)
    filtered: list[dict[str, Any]] = []
    repeat_count = 0
    prev_w = ""
    for w in relevant:
        w_clean = w.get("word", "").strip().lower()
        if w_clean == prev_w:
            repeat_count += 1
        else:
            prev_w = w_clean
            repeat_count = 1
        if repeat_count <= 2:
            filtered.append(w)

    # Shift to clip-relative time.
    rel = [
        {"start": w["start"] - clip_start, "end": w["end"] - clip_start, "word": w["word"]}
        for w in filtered
    ]

    lines = _split_into_lines(rel)

    for line in lines:
        line_start = line[0]["start"]
        # End each line when the next line starts, or at clip end.
        line_end = line[-1]["end"] + 0.4
        # Build the karaoke text with emotion-driven color accents.
        parts: list[str] = []
        for w in line:
            dur_cs = max(1, int(round((w["end"] - w["start"]) * 100)))
            # Escape any braces in the word.
            word_text = w["word"].replace("{", "(").replace("}", ")")
            w_clean = word_text.strip().lower().strip(".,!?:;\"'")

            if w_clean in TRIGGER_WORDS_RED:
                color_tag = r"\c&H001E1EFF&"   # Crimson Red
            elif w_clean in TRIGGER_WORDS_GREEN:
                color_tag = r"\c&H0033FF00&"   # Neon Lime/Green
            elif w_clean in TRIGGER_WORDS_YELLOW or (len(w_clean) > 2 and word_text.isupper()):
                color_tag = r"\c&H0000FFFF&"   # Neon Electric Yellow
            else:
                color_tag = ""

            parts.append(rf"{{\k{dur_cs}{color_tag}}}{word_text}")
        text = " ".join(parts).replace("} {", "}{")

        if CONFIG.caption_style == "block":
            # Plain block style: show whole line, no karaoke highlight.
            text = " ".join(w["word"].replace("{", "(").replace("}", ")") for w in line)
            text = r"{\fad(100,100)}" + text

        events.append(
            f"Dialogue: 0,{_fmt_time(line_start)},{_fmt_time(line_end)},"
            f"Karaoke,,0,0,0,,{text}"
        )

    body = _get_ass_header(CONFIG.output_width, CONFIG.output_height)
    body += "\n".join(events) + "\n"
    out_path.write_text(body, encoding="utf-8")
    return out_path
