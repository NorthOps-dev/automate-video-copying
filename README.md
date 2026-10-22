# NorthOps Prophet

Internal NorthOps software. Drop in a viral reference and a folder of raw footage — Prophet copies the edit (pacing, shot order, Classic TikTok captions) using **only your clips**.

It copies the **edit**, not the pixels, and not the original song. Lay in a track you have rights to; Prophet still reads the reference beat/energy.

Keep this repository **private**. Sign-in is required for the web app.

## Sign in

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) and use:

- **Email:** `admin@northops.com`
- **Password:** `northops`

Override with `NORTHOPS_EMAIL`, `NORTHOPS_PASSWORD`, and `NORTHOPS_SECRET` if you need to.

## Run it

You need [FFmpeg](https://ffmpeg.org/) (`brew install ffmpeg`) and Python 3.11+.

```bash
cd VideoCopier
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv sync
uv run python -m videocopier
```

CLI (no sign-in):

```bash
uv run python -m videocopier run \
  --reference /path/to/viral.mp4 \
  --footage /path/to/raw-folder \
  --out ./output.mp4
```

`--reference` can also be a TikTok / YouTube / Instagram URL or a Google Drive file link.

## Push to GitHub

This repo is meant to stay private.

```bash
gh auth login
gh repo create NorthOps-Prophet --private --source=. --remote=origin --push
```

## Can it reach Google Drive?

The app can, in three ways:

1. **Local path** — Google Drive for Desktop folder path (usually under `~/Library/CloudStorage/GoogleDrive-…/My Drive/…`).
2. **Public link** — an “anyone with the link” Drive file or folder URL. Downloaded with `gdown`, no Google login.
3. **Private Drive** — put a Google Cloud OAuth `client_secret.json` in `~/.videocopier/` (Drive **read-only** scope) and click **Connect Google Drive**.

## Captions

Every export burns **Classic TikTok captions**: Proxima-like Bold (Avenir Next Bold on macOS, Montserrat Bold otherwise), white fill, thick black outline.

- **Auto** — caption what your footage actually says; if the clips are silent B-roll, use the reference script instead.
- **Reference** — always the viral on-screen text, timed like the original.
- **Footage** — always your speech.

## What it will not do

- Mux the viral video’s audio onto your export by default (that’s their recording).
- Invent shots you did not film. Missing matches become black **FILM THIS** slates plus a shot list.

## Output

- `output.mp4` — 1080×1920, captions on
- `output.fcpxml` — timeline for Final Cut / Resolve
- `cutlist.json` — every slot, score, and source in/out
