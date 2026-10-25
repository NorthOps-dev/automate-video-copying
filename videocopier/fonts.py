from __future__ import annotations

import io
import zipfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = ROOT / "fonts"
TIKTOK_SANS = FONTS_DIR / "TikTokSans.ttf"
TIKTOK_SANS_XBOLD = FONTS_DIR / "TikTokSans-ExtraBold.ttf"

TIKTOK_FONT_URLS = [
    "https://github.com/google/fonts/raw/main/ofl/tiktoksans/TikTokSans%5Bopsz%2Cslnt%2Cwdth%2Cwght%5D.ttf",
    "https://github.com/google/fonts/raw/main/ofl/tiktoksans/static/TikTokSans_36pt-ExtraBold.ttf",
]


class FontChoice:
    def __init__(self, path: Path, ass_name: str, index: int = 0):
        self.path = path
        self.ass_name = ass_name
        self.index = index
        self.dir = path.parent


def _download(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NorthOps-Prophet/1.0"})
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = resp.read()
        if len(data) < 10_000 or data[:4] not in {b"\x00\x01\x00\x00", b"OTTO", b"true", b"wOFF"}:
            return False
        dest.write_bytes(data)
        return True
    except Exception:
        return False


def _download_from_release(dest: Path) -> bool:
    url = "https://github.com/tiktok/TikTokSans/releases/download/v4.000/TikTokSans-v4.000.zip"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NorthOps-Prophet/1.0"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            blob = io.BytesIO(resp.read())
        with zipfile.ZipFile(blob) as zf:
            prefer = [n for n in zf.namelist() if n.lower().endswith(".ttf") and "tiktoksans" in n.lower().replace(" ", "")]
            var = [n for n in prefer if "opsz" in n.lower() or "[" in n]
            pick = (var or prefer or [n for n in zf.namelist() if n.endswith(".ttf")])
            if not pick:
                return False
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(pick[0]))
            return dest.stat().st_size > 10_000
    except Exception:
        return False


def ensure_caption_font() -> FontChoice:
    """TikTok Sans — native TikTok caption face, ExtraBold instance."""
    for path in (TIKTOK_SANS, TIKTOK_SANS_XBOLD):
        if path.exists() and path.stat().st_size > 10_000:
            return FontChoice(path, "TikTok Sans")
    if _download(TIKTOK_FONT_URLS[0], TIKTOK_SANS):
        return FontChoice(TIKTOK_SANS, "TikTok Sans")
    if _download_from_release(TIKTOK_SANS):
        return FontChoice(TIKTOK_SANS, "TikTok Sans")
    for url in TIKTOK_FONT_URLS[1:]:
        if _download(url, TIKTOK_SANS_XBOLD):
            return FontChoice(TIKTOK_SANS_XBOLD, "TikTok Sans")
    raise FileNotFoundError(
        "Could not download TikTok Sans. Put the TTF at fonts/TikTokSans.ttf"
    )


def ensure_tiktok_font() -> FontChoice:
    return ensure_caption_font()
