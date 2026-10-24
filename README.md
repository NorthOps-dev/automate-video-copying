# NorthOps Prophet

Internal NorthOps software. Remake an **approved TikTok format** for a **named client**.

Prophet does not paste the viral’s words onto leftover clips. It:

1. Loads the client from the Board and a fillable brief (`clients/*.json`)
2. Uses that slot’s remake script (`scriptLines.brand` / `clientScript`)
3. Copies the approved cut’s pacing and shot order
4. Spreads the client’s **good takes** across the format
5. Burns Classic TikTok captions **inside** the 9:16 frame

It copies the **edit**, not the pixels, and not the original song.

Keep this repository **private**. Sign-in is required for the web app.

## How you use it

1. **Client** — pick who this is for. Fill or correct the brief (voice, CTA, never-say). MeloMelo is already seeded.
2. **Approved format** — pick the Board design. Prophet shows the remake script, not the viral OCR.
3. **Footage** — add the client’s talking-heads and B-roll. Command-click several files.
4. **Remake** — export 1080×1920 with client captions.

## Board

Prophet reads approved slots from `https://board-production-bd79.up.railway.app` with the same admin login. Override with `NORTHOPS_BOARD_URL`.

## Client knowledge

Briefs live in `clients/{clientId}.json`. Edit them in the app or in the file. Fields: one-liner, location, what they do, voice, CTA, avoid.

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

CLI:

```bash
uv run python -m videocopier run \
  --reference board:SLOT_ID \
  --footage /path/to/raw-folder \
  --captions client \
  --out ./output.mp4
```

## Captions

Classic TikTok look: Avenir Next Bold on macOS (Montserrat Bold otherwise), white fill, thick black outline, wrapped to stay inside 1080×1920.

- **Client** (default) — Board remake script + brief
- **Reference** — viral on-screen text (almost never what you want)
- **Footage** — only what is said in these clips

## What it will not do

- Mux the viral video’s audio onto your export by default
- Invent shots you did not film. Missing matches become black **FILM THIS** slates

## Output

- `output.mp4` — 1080×1920, captions on
- `output.fcpxml` — timeline for Final Cut / Resolve
