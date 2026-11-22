"""Command-line interface for the pipeline.

Usage:
    python cli.py add "https://youtube.com/watch?v=..."
    python cli.py add /path/to/local.mp4 --title "My talk"
    python cli.py list                  # show concepts + content
    python cli.py queue                 # show todo concepts only
    python cli.py run                   # process up to 2 todo concepts
    python cli.py run --limit 5
    python cli.py run-one 42            # process one specific concept id
    python cli.py reset-stuck           # re-queue anything stuck in 'processing'
    python cli.py post                  # post one random ready clip
    python cli.py post 12               # post content row id 12
    python cli.py doctor                # verify config + tools
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from config import CONFIG
from db import (
    fetch_random_ready_clip,
    get_content,
    init_db,
    list_concepts,
    list_ready_content,
    mark_concept_failed,
    mark_concept_processed,
    reset_processing_concepts,
    # Live mode
    add_channel,
    list_channels,
    remove_channel,
    set_channel_enabled,
    list_active_streams,
    list_streams_for_cleanup,
    list_live_clips_for_stream,
)
from download import add_video_to_queue, ensure_tools_installed

console = Console()


def cmd_add(args: argparse.Namespace) -> int:
    init_db()
    cid = add_video_to_queue(args.url, title=args.title)
    console.print(f"[green]Added concept #{cid}[/green]: {args.url}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    init_db()
    concepts = list_concepts(limit=args.limit)

    t = Table(title="Concepts")
    t.add_column("ID", justify="right")
    t.add_column("Status")
    t.add_column("Source")
    t.add_column("Title")
    t.add_column("URL / path", overflow="fold")
    for c in concepts:
        t.add_row(str(c["id"]), c["status"], c["source"], c.get("title") or "",
                  c["video_url"])
    console.print(t)

    ready = list_ready_content(limit=args.limit)
    t2 = Table(title="Content (Ready to Post)")
    t2.add_column("ID", justify="right")
    t2.add_column("Concept", justify="right")
    t2.add_column("Title")
    t2.add_column("Status")
    t2.add_column("Clip path", overflow="fold")
    for c in ready:
        t2.add_row(str(c["id"]), str(c["concept_id"]), c["title"],
                   c["status"], c["clip_path"])
    console.print(t2)
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    init_db()
    todos = list_concepts(status="todo", limit=args.limit)
    if not todos:
        console.print("[yellow]Queue is empty.[/yellow]")
        return 0
    t = Table(title="Todo concepts")
    t.add_column("ID", justify="right")
    t.add_column("Source")
    t.add_column("Title")
    t.add_column("URL / path", overflow="fold")
    for c in todos:
        t.add_row(str(c["id"]), c["source"], c.get("title") or "", c["video_url"])
    console.print(t)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    init_db()
    ensure_tools_installed()
    # Import inside the function so `clips list` doesn't load Whisper.
    from pipeline import run_pending
    n = run_pending(limit=args.limit)
    console.print(f"[green]Rendered {n} clips.[/green]")
    return 0


def cmd_run_one(args: argparse.Namespace) -> int:
    init_db()
    ensure_tools_installed()
    from pipeline import process_concept
    from db import list_concepts
    concept = next((c for c in list_concepts(limit=10000) if c["id"] == args.concept_id), None)
    if concept is None:
        console.print(f"[red]Concept {args.concept_id} not found.[/red]")
        return 1
    n = process_concept(concept["id"], concept["video_url"], concept["source"])
    console.print(f"[green]Rendered {n} clips from concept {args.concept_id}.[/green]")
    return 0


def cmd_upload(args: argparse.Namespace) -> int:
    """Upload any video file directly to YouTube Shorts with multi-account failover."""
    init_db()
    file_path = Path(args.file_path).expanduser().resolve()
    if not file_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        return 1

    from post_youtube import publish_short
    title = args.title or file_path.stem.replace("_", " ").title()[:70]
    caption = args.caption or f"{title} #shorts #gta6 #gaming #gta5"

    console.print(f"[cyan]Uploading {file_path.name} to YouTube Shorts...[/cyan]")
    console.print(f"[yellow]Title:[/yellow] {title}")

    try:
        account_arg = getattr(args, "account", None)
        res = publish_short(clip_path=file_path, caption=caption, title=title, account=account_arg)
        yt_info = res.get("youtube", res)
        video_id = yt_info.get("video_id") or yt_info.get("id")
        account = yt_info.get("account", "primary")
        if video_id:
            console.print(f"[green]SUCCESS! Video published to YouTube on account '[bold]{account}[/bold]':[/green]")
            console.print(f"https://youtube.com/shorts/{video_id}")
            return 0
        else:
            console.print(f"[red]Upload failed: {res}[/red]")
            return 1
    except Exception as e:
        console.print(f"[red]Upload failed: {e}[/red]")
        return 1


def cmd_post(args: argparse.Namespace) -> int:
    init_db()
    if args.content_id:
        # Force-post a specific clip - bypass the random picker.
        from post_instagram import publish_reel
        from post_tiktok import publish_tiktok
        from post_youtube import publish_short
        from db import mark_content_posted
        clip = get_content(args.content_id)
        if clip is None:
            console.print(f"[red]Content {args.content_id} not found.[/red]")
            return 1
        state: dict = {}
        if CONFIG.instagram_enabled:
            state.update(publish_reel(Path(clip["clip_path"]), clip.get("caption") or ""))
        if CONFIG.tiktok_enabled:
            state.update(publish_tiktok(Path(clip["clip_path"]), clip.get("caption") or ""))
        if CONFIG.youtube_enabled:
            state.update(publish_short(Path(clip["clip_path"]), clip.get("caption") or "", title=clip.get("title")))
        mark_content_posted(clip["id"], state)
        console.print(f"[green]Posted content {clip['id']}.[/green]")
        return 0

    from post_loop import post_one
    state = post_one()
    if state is None:
        console.print("[yellow]No ready clips to post.[/yellow]")
        return 0
    console.print(f"[green]Posted. State: {state}[/green]")
    return 0


def cmd_reset_stuck(args: argparse.Namespace) -> int:
    init_db()
    n = reset_processing_concepts()
    console.print(f"[green]Re-queued {n} stuck concepts.[/green]")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Verify environment: paths, tools, API config."""
    init_db()
    issues: list[str] = []

    import shutil
    for tool in ("yt-dlp", "ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            issues.append(f"Missing CLI: {tool} (brew install {tool})")
    # streamlink is needed for live mode
    if not shutil.which("streamlink"):
        issues.append("Missing CLI: streamlink (brew install streamlink) - needed for live mode")

    # Python deps
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        issues.append("Missing Python dep: faster-whisper (pip install -r requirements.txt)")

    # Antigravity
    if CONFIG.antigravity_enabled:
        console.print("[green]Antigravity:[/green] model present at "
                      f"{CONFIG.antigravity_model_path}")
    else:
        console.print("[yellow]Antigravity:[/yellow] no model path set "
                       "(curator will use heuristic fallback)")

    # Social APIs
    if CONFIG.instagram_enabled:
        console.print(f"[green]Instagram:[/green] configured (user {CONFIG.ig_user_id})")
    else:
        console.print("[yellow]Instagram:[/yellow] not configured (will be skipped)")
    if CONFIG.tiktok_enabled:
        console.print(f"[green]TikTok:[/green] configured")
    else:
        console.print("[yellow]TikTok:[/yellow] not configured (will be skipped)")

    # YouTube (OAuth)
    if CONFIG.youtube_enabled:
        if CONFIG.youtube_token_path.exists():
            console.print(f"[green]YouTube:[/green] OAuth token cached at "
                          f"{CONFIG.youtube_token_path}")
            try:
                from google.oauth2.credentials import Credentials
                creds = Credentials.from_authorized_user_file(
                    str(CONFIG.youtube_token_path), None
                )
                if creds.expired:
                    console.print("[yellow]YouTube token expired - will auto-refresh on next run.[/yellow]")
            except ImportError:
                pass
        elif CONFIG.youtube_client_secret_path.exists():
            console.print(f"[yellow]YouTube:[/yellow] client secret present but no token yet. "
                          f"Run: python cli.py youtube-auth")
            issues.append("YouTube: run `python cli.py youtube-auth` to complete OAuth")
        else:
            console.print("[yellow]YouTube:[/yellow] enabled but no client_secret.json found at "
                          f"{CONFIG.youtube_client_secret_path}")
            issues.append("YouTube: download OAuth client secret from Google Cloud Console")
    elif CONFIG.youtube_enabled_flag:
        # Flag is on but neither token nor client_secret exists yet.
        console.print(f"[yellow]YouTube:[/yellow] enabled in config but not set up yet. "
                      f"See README → YouTube Shorts setup.")
        issues.append("YouTube: not set up yet (see README)")
    else:
        console.print("[yellow]YouTube:[/yellow] disabled (YOUTUBE_ENABLED=0)")

    # Data dir
    console.print(f"[blue]Data dir:[/blue] {CONFIG.data_dir}")
    console.print(f"[blue]DB path:[/blue] {CONFIG.db_path}")

    if issues:
        console.print("\n[red]Issues found:[/red]")
        for i in issues:
            console.print(f"  - {i}")
        return 1
    console.print("\n[green]All checks passed.[/green]")
    return 0


def cmd_youtube_auth(args: argparse.Namespace) -> int:
    """One-time interactive OAuth flow for YouTube (supports multiple accounts)."""
    init_db()
    try:
        from post_youtube import run_interactive_auth
        account = getattr(args, "account", None)
        dest = run_interactive_auth(account=account)
        label = f"account '{account}'" if account else "primary account"
        console.print(f"[green]YouTube authorised for {label}.[/green] Token cached at {dest}")
        return 0
    except FileNotFoundError as e:
        console.print(f"[red]Setup incomplete:[/red]\n{e}")
        return 1
    except Exception as e:
        console.print(f"[red]OAuth flow failed:[/red] {e}")
        return 1


def cmd_youtube_accounts(args: argparse.Namespace) -> int:
    """List all connected YouTube accounts."""
    init_db()
    from post_youtube import get_all_token_paths
    tokens = get_all_token_paths()
    if not tokens:
        console.print("[yellow]No YouTube accounts authenticated yet.[/yellow]")
        return 0
    console.print(f"[bold green]Connected YouTube Accounts ({len(tokens)}):[/bold green]")
    for i, t in enumerate(tokens, 1):
        label = t.stem.replace("youtube_token", "").strip("_") or "primary (default)"
        console.print(f"  {i}. [bold cyan]{label}[/bold cyan] -> {t}")
    return 0


# ===== Live mode commands =====

def _detect_platform(url: str) -> tuple[str, str, str]:
    """Return (platform, channel_slug, full_url) for a user-supplied input.
    Accepts either a full URL or 'twitch:shroud' style shorthand."""
    if ":" in url and not url.startswith("http"):
        platform, slug = url.split(":", 1)
        platform = platform.strip().lower()
        slug = slug.strip().strip("/")
        # Strip a leading '@' on YouTube handles, then re-add it in the URL.
        if slug.startswith("@"):
            slug = slug[1:]
        if platform == "twitch":
            full = f"https://twitch.tv/{slug}"
        elif platform == "youtube":
            full = f"https://youtube.com/@{slug}/live"
        elif platform == "kick":
            full = f"https://kick.com/{slug}"
        elif platform == "trovo":
            full = f"https://trovo.live/{slug}"
        else:
            full = url
        return platform, slug, full

    # Try to parse as URL.
    from urllib.parse import urlparse
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").strip("/")

    if "twitch.tv" in host:
        slug = path.split("/")[0] if path else ""
        return "twitch", slug, f"https://twitch.tv/{slug}"
    if "youtube.com" in host or "youtu.be" in host:
        if path.startswith("@"):
            slug = path.split("/")[0][1:]
            return "youtube", slug, f"https://youtube.com/@{slug}/live"
        return "youtube", path, url
    if "kick.com" in host:
        slug = path.split("/")[0] if path else ""
        return "kick", slug, f"https://kick.com/{slug}"
    if "trovo.live" in host:
        slug = path.split("/")[0] if path else ""
        return "trovo", slug, f"https://trovo.live/{slug}"
    return "other", path, url


def cmd_live_add(args: argparse.Namespace) -> int:
    init_db()
    platform, slug, full_url = _detect_platform(args.channel)
    if not slug:
        console.print(f"[red]Could not parse channel from {args.channel!r}[/red]")
        return 1
    cid = add_channel(platform, slug, full_url, display_name=args.display_name or slug)
    console.print(f"[green]Added channel #{cid}[/green]: {platform}/{slug} -> {full_url}")
    console.print("Start the watcher with: python cli.py live watch")
    return 0


def cmd_live_list(args: argparse.Namespace) -> int:
    init_db()
    channels = list_channels(enabled_only=False)
    if not channels:
        console.print("[yellow]No channels yet. Add one with:[/yellow] python cli.py live add <url>")
        return 0
    t = Table(title="Watched channels")
    t.add_column("ID", justify="right")
    t.add_column("Platform")
    t.add_column("Channel")
    t.add_column("Display name")
    t.add_column("Enabled")
    t.add_column("URL", overflow="fold")
    for c in channels:
        t.add_row(str(c["id"]), c["platform"], c["channel"],
                  c.get("display_name") or "",
                  "yes" if c["enabled"] else "no", c["url"])
    console.print(t)

    # Also show active streams.
    streams = list_active_streams()
    if streams:
        t2 = Table(title="Active streams")
        t2.add_column("Stream ID", justify="right")
        t2.add_column("Channel")
        t2.add_column("Status")
        t2.add_column("Started")
        t2.add_column("Recording path", overflow="fold")
        for s in streams:
            t2.add_row(str(s["id"]), f"{s['platform']}/{s['channel']}",
                       s["status"], s["started_at"], s["recording_path"])
        console.print(t2)
    return 0


def cmd_live_remove(args: argparse.Namespace) -> int:
    init_db()
    remove_channel(args.channel_id)
    console.print(f"[green]Removed channel {args.channel_id}.[/green]")
    return 0


def cmd_live_enable(args: argparse.Namespace) -> int:
    init_db()
    set_channel_enabled(args.channel_id, True)
    console.print(f"[green]Enabled channel {args.channel_id}.[/green]")
    return 0


def cmd_live_disable(args: argparse.Namespace) -> int:
    init_db()
    set_channel_enabled(args.channel_id, False)
    console.print(f"[green]Disabled channel {args.channel_id}.[/green]")
    return 0


def cmd_live_watch(args: argparse.Namespace) -> int:
    """Run the watcher daemon in the foreground. launchd runs this in the
    background; use this for debugging."""
    init_db()
    ensure_tools_installed()
    console.print(f"[blue]Starting watcher. Polling every "
                  f"{CONFIG.live_poll_interval_seconds}s. Ctrl-C to stop.[/blue]")
    from watcher import Watcher
    try:
        Watcher().run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping...[/yellow]")
    return 0


def cmd_live_status(args: argparse.Namespace) -> int:
    """Show what the watcher is currently doing."""
    init_db()
    streams = list_active_streams()
    if not streams:
        console.print("[yellow]No active streams.[/yellow]")
        return 0
    for s in streams:
        console.print(f"[blue]Stream {s['id']}[/blue]: {s['platform']}/{s['channel']} "
                      f"({s['status']}, started {s['started_at']})")
        clips = list_live_clips_for_stream(s["id"])
        if clips:
            posted = sum(1 for c in clips if c["status"] == "posted")
            failed = sum(1 for c in clips if c["status"] == "failed")
            pending = sum(1 for c in clips if c["status"] in ("pending", "rendering"))
            console.print(f"  Clips picked: {len(clips)} (posted: [green]{posted}[/green], failed: [red]{failed}[/red], pending: [yellow]{pending}[/yellow])")
            # Show the most recent 5 clips
            for c in clips[-5:]:
                color = "green" if c["status"] == "posted" else ("red" if c["status"] == "failed" else "yellow")
                console.print(f"    [{c['start_seconds']:.0f}-{c['end_seconds']:.0f}s] "
                              f"{c.get('title', '')[:50]} ([{color}]{c['status']}[/{color}])")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """Generate a split-screen GTA 5 vs GTA 6 comparison short from a stream."""
    init_db()
    from compare_edit import render_comparison_clip, classify_action
    from live_curate import _resolve_creator_name, _load_transcript
    from db import get_stream

    stream_id = args.stream_id
    stream_info = get_stream(stream_id)
    if not stream_info:
        console.print(f"[red]Stream #{stream_id} not found in database.[/red]")
        return 1

    stream_path = Path(stream_info["recording_path"])
    if not stream_path.exists():
        console.print(f"[red]Recording not found at {stream_path}[/red]")
        return 1

    transcript_path = CONFIG.live_transcripts_dir / f"stream_{stream_id}_rolling.json"
    transcript = _load_transcript(transcript_path) if transcript_path.exists() else {}
    words = transcript.get("words", [])

    start = args.start if args.start is not None else (words[0]["start"] if words else 30.0)
    end = args.end if args.end is not None else min(start + 45.0, (words[-1]["end"] if words else start + 45.0))

    creator = _resolve_creator_name(stream_id)
    classification = classify_action(words, title=args.title or "")
    cat = args.category or classification["category"]

    out_name = f"compare_stream_{stream_id}_{int(start)}_{int(end)}.mp4"
    out_path = CONFIG.clips_dir / out_name

    console.print(f"[cyan]Rendering GTA 5 vs GTA 6 comparison edit for {creator}...[/cyan]")
    console.print(f"[yellow]Category:[/yellow] {cat} | [yellow]Time:[/yellow] [{start:.0f}s - {end:.0f}s]")

    out, dur = render_comparison_clip(
        gta6_source=stream_path,
        start=start,
        end=end,
        out_path=out_path,
        words=words,
        streamer_name=creator,
        custom_title=args.title or classification["title"],
    )

    console.print(f"[green]SUCCESS! Comparison video created:[/green] {out} ({dur:.1f}s)")
    return 0


def cmd_live_cleanup(args: argparse.Namespace) -> int:
    """Run the cleanup pass manually (launchd normally does this hourly)."""
    init_db()
    from cleanup import run_cleanup
    return run_cleanup()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="clips", description="Local free clip pipeline.")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="Add a video URL or local path to the queue.")
    a.add_argument("url")
    a.add_argument("--title", default=None)
    a.set_defaults(func=cmd_add)

    a = sub.add_parser("list", help="List all concepts and ready content.")
    a.add_argument("--limit", type=int, default=50)
    a.set_defaults(func=cmd_list)

    a = sub.add_parser("queue", help="List only Todo concepts.")
    a.add_argument("--limit", type=int, default=50)
    a.set_defaults(func=cmd_queue)

    a = sub.add_parser("run", help="Process queued concepts into clips.")
    a.add_argument("--limit", type=int, default=2)
    a.set_defaults(func=cmd_run)

    a = sub.add_parser("run-one", help="Process one specific concept by id.")
    a.add_argument("concept_id", type=int)
    a.set_defaults(func=cmd_run_one)

    a = sub.add_parser("post", help="Post one ready clip. Optionally specify content id.")
    a.add_argument("content_id", type=int, nargs="?", default=None)
    a.set_defaults(func=cmd_post)

    a = sub.add_parser("upload", help="Upload any video file directly to YouTube Shorts with multi-account failover.")
    a.add_argument("file_path", help="Path to the video file to upload.")
    a.add_argument("--title", default=None, help="Custom YouTube Short title.")
    a.add_argument("--caption", default=None, help="Custom caption/description.")
    a.add_argument("--account", default=None, help="Target specific YouTube account (e.g. 'channel2', 'primary').")
    a.set_defaults(func=cmd_upload)

    a = sub.add_parser("reset-stuck", help="Re-queue concepts stuck in 'processing'.")
    a.set_defaults(func=cmd_reset_stuck)

    a = sub.add_parser("youtube-auth", help="One-time interactive OAuth flow for YouTube Shorts.")
    a.add_argument("--account", default=None, help="Account label (e.g. 'channel2', 'backup'). Omit for default.")
    a.set_defaults(func=cmd_youtube_auth)

    a = sub.add_parser("youtube-accounts", help="List all authenticated YouTube channels/accounts.")
    a.set_defaults(func=cmd_youtube_accounts)

    # --- Live mode subcommands ---
    live = sub.add_parser("live", help="Live stream monitoring and clipping.")
    live_sub = live.add_subparsers(dest="live_cmd", required=True)

    a = live_sub.add_parser("add", help="Add a channel to watch.")
    a.add_argument("channel", help="Channel URL or 'twitch:shroud' / 'youtube:@channel' shorthand.")
    a.add_argument("--display-name", default=None)
    a.set_defaults(func=cmd_live_add)

    a = live_sub.add_parser("list", help="List watched channels and active streams.")
    a.set_defaults(func=cmd_live_list)

    a = live_sub.add_parser("remove", help="Stop watching a channel.")
    a.add_argument("channel_id", type=int)
    a.set_defaults(func=cmd_live_remove)

    a = live_sub.add_parser("enable", help="Re-enable a disabled channel.")
    a.add_argument("channel_id", type=int)
    a.set_defaults(func=cmd_live_enable)

    a = live_sub.add_parser("disable", help="Temporarily disable a channel without removing it.")
    a.add_argument("channel_id", type=int)
    a.set_defaults(func=cmd_live_disable)

    a = live_sub.add_parser("watch", help="Run the watcher daemon in the foreground.")
    a.set_defaults(func=cmd_live_watch)

    a = live_sub.add_parser("status", help="Show what the watcher is currently doing.")
    a.set_defaults(func=cmd_live_status)

    a = live_sub.add_parser("cleanup", help="Delete old source recordings manually.")
    a.set_defaults(func=cmd_live_cleanup)

    a = sub.add_parser("compare", help="Generate a GTA 5 vs GTA 6 split-screen comparison short.")
    a.add_argument("stream_id", type=int, help="Stream ID to extract GTA 6 streamer clip from.")
    a.add_argument("--start", type=float, default=None, help="Start time in seconds.")
    a.add_argument("--end", type=float, default=None, help="End time in seconds.")
    a.add_argument("--category", default=None, help="Comparison category (e.g. car_physics, police_chase, water_physics, graphics).")
    a.add_argument("--title", default=None, help="Custom hook title.")
    a.set_defaults(func=cmd_compare)

    a = sub.add_parser("doctor", help="Verify config and tools.")
    a.set_defaults(func=cmd_doctor)

    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=CONFIG.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
