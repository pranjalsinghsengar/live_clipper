"""Live curator: periodically runs Antigravity on the rolling transcript and
emits new clip suggestions, deduplicating against clips we've already picked
for this stream."""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from config import CONFIG
from db import (
    add_live_clip,
    get_stream,
    list_live_clips_for_stream,
)

log = logging.getLogger("live_curate")

GTA6_HOOK_TEMPLATES = [
    "{creator} in GTA 6 is UNREAL! 😱🔥",
    "{creator} Playing GTA 6 For The First Time! 🤯",
    "{creator} First Mission in GTA 6! 😂🚗",
    "GTA 6 Vice City Craziest Moment with {creator}! 💥",
    "{creator} Wasn't Ready For GTA 6 💀",
    "{creator} Escaping 5-Star Police in GTA 6! 🚨",
    "GTA 6 Graphics are INSANE! {creator} Reaction 🏎️💨",
    "{creator} Driving in GTA 6 Gone Wrong! 😂💥",
    "{creator} and Lucia Secret Mission in GTA 6! 🔥",
    "GTA 6 Car Physics with {creator}! 🚗💨",
    "{creator} Reaction to Vice City in GTA 6! ⚡",
    "{creator} Funniest Moment in GTA 6! 😂",
    "Craziest Stunt by {creator} in GTA 6! 🏎️💥",
    "GTA 6 Open World Exploration with {creator}! 🌴🔥",
]


def _resolve_creator_name(stream_id: int | None) -> str:
    if not stream_id:
        return "Gamer"
    try:
        info = get_stream(stream_id)
        if not info:
            return "Gamer"
        name = info.get("display_name") or info.get("channel") or ""
        name_lower = name.lower()
        if "speed" in name_lower:
            return "IShowSpeed"
        if "carry" in name_lower:
            return "CarryMinati"
        if "mythpat" in name_lower:
            return "Mythpat"
        if "techno" in name_lower:
            return "Techno Gamerz"
        if "total" in name_lower:
            return "Total Gaming"
        if "scout" in name_lower:
            return "ScoutOP"
        if "mortal" in name_lower:
            return "MortaL"
        if "dynamo" in name_lower:
            return "Dynamo"
        if "asgaming" in name_lower or "a_s" in name_lower:
            return "A_S Gaming"
        if "beast" in name_lower:
            return "MrBeast"
        return name or "Gamer"
    except Exception:
        return "Gamer"


def _clean_and_check_speech(words_list: list[dict]) -> tuple[bool, str]:
    """Check if the speech in words_list is repetitive hallucination (engine noise, music)
    or real speech. Returns (is_repetitive, clean_sample_text)."""
    import re
    raw_words = [w.get("word", "").strip() for w in words_list if w.get("word", "").strip()]
    if not raw_words or len(raw_words) < 5:
        return True, ""

    # Filter out punctuation, dashes, dots, numbers like -2
    meaningful = [
        w for w in raw_words
        if any(c.isalnum() for c in w)
        and not re.match(r"^[\W_]+$", w)
        and not re.match(r"^-\d+$", w)
    ]
    if len(meaningful) < 5:
        return True, ""

    # 1-gram consecutive duplication check (e.g. "पर पर पर" or "नहीं नहीं नहीं")
    consecutive_dupes = 0
    for k in range(1, len(meaningful)):
        if meaningful[k].lower() == meaningful[k - 1].lower():
            consecutive_dupes += 1

    # 2-gram consecutive duplication check (e.g. "पे जाने पे जाने" or "ye bhai ye bhai")
    bigrams = [(meaningful[k].lower(), meaningful[k + 1].lower()) for k in range(len(meaningful) - 1)]
    consecutive_bigram_dupes = 0
    for k in range(1, len(bigrams)):
        if bigrams[k] == bigrams[k - 1]:
            consecutive_bigram_dupes += 1

    unique_ratio = len(set(w.lower() for w in meaningful)) / len(meaningful) if meaningful else 1.0
    is_repetitive = (
        (consecutive_dupes >= 3)
        or (consecutive_bigram_dupes >= 2)
        or (len(meaningful) >= 8 and unique_ratio < 0.40)
    )

    deduped = []
    for w in meaningful:
        if not deduped or deduped[-1].lower() != w.lower():
            deduped.append(w)

    clean_sample = " ".join(deduped[:25])
    return is_repetitive, clean_sample


def _load_transcript(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {"words": [], "segments": [], "duration_seconds": 0.0}
    try:
        text = state_path.read_text().strip()
        if not text:
            return {"words": [], "segments": [], "duration_seconds": 0.0}
        return json.loads(text)
    except Exception as e:
        log.warning("Could not load transcript from %s: %s", state_path, e)
        return {"words": [], "segments": [], "duration_seconds": 0.0}


def _overlaps_existing(start: float, end: float, existing: list[dict]) -> bool:
    """True if [start, end] overlaps by more than 5s with any existing clip."""
    for c in existing:
        c_start = float(c["start_seconds"])
        c_end = float(c["end_seconds"])
        # Standard overlap test.
        overlap = min(end, c_end) - max(start, c_start)
        if overlap > 5.0:
            return True
    return False


def curate_rolling(
    stream_id: int,
    transcript_path: Path,
    stop_event: threading.Event,
    shared_agent_state: dict | None = None,
) -> None:
    """Loop: every live_curate_interval_seconds, send the recent transcript
    window to Antigravity and write any new clip suggestions to the DB.

    `shared_agent_state` lets the watcher pass a shared Antigravity Agent
    across all streams. If None, we lazily build one here. Sharing one
    model is essential - Gemma 4 26B takes 16GB+ of memory and ~30s to
    load per stream.
    """
    interval = CONFIG.live_curate_interval_seconds
    window_lookback = 600   # always re-curate last 10 min for context

    # Wait for the first Whisper window (~70s) before first pass
    initial_wait = min(70, interval)
    for _ in range(initial_wait):
        if stop_event.is_set():
            return
        time.sleep(1)

    while not stop_event.is_set():
        try:
            transcript = _load_transcript(transcript_path)
            words = transcript.get("words", [])
            if len(words) < 20:
                log.info("Stream %d: not enough transcript yet (%d words)",
                         stream_id, len(words))
                for _ in range(30):
                    if stop_event.is_set():
                        return
                    time.sleep(1)
                continue

            # Look at the last `window_lookback` seconds of transcript.
            current_end = words[-1]["end"] if words else 0.0
            window_start = max(0.0, current_end - window_lookback)
            window_words = [w for w in words if w["end"] >= window_start]
            if len(window_words) < 30:
                continue

            try:
                new_specs = _call_curator(window_words, shared_agent_state, stream_id=stream_id)
            except Exception as e:
                log.exception("Stream %d: curator call failed: %s", stream_id, e)
                continue

            if not new_specs:
                continue

            # Shift the timestamps back to be stream-relative (window_words were
            # already stream-relative because the curator sees absolute times
            # in the rolling transcript file).
            existing = list_live_clips_for_stream(stream_id)
            max_clips = getattr(CONFIG, "max_live_clips_per_stream", 3)
            if len(existing) >= max_clips:
                log.info("Stream %d: already reached max clips limit (%d/%d), skipping new clips",
                         stream_id, len(existing), max_clips)
                for _ in range(interval):
                    if stop_event.is_set():
                        return
                    time.sleep(1)
                continue

            spacing = getattr(CONFIG, "live_min_clip_spacing_seconds", 900)
            min_score = getattr(CONFIG, "min_viral_score", 8.0)
            added = 0
            for spec in new_specs:
                start = float(spec.get("start", 0))
                end = float(spec.get("end", start + 45))
                if end <= start:
                    continue

                # Quality gate: drop anything with viral_score < min_score
                score = float(spec.get("viral_score", 8.0))
                if score < min_score:
                    log.info("Stream %d: dropped candidate [%.0f-%.0f]s (viral score %.1f < %.1f threshold)",
                             stream_id, start, end, score, min_score)
                    continue

                if _overlaps_existing(start, end, existing):
                    continue
                if existing:
                    last_clip_end = max(float(c["end_seconds"]) for c in existing)
                    if start < last_clip_end + spacing:
                        log.debug("Stream %d: candidate [%.0f-%.0f]s within spacing window (%.0fs < %.0fs + %ds)",
                                  stream_id, start, end, start, last_clip_end, spacing)
                        continue
                cid = add_live_clip(
                    stream_id=stream_id,
                    start=start,
                    end=end,
                    title=spec.get("title", ""),
                    caption=spec.get("caption", ""),
                    reason=spec.get("reason", ""),
                )
                log.info("Stream %d: picked high-retention clip [%d-%d]s '%s' (viral_score=%.1f, live_clip=%d)",
                         stream_id, start, end, spec.get("title", "")[:40], score, cid)
                added += 1
                existing = list_live_clips_for_stream(stream_id)
            if added:
                log.info("Stream %d: added %d new clip(s)", stream_id, added)
        except Exception as e:
            log.exception("Stream %d: unexpected curate loop error: %s", stream_id, e)

        for _ in range(interval):
            if stop_event.is_set():
                return
            time.sleep(1)


_PROMPT_TEMPLATE = """You are an elite short-form video editor watching a rolling transcript of a LIVE GTA 6 (Grand Theft Auto VI) gaming stream.

Pick AT MOST 1 truly viral, exciting, high-retention moment from this transcript for YouTube Shorts.
Each clip must be {min_s}-{max_s} seconds long.

CRITICAL SELECTION CRITERIA:
- The segment MUST have real, engaging streamer dialogue or loud, funny reactions (screams, jokes, epic fails, clutch escapes, shock).
- ONLY pick moments that have strong viral potential and will get high view counts.
- Rate the moment on a viral_score scale of 1.0 to 10.0:
    * 9.0-10.0: Insane clutch, hysterical scream/laugh, shock moment, viral punchline.
    * 8.0-8.9: Great funny moment, high-energy fail, police chase highlight.
    * Below 8.0: Ordinary gameplay or conversational chat.
- DO NOT pick repetitive audio hallucinations (repeating the same word or syllable), engine droning, background music, silence, or mundane filler talk.
- If this window is boring, repetitive, or has no moment with viral_score >= 8.0, return [] (empty list). DO NOT force a clip.

Return ONLY a valid JSON array. No markdown fences, no explanatory text. Format:
[
  {{
    "start": <float, exact start seconds matching a word in the transcript>,
    "end":   <float, exact end seconds matching a word in the transcript>,
    "title": <string, max 70 chars, high-CTR hook with emojis>,
    "hook_banner": <string, max 35 chars, punchy header like '🔴 CARRY IN GTA 6! 😱'>,
    "caption": <string, max 220 chars, rich description with #shorts #gta6 #gaming>,
    "viral_score": <float, e.g. 8.5>,
    "reason": <string, brief justification>
  }}
]

If nothing in this window is worth clipping (viral_score < 8.0), return [].

TRANSCRIPT (most recent 10 min, word-level):
{transcript_json}
"""


def _call_curator(window_words: list[dict],
                  shared_agent_state: dict | None,
                  stream_id: int | None = None) -> list[dict[str, Any]]:
    """Call Antigravity (if available) or fall back to heuristic. Returns
    a list of clip specs with stream-relative timestamps."""
    # Pre-screen window: if speech is repetitive hallucination or empty, skip immediately
    is_rep, sample = _clean_and_check_speech(window_words)
    if is_rep and len(sample.split()) < 5:
        log.debug("Stream %s: skipping window due to repetitive speech or lack of words", stream_id)
        return []

    # Try Antigravity (Gemma 4 via LiteRT) first.
    if CONFIG.antigravity_enabled and shared_agent_state is not None:
        try:
            clips = _call_antigravity(window_words, shared_agent_state)
            if isinstance(clips, list):
                # Validate that Gemma's selected clip actually contains real speech
                filtered = []
                for c in clips:
                    c_start = float(c.get("start", 0))
                    c_end = float(c.get("end", 0))
                    clip_words = [w for w in window_words if c_start <= w.get("start", 0) <= c_end]
                    c_rep, _ = _clean_and_check_speech(clip_words)
                    if not c_rep:
                        filtered.append(c)
                    else:
                        log.info("Stream %s: Gemma picked clip [%.0f-%.0f]s but dropped due to repetitive speech",
                                 stream_id, c_start, c_end)
                return filtered
        except Exception as e:
            log.warning("Antigravity failed (%s); falling back to heuristic.", e)

    # Heuristic fallback for live mode: pick the longest contiguous speech
    # window in the lookback range, capped to max_clip_seconds.
    return _heuristic_live(window_words, stream_id=stream_id)


def _call_antigravity(window_words: list[dict],
                      shared_agent_state: dict) -> list[dict[str, Any]]:
    import asyncio
    import re
    from google.antigravity import Agent, LiteRTAgentConfig

    if "agent" not in shared_agent_state:
        model_path = Path(CONFIG.antigravity_model_path).expanduser()
        config = LiteRTAgentConfig(
            model_path=str(model_path),
            backend=CONFIG.antigravity_backend,
        )

        loop = asyncio.new_event_loop()
        shared_agent_state["loop"] = loop
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True, name="agent-event-loop")
        loop_thread.start()

        async def _build():
            a = Agent(config)
            await a.__aenter__()
            return a

        shared_agent_state["agent"] = asyncio.run_coroutine_threadsafe(_build(), loop).result(timeout=180)

    agent = shared_agent_state["agent"]
    loop = shared_agent_state["loop"]

    slim = [{"start": w["start"], "end": w["end"], "word": w["word"]}
            for w in window_words]
    prompt = _PROMPT_TEMPLATE.format(
        min_s=CONFIG.clip_min_seconds,
        max_s=CONFIG.clip_max_seconds,
        transcript_json=json.dumps(slim, ensure_ascii=False),
    )

    async def _run() -> str:
        chunks: list[str] = []
        async for token in await agent.chat(prompt):
            chunks.append(token)
        return "".join(chunks)

    raw = asyncio.run_coroutine_threadsafe(_run(), loop).result(timeout=180)
    # Try direct JSON parse first.
    try:
        v = json.loads(raw)
        if isinstance(v, list):
            return v
        if isinstance(v, dict) and "clips" in v:
            return v["clips"]
    except json.JSONDecodeError:
        pass
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"Curator returned unparseable response: {raw[:300]}")


def _heuristic_live(window_words: list[dict], stream_id: int | None = None) -> list[dict[str, Any]]:
    """Pick the single longest contiguous speech window and format with high-CTR
    GTA 6 viral hooks and clean creator attribution."""
    if not window_words:
        return []
    # Find a window of ~45s with the most words (i.e. least silence).
    target_s = (CONFIG.clip_min_seconds + CONFIG.clip_max_seconds) / 2
    best = None
    best_word_count = 0
    for i in range(len(window_words)):
        j = i
        while j < len(window_words) and window_words[j]["end"] - window_words[i]["start"] < target_s:
            j += 1
        if j > i and (j - i) > best_word_count:
            best = (i, j)
            best_word_count = j - i
    if not best:
        return []
    i, j = best
    start = window_words[i]["start"]
    end = window_words[j - 1]["end"]
    if end - start < CONFIG.clip_min_seconds:
        return []
    if end - start > CONFIG.clip_max_seconds:
        end = start + CONFIG.clip_max_seconds

    creator = _resolve_creator_name(stream_id)
    is_repetitive, clean_sample = _clean_and_check_speech(window_words[i:j])
    if is_repetitive or len(clean_sample.split()) < 5:
        log.debug("Stream %s: skipping candidate window [%.0f-%.0f]s (repetitive or insufficient speech)",
                  stream_id, start, end)
        return []

    # Dynamic viral hook based on timestamp / position
    hook_idx = int(start // 45) % len(GTA6_HOOK_TEMPLATES)
    hook = GTA6_HOOK_TEMPLATES[hook_idx].format(creator=creator)

    # Title: Keep under 75 chars so #shorts #gta6 fits cleanly
    title = hook[:75]

    # Attention-grabbing top sticky hook banner (max 35 chars)
    hook_banners = [
        f"🔴 {creator.upper()} IN GTA 6! 😱",
        f"💀 {creator.upper()} CAN'T BELIEVE THIS",
        f"🚗 FIRST MISSION IN GTA 6 😂",
        f"🚨 5-STAR POLICE CHASE! 💥",
        f"😱 CRAZIEST MOMENT IN GTA 6 🔥",
        f"🏎️ {creator.upper()} IN VICE CITY 💀",
        f"⚡ GTA 6 GRAPHICS ARE INSANE!",
        f"🤯 {creator.upper()} FOUND A SECRET!",
    ]
    hook_banner = hook_banners[hook_idx % len(hook_banners)]

    caption = (
        f"[{creator}] \"{clean_sample}\" - Playing GTA 6 (Grand Theft Auto VI) live in Vice City! "
        f"Best gameplay moments and funny reactions. #shorts #gta6 #gaming #{creator.lower()}"
    )[:220]

    return [{
        "start": start,
        "end": end,
        "title": title,
        "caption": caption,
        "hook_banner": hook_banner,
        "viral_score": 8.0,
        "reason": f"gta6 viral speech ({creator})",
    }]
