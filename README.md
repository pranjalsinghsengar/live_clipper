# clips_pipeline — 100% free, local-Mac replacement for the Opus Clip + Buffer + Airtable n8n workflow

This project reproduces the behaviour of your paid n8n workflow entirely on
your Mac, with zero ongoing cost. It turns long videos into short vertical
clips with burned-in karaoke captions, then auto-posts them to Instagram
Reels and TikTok on a schedule. The AI curation step uses Google
Antigravity's SDK running Gemma 4 26B locally; the whole thing stays alive
across reboots via macOS launchd.

```
┌──────────────┐   yt-dlp    ┌─────────────┐  faster-  ┌──────────────┐
│ SQLite queue │ ──────────► │ downloaded  │  whisper  │  transcript  │
│  concepts     │             │  source.mp4 │ ────────► │  + word ts   │
└──────┬───────┘             └─────────────┘           └──────┬───────┘
       │                                                      │
       │                                                Antigravity SDK
       │                                                Gemma 4 26B (LiteRT)
       │                                                      ▼
       │                                              ┌────────────────┐
       │                                              │  clip specs    │
       │                                              │ (start/end/    │
       │                                              │  title/caption)│
       │                                              └───────┬────────┘
       │                                                      │
       │                                                 ffmpeg cut + crop
       │                                                 + ASS captions burn
       │                                                      ▼
       │                                              ┌────────────────┐
       │                                              │  vertical mp4  │
       └─────────────────────────────────────────────►│  in clips/     │
                                                      └───────┬────────┘
                                                              │
   launchd 3PM + 8PM jobs                                    / \
   pick one random Ready clip                            ┌─────┴─────┐
                                                         ▼           ▼
                                                Meta Graph API  TikTok API
                                                (Instagram Reel) (post)
```

---

## Table of contents

1. [What this replaces](#what-this-replaces)
2. [Prerequisites](#prerequisites)
3. [Setup](#setup)
4. [Day-to-day usage](#day-to-day-usage)
5. [Schedule (launchd)](#schedule-launchd)
6. [Antigravity + Gemma 4 local model](#antigravity--gemma-4-local-model)
7. [Social API setup](#social-api-setup)
8. [Live mode (Twitch, YouTube Live, Kick, Trovo)](#live-mode)
9. [Troubleshooting](#troubleshooting)
10. [Cost comparison vs the paid n8n workflow](#cost-comparison)

---

## What this replaces

| Paid node in your n8n workflow | Free local replacement |
|---|---|
| Opus Clip HTTP node (clip curation) | `curate.py` — Antigravity SDK + Gemma 4 26B via LiteRT, with a heuristic fallback |
| Airtable Concepts + Content tables | `db.py` — local SQLite at `~/clips_pipeline_data/state.db` |
| Cloudinary (file hosting for social APIs) | Local HTTP server (or `PUBLIC_VIDEO_BASE_URL` via Cloudflare Tunnel) |
| Buffer (Instagram + TikTok) | `post_instagram.py` (Meta Graph API) + `post_tiktok.py` (TikTok Content Posting API) + `post_youtube.py` (YouTube Data API v3, OAuth 2.0) |
| n8n schedule triggers | macOS launchd plists (`launchd/install.sh`) |
| n8n webhook wait | Not needed — pipeline runs synchronously, no webhook |
| `Wait 1 hour` node | Not needed — local pipeline waits inline |

---

## Prerequisites

- **macOS** (Apple Silicon recommended; Intel works but slower).
- **24GB+ unified memory** if you want to use the Antigravity + Gemma 4 path
  for clip curation. If you have 16GB or less, leave
  `ANTIGRAVITY_MODEL_PATH` blank — the curator falls back to a pure-Python
  heuristic that still produces decent clips, just without AI judgement.
- **Homebrew** for installing the system tools.
- A **Meta Business account** for Instagram, and a **TikTok developer app**
  with the Content Posting API enabled. (Skip these if you only want clips
  locally — both platforms are independent.)

---

## Setup

### 1. Install system tools

```bash
brew install yt-dlp ffmpeg
brew install python@3.12
```

### 2. Move this project somewhere permanent

```bash
# e.g.
mv clips_pipeline ~/clips_pipeline
cd ~/clips_pipeline
```

### 3. Create a virtualenv and install Python deps

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
$EDITOR .env
```

At minimum, fill in:
- `ANTIGRAVITY_MODEL_PATH` (see [Antigravity section](#antigravity--gemma-4-local-model))
  — or leave blank to use the heuristic curator.
- `IG_ACCESS_TOKEN`, `IG_USER_ID` if you want Instagram auto-posting.
- `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_ACCESS_TOKEN`,
  `TIKTOK_OPEN_ID` if you want TikTok auto-posting.

### 5. Verify the setup

```bash
python cli.py doctor
```

This checks that `yt-dlp`, `ffmpeg`, `ffprobe`, and `faster-whisper` are
installed, that Antigravity is reachable (or that you've accepted the
heuristic fallback), and that the social APIs are configured.

### 6. Install the launchd schedule (optional, but recommended)

```bash
bash launchd/install.sh
```

This creates three launchd jobs in `~/Library/LaunchAgents/`:

| Job | Schedule (local time) | Action |
|---|---|---|
| `com.<you>.clips.clip.weekly` | Sunday 03:00 | `python cli.py run --limit 2` |
| `com.<you>.clips.post.3pm` | Daily 15:00 | `python cli.py post` |
| `com.<you>.clips.post.8pm` | Daily 20:00 | `python cli.py post` |

Edit `launchd/install.sh` to change times.

---

## Day-to-day usage

### Add a video to the queue

```bash
# YouTube URL (yt-dlp handles Vimeo, Twitch, etc. too)
python cli.py add "https://www.youtube.com/watch?v=..."

# Local file
python cli.py add /Users/me/Movies/talk.mp4 --title "My conference talk"
```

### See the queue

```bash
python cli.py list
python cli.py queue
```

### Process queued concepts manually (don't wait for Sunday)

```bash
python cli.py run            # processes the 2 oldest Todo concepts
python cli.py run --limit 5  # processes 5
python cli.py run-one 42     # processes concept id 42 specifically
```

### Post a clip manually (don't wait for 3PM/8PM)

```bash
python cli.py post       # picks one random Ready-to-Post clip
python cli.py post 12    # posts content row id 12 specifically
```

### Recover from a crash

If a run was killed mid-processing, the concept is left in `processing`
status. Reset it with:

```bash
python cli.py reset-stuck
```

### File layout

```
~/clips_pipeline_data/
├── state.db                # SQLite (Concepts + Content tables)
├── downloads/              # source videos
├── clips/                  # finished vertical mp4 + .ass subtitle files
├── transcripts/            # Whisper transcripts (word-level JSON)
└── logs/                   # launchd stdout/stderr logs
```

---

## Schedule (launchd)

### Change the schedule

Edit `launchd/install.sh` — the three `gen_plist` calls at the bottom — and
re-run `bash launchd/install.sh`. The old plists are overwritten and
reloaded.

### Wake the Mac from sleep

launchd jobs do not run while the Mac is asleep. If yours is asleep at
3AM / 3PM / 8PM, schedule wake-ups:

```bash
sudo pmset repeat wakeorpoweron MTWRFSU 02:55:00
sudo pmset repeat wakeorpoweron MTWRFSU 14:55:00
sudo pmset repeat wakeorpoweron MTWRFSU 19:55:00
```

(`MTWRFSU` = Mon Tue Wed Thu Fri Sat Sun — every day.)

Alternatively, in **System Settings → Battery → Schedule…** set the wake
times via the GUI.

### Inspect / stop

```bash
launchctl list | grep clips           # see loaded jobs + last exit code
tail -f ~/clips_pipeline/logs/com.*.clips.clip.weekly.out.log
bash launchd/uninstall.sh             # stop + remove all three jobs
```

---

## Antigravity + Gemma 4 local model

The clip-curation step is the only part of the pipeline that benefits from
a frontier LLM. We use Google Antigravity's Python SDK running Gemma 4 26B
A4B locally via LiteRT. This is **100% offline, free, no API key**.

### One-time setup

Follow the official docs at <https://antigravity.google/docs/sdk/local-models>
but the short version:

```bash
# Inside your venv
pip install google-antigravity litert-lm
pip install certifi
export SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())")

# Import the Gemma 4 26B A4B checkpoint (~16.8 GB download).
litert-lm import \
  --from-huggingface-repo=litert-community/gemma-4-26B-A4B-it-litert-lm \
  gemma-4-26B-A4B-it-gpu.litertlm \
  gemma4-26b
```

Then point `.env` at the model:

```
ANTIGRAVITY_MODEL_PATH=~/.litert-lm/models/gemma4-26b/model.litertlm
ANTIGRAVITY_BACKEND=gpu
```

### How the agent is wired in

`curate.py` calls Antigravity SDK directly via the Python API. The agent's
persona and skill live in:

- `antigravity/agents.md` — the curator agent definition
- `antigravity/skills/curate_clips.md` — the step-by-step skill

These files are read by Antigravity when running. You can edit them to
change the curator's behaviour (different hook style, different caption
tone, different languages, etc.).

### Heuristic fallback

If `ANTIGRAVITY_MODEL_PATH` is blank or the file doesn't exist, `curate.py`
skips Antigravity entirely and uses a pure-Python heuristic: it slices the
transcript into ~45-second windows of contiguous speech, dropping silence.
This is fast (no model load) but has no taste — it just produces uniform
clips. Good enough to keep the pipeline running while you wait for the
Gemma 4 download.

---

## Social API setup

### Instagram (Meta Graph API)

1. Go to <https://developers.facebook.com/> and create a Meta app.
2. Add the **Instagram Graph API** product.
3. Link it to an Instagram Business account (a Creator account is not
   enough).
4. Generate a long-lived access token (60 days; refresh quarterly).
5. Get your IG user ID (numeric, not your handle).
6. Fill in `.env`:
   ```
   IG_ACCESS_TOKEN=...
   IG_USER_ID=...
   ```

For `video_url` to be reachable by Meta's servers, you have two options:

- **Public base URL** (recommended): run any static file server over
  Cloudflare Tunnel (free, no signup needed for a quick tunnel):

  ```bash
  brew install cloudflared
  cd ~/clips_pipeline_data/clips
  python3 -m http.server 8000 &
  cloudflared tunnel --url http://localhost:8000
  # copy the https://*.trycloudflare.com URL
  ```

  Put it in `.env`:
  ```
  PUBLIC_VIDEO_BASE_URL=https://random-words.trycloudflare.com
  ```

- **No public URL**: leave `PUBLIC_VIDEO_BASE_URL` blank. The pipeline
  spins up a tiny `http.server` on a random port and serves `clips/` for
  the duration of each upload. This works only on home networks with a
  public IP (no CGNAT). Meta's servers will fetch from your public IP.

### TikTok (Content Posting API)

TikTok lets us upload the file directly — no public URL needed.

1. Go to <https://developers.tiktok.com/> and register an app.
2. Enable the scopes: `video.upload`, `video.publish`.
3. Walk through the OAuth flow to get an access token for your account.
4. Get your open ID.
5. Fill in `.env`:
   ```
   TIKTOK_CLIENT_KEY=...
   TIKTOK_CLIENT_SECRET=...
   TIKTOK_ACCESS_TOKEN=...
   TIKTOK_OPEN_ID=...
   ```

TikTok access tokens expire; refresh per their docs.

### YouTube Shorts (Data API v3, OAuth 2.0)

YouTube uses OAuth 2.0 user consent (not a static API key) because uploading to
a channel is a user action. The OAuth token is cached after a one-time
interactive auth, then refreshed automatically.

**Free quota:** 10,000 units/day. A video upload costs ~1600 units, so you can
upload ~6 videos/day for free — plenty for our 2/day pipeline.

**One-time setup:**

1. Go to <https://console.cloud.google.com/> and create (or pick) a project.
2. **APIs & Services → Library →** search "YouTube Data API v3" → **Enable**.
3. **APIs & Services → OAuth consent screen:**
   - User type: **External** (or Internal if you have a Google Workspace).
   - Add yourself as a Test User.
   - Add scope: `https://www.googleapis.com/auth/youtube.upload`.
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID:**
   - Application type: **Desktop app** (important — not Web app).
   - Name: anything (e.g. "clips_pipeline").
   - Download the JSON.
5. Move the downloaded JSON to your pipeline data dir, renaming it:
   ```bash
   mv ~/Downloads/client_secret_*.json ~/clips_pipeline_data/youtube_client_secret.json
   ```
6. Run the one-time interactive auth:
   ```bash
   python cli.py youtube-auth
   ```
   A browser opens, you log in with the Google account tied to your YouTube
   channel, click Allow. The token is cached at
   `~/clips_pipeline_data/youtube_token.json`. Subsequent runs (including
   the launchd jobs) refresh it silently — no browser, no prompts.

**To disable YouTube** (e.g. while you set it up), set `YOUTUBE_ENABLED=0`
in `.env`. The pipeline then skips YouTube and posts only to IG/TikTok.

**Shorts classification:** YouTube auto-classifies a video as a Short when
it's vertical (9:16 or taller) and ≤60s — both guaranteed by `clip.py`. We
also append `#shorts` to the description as a belt-and-braces signal.

---

## Live mode

The pipeline also handles **live streams**. It watches a list of channels
(Twitch, YouTube Live, Kick, Trovo), starts recording the moment a stream
goes live, transcribes the audio in near-real-time, asks Antigravity every
5 minutes to pick the most shareable moments of the last 10 minutes, and
posts those clips immediately — not on the 3PM/8PM schedule.

When the stream ends, the pipeline runs the full (non-live) clip pipeline
on the entire recording to catch anything the live loop's 10-min window
missed. 24h after the stream ends, the source recording is deleted
automatically (but the rendered clips and posts stay).

```
┌─────────────┐  every 2 min   ┌──────────────┐
│  Watcher    │ ────────────► │ is_live(url)? │ ─── no ──► sleep
│  daemon     │               └──────┬───────┘
└─────────────┘                      │ yes
                                     ▼
                          ┌─────────────────────┐
                          │ LivePipeline thread │  (one per stream)
                          └──────────┬──────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                       ▼                      ▼
        streamlink           incremental Whisper        Antigravity
        records to disk      on rolling 60s windows     every 5 min on
        (one mp4 per stream)  updates transcript.json   last 10 min
              │                       │                      │
              │                       │                      ▼
              │                       │              new clip suggestions
              │                       │              (deduped vs existing)
              │                       │                      │
              │                       ▼                      ▼
              │                  ffmpeg cut + crop + burn ASS captions
              │                                       │
              │                                       ▼
              │                              post to IG + TikTok + YouTube
              │                              (immediate, no launchd wait)
              │
              ▼  stream ends
        run existing pipeline on full recording → catches anything missed
              │
              ▼  +24h
        cleanup.py deletes the source mp4
```

### Prerequisites for live mode

- `streamlink` CLI: `brew install streamlink`
- Disk space: ~2GB/hour at the default `720p60` quality. An 8-hour stream
  is ~16GB.
- macOS must stay awake while the watcher runs. Either:
  - `sudo pmset -a disablesleep 1` (always on), or
  - Schedule periodic wake-ups every few minutes so the watcher catches
    the start of streams.

### Setup

1. Add channels to watch:
   ```bash
   python cli.py live add twitch:shroud
   python cli.py live add "https://youtube.com/@MrBeast"
   python cli.py live add kick:xqc
   python cli.py live add trovo:somechannel
   ```
   Shorthand `platform:slug` works for any platform. Full URLs are also
   accepted.

2. List what's being watched:
   ```bash
   python cli.py live list
   ```

3. Install the always-on launchd jobs (run the same installer as before —
   it now creates 5 jobs instead of 3):
   ```bash
   bash launchd/install.sh
   ```
   New jobs:
   - `com.<you>.clips.watcher` — always-on daemon (`KeepAlive=true`)
   - `com.<you>.clips.cleanup` — runs hourly at :17

4. Watch the logs:
   ```bash
   tail -f ~/clips_pipeline_data/logs/com.*.clips.watcher.out.log
   ```

5. See what's recording right now:
   ```bash
   python cli.py live status
   ```

### How real-time is "real-time"?

Per stream, the latency budget is roughly:

| Step | Time |
|---|---|
| Whisper transcribes 60s window | 10-15s on M2 Pro (`small` model) |
| Antigravity picks clip from last 10 min | 30-60s (Gemma 4 26B inference) |
| ffmpeg cut + crop + burn ASS | 20-30s for a 45s clip |
| Instagram Graph API upload | 30-60s (Meta fetches the file) |
| TikTok upload | 1-5 min (chunked PUT) |
| YouTube upload | 1-3 min (resumable) |

Total: **3-7 minutes** from a moment happening on stream to all three
platforms posted. Lower `LIVE_TRANSCRIBE_WINDOW_SECONDS` for faster
turnaround at the cost of more CPU.

### Resource usage notes

- One Whisper model is loaded and shared across all streams. Default is the
  `small` model (~3GB RAM). Override with `WHISPER_MODEL=medium` for better
  accuracy at the cost of ~2x slower transcription.
- One Antigravity Agent is loaded and shared across all streams (Gemma 4
  26B is ~16GB in memory). If `ANTIGRAVITY_MODEL_PATH` is blank, the live
  curator falls back to a heuristic that picks the densest speech window —
  no LLM call, no model load.
- Each parallel stream uses one streamlink subprocess (a few hundred MB)
  plus one ffmpeg subprocess during clip rendering.

If you watch many channels and your Mac is OOM'ing, set
`LIVE_MAX_PARALLEL=3` (or whatever fits your RAM) to cap concurrent
recordings. Channels that go live while you're at the cap are skipped —
the next poll cycle catches them if a slot freed up.

### Live-mode DB schema

Three new tables (see `db.py`):

- `channels` — the channels you watch
- `streams` — one row per recording session (status: recording → done)
- `live_clips` — clips picked during the live stream, with status
  pending → rendering → posted

A live clip also gets a row in the existing `content` table after it's
rendered and posted, so it shows up in `python cli.py list` like any other
clip.

### Manual control

```bash
python cli.py live disable 2     # stop watching channel 2 (keep row)
python cli.py live enable 2
python cli.py live remove 2      # delete channel 2 entirely
python cli.py live cleanup       # run cleanup pass manually
python cli.py live watch         # run watcher in foreground (debug)
```

---

## Troubleshooting

### `python cli.py doctor` says "Missing CLI: ffmpeg"

```bash
brew install ffmpeg
```

### `python cli.py doctor` says "Missing CLI: streamlink"

```bash
brew install streamlink
```

Needed only for live mode. If you never use live mode, ignore the warning.

### Whisper is slow

Try a smaller model. `WHISPER_MODEL=small python cli.py run` runs about 3×
faster than `medium` at a noticeable accuracy hit.

### Antigravity fails to load the model

- Confirm the file exists: `ls -lh ~/.litert-lm/models/gemma4-26b/model.litertlm`
- The first call to `Agent()` is slow (loads ~17GB into memory). Subsequent
  calls reuse the loaded model only if you keep the Python process alive —
  our pipeline calls Antigravity once per concept, so each call pays the
  load cost. Acceptable for a weekly run.
- If you don't have 24GB RAM, leave `ANTIGRAVITY_MODEL_PATH` blank. The
  heuristic curator is fine for most content.

### Instagram container stuck at `IN_PROGRESS`

Meta's fetch can take 1-2 minutes for large files. Our timeout is 5 minutes.
If you see timeouts, set `PUBLIC_VIDEO_BASE_URL` to a real public URL so
Meta doesn't have to deal with your home router.

### launchd job doesn't fire

- `launchctl list | grep clips` — check the job is loaded.
- Check `~/clips_pipeline/logs/*.err.log`.
- The `PATH` inside the plist is set to `/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin`. If you installed Python or yt-dlp somewhere else, edit the plist.
- The Mac was probably asleep. Schedule a wake-up with `pmset` (above).

### A video got stuck in `processing` status

```bash
python cli.py reset-stuck
```

### YouTube upload fails with "OAuth token missing or invalid"

The cached OAuth token has been deleted or revoked. Re-run the one-time auth:

```bash
python cli.py youtube-auth
```

If the client secret is also missing, redownload it from the Google Cloud
Console and place it at `~/clips_pipeline_data/youtube_client_secret.json`
first.

### YouTube quota exceeded

Each upload costs ~1600 quota units; the free daily quota is 10,000. If you
hit the limit, uploads will fail until midnight Pacific Time. The pipeline
records the error in `platform_state.youtube.error` and marks the clip
"posted" anyway (so it won't retry the same clip). To retry, set the
content row back to `ready`:

```sql
UPDATE content SET status='ready' WHERE id=12;
```

### Watcher didn't catch a stream

- The Mac was asleep. Either keep it awake (`pmset -a disablesleep 1`) or
  schedule frequent wake-ups.
- Check the watcher log: `tail -200 ~/clips_pipeline_data/logs/com.*.clips.watcher.out.log`
- streamlink's `is_live` check occasionally fails for Twitch channels that
  just went live — the API lags by 30-60s. The next poll cycle catches it.
- For YouTube Live channels, `https://youtube.com/@channel/live` only
  works if the channel is currently live and has the live badge. If a
  streamer premieres a video instead, that won't be detected.

### Watcher crashed and won't restart

launchd's `KeepAlive=true` should auto-restart it. If it doesn't:

```bash
launchctl list | grep watcher
# If the exit code is non-zero, check the err.log:
tail -200 ~/clips_pipeline_data/logs/com.*.clips.watcher.err.log
# Manually restart:
launchctl kickstart -k gui/$(id -u)/com.$(whoami).clips.watcher
```

A stale PID file at `~/clips_pipeline_data/watcher.pid` will block startup.
Delete it if the watcher is definitely not running.

---

## Cost comparison

| Component | Paid workflow | This pipeline |
|---|---|---|
| Workflow runner | n8n Cloud ($20/mo) or self-host n8n (free, your time) | macOS launchd (free, built in) |
| Clip curation | Opus Clip ($15-79/mo) | Antigravity SDK + Gemma 4 (free, local) |
| Database | Airtable ($10/mo for >1000 records) | SQLite (free) |
| File hosting | Cloudinary ($89/mo pro) | Local file server or Cloudflare Tunnel (free) |
| Social scheduling | Buffer ($6-12/mo per channel) | Meta Graph API + TikTok API (free) |
| **Monthly total** | **$40-200+** | **$0** |

The only ongoing cost is electricity to run your Mac.

---

## License

This project's source is yours to do with as you please. Its dependencies
retain their own licenses (see `requirements.txt` for the SPDX identifiers).
