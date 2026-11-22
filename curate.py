"""Viral-moment curation. This replaces Opus Clip's AI.

Strategy:
  1. If a local Antigravity model is configured (Gemma 4 26B via LiteRT), we
     hand the transcript to a local Antigravity agent and ask it to return
     JSON-formatted clip suggestions.
  2. If no model is configured (e.g. user has < 24GB RAM and skipped the
     Antigravity install), we fall back to a pure-Python heuristic that picks
     the longest non-silent segments of CLIP_MIN..MAX seconds.

Either path returns a list of dicts shaped like:
  {
    "start": float,         # seconds
    "end": float,           # seconds
    "title": str,           # short hook / caption headline
    "caption": str,         # full caption text for the social post
    "reason": str,           # why this moment is good (for logs only)
  }
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from config import CONFIG
from transcribe import transcribe


# --- Heuristic fallback ---------------------------------------------------

def _heuristic_curate(transcript: dict[str, Any]) -> list[dict[str, Any]]:
    """Pick clip-length windows from the word-level transcript. Drops silent
    gaps and aims for ~45s clips by default."""
    words = transcript.get("words", [])
    if not words:
        return []

    min_s = CONFIG.clip_min_seconds
    max_s = CONFIG.clip_max_seconds
    target = (min_s + max_s) / 2

    clips: list[dict[str, Any]] = []
    i = 0
    while i < len(words):
        window_start = words[i]["start"]
        j = i
        while j < len(words) and words[j]["end"] - window_start < target:
            j += 1
        end = words[j - 1]["end"] if j > i else words[i]["end"]
        duration = end - window_start
        if duration < min_s:
            i = j
            continue
        if duration > max_s:
            end = window_start + max_s

        text = " ".join(w["word"] for w in words[i:j])
        # First 6-8 words as a hook.
        hook_words = [w["word"] for w in words[i:i + 8]]
        hook = " ".join(hook_words).strip()
        if len(hook) > 60:
            hook = hook[:57].rstrip() + "..."

        clips.append({
            "start": round(window_start, 2),
            "end": round(end, 2),
            "title": hook,
            "caption": text[:220],
            "reason": "heuristic: contiguous speech window",
        })
        i = j
    return clips[: CONFIG.max_clips_per_video]


# --- Antigravity SDK call -------------------------------------------------

_PROMPT_TEMPLATE = """You are a viral short-form video curator.

You are given a JSON transcript of a long video. The "words" array contains
objects with start, end (seconds) and word fields.

Pick the {max_clips} most shareable moments from this transcript for Instagram
Reels and TikTok. Each moment must be {min_s}-{max_s} seconds long.

A good short clip:
- Hooks the viewer in the first 1-2 seconds with a surprising claim, a
  question, or a strong opinion.
- Stands alone - a stranger who has never seen the source video can follow it.
- Ends on a punchline, a contradiction, or an open question - never mid-sentence.

Return ONLY a JSON array. No prose, no markdown fences. Each element:
{{
  "start": <float, seconds>,
  "end":   <float, seconds>,
  "title": <string, max 60 chars - the on-screen hook>,
  "caption": <string, max 220 chars - the post caption incl. 2-3 hashtags>,
  "reason": <string, one sentence why this works>
}}

TRANSCRIPT JSON:
{transcript_json}
"""


def _strip_to_json_array(text: str) -> list[dict[str, Any]]:
    """LLMs sometimes wrap JSON in ```json fences or add stray text. Be lenient."""
    # Try direct parse first.
    try:
        v = json.loads(text)
        if isinstance(v, list):
            return v
        if isinstance(v, dict) and "clips" in v:
            return v["clips"]
    except json.JSONDecodeError:
        pass
    # Find the first [ ... ] block.
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"Curator returned unparseable response: {text[:500]}")


def _antigravity_curate(transcript: dict[str, Any]) -> list[dict[str, Any]]:
    """Call Antigravity SDK with Gemma 4 26B via LiteRT. Runs fully offline."""
    # Lazy import - keeps the CLI fast when Antigravity isn't being used.
    from google.antigravity import Agent, LiteRTAgentConfig

    model_path = Path(CONFIG.antigravity_model_path).expanduser()
    if not model_path.exists():
        raise FileNotFoundError(
            f"Antigravity model not found at {model_path}. Run the litert-lm "
            f"import command in the README, or leave ANTIGRAVITY_MODEL_PATH "
            f"blank to use the heuristic curator."
        )

    # Trim the transcript so it fits in Gemma's context window. We keep every
    # word but only its start/end - the LLM doesn't need the audio.
    words = transcript.get("words", [])
    # Cap at ~8k words to stay safe under 8k context. (~1.5h of dense speech.)
    if len(words) > 8000:
        words = words[:8000]
    slim = {
        "language": transcript.get("language"),
        "duration_seconds": transcript.get("duration_seconds"),
        "words": words,
    }

    prompt = _PROMPT_TEMPLATE.format(
        max_clips=CONFIG.max_clips_per_video,
        min_s=CONFIG.clip_min_seconds,
        max_s=CONFIG.clip_max_seconds,
        transcript_json=json.dumps(slim, ensure_ascii=False),
    )

    # Prepend the skill file content if present, so users can edit curator
    # behaviour without touching code. Antigravity's IDE also reads these
    # files natively; here we load them explicitly for the SDK path.
    skill_path = Path(__file__).parent / "antigravity" / "skills" / "curate_clips.md"
    if skill_path.exists():
        skill_text = skill_path.read_text()
        prompt = f"{skill_text}\n\n---\n\n{prompt}"

    config = LiteRTAgentConfig(
        model_path=str(model_path),
        backend=CONFIG.antigravity_backend,  # "gpu" for Apple Silicon Metal
    )

    async def _run() -> str:
        async with Agent(config) as agent:
            chunks: list[str] = []
            async for token in await agent.chat(prompt):
                chunks.append(token)
            return "".join(chunks)

    raw = asyncio.run(_run())
    clips = _strip_to_json_array(raw)

    # Validate + clamp.
    cleaned: list[dict[str, Any]] = []
    for c in clips:
        start = float(c.get("start", 0))
        end = float(c.get("end", start + 45))
        if end <= start:
            continue
        if end - start > CONFIG.clip_max_seconds:
            end = start + CONFIG.clip_max_seconds
        if end - start < CONFIG.clip_min_seconds:
            # nudge start back so the window stays valid
            start = max(0, end - CONFIG.clip_min_seconds)
        cleaned.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "title": str(c.get("title", ""))[:60],
            "caption": str(c.get("caption", ""))[:220],
            "reason": str(c.get("reason", "")),
        })
    return cleaned[: CONFIG.max_clips_per_video]


# --- Public entrypoint ----------------------------------------------------

def curate(video_path: Path, concept_id: int) -> list[dict[str, Any]]:
    """Run transcription + curation. Returns the clip suggestions list."""
    transcript = transcribe(video_path, concept_id)

    if CONFIG.antigravity_enabled:
        try:
            return _antigravity_curate(transcript)
        except Exception as e:
            # Don't lose the run - fall back to heuristic.
            print(f"[curate] Antigravity failed ({e!r}); falling back to heuristic.")
            return _heuristic_curate(transcript)
    return _heuristic_curate(transcript)
