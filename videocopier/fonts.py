from __future__ import annotations

import io
import zipfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = ROOT / "fonts"
MONTSERRAT = FONTS_DIR / "Montserrat-SemiBold.ttf"
TIKTOK_SANS = FONTS_DIR / "TikTokSans.ttf"
AVENIR_NEXT = Path("/System/Library/Fonts/Avenir Next.ttc")
# Medium in Apple's Avenir Next.ttc — fill is thin; the outline makes Classic.
# (Demi Bold + thick stroke reads as ExtraBold. Original cards are not that.)
AVENIR_CLASSIC_INDEX = 5


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
    """Classic TikTok card face: Semibold geometric, not ExtraBold blobs."""
    if AVENIR_NEXT.exists():
        return FontChoice(AVENIR_NEXT, "Avenir Next", index=AVENIR_CLASSIC_INDEX)
    if MONTSERRAT.exists() and MONTSERRAT.stat().st_size > 10_000:
        return FontChoice(MONTSERRAT, "Montserrat")
    if TIKTOK_SANS.exists() and TIKTOK_SANS.stat().st_size > 10_000:
        return FontChoice(TIKTOK_SANS, "TikTok Sans")
    if _download_from_release(TIKTOK_SANS):
        return FontChoice(TIKTOK_SANS, "TikTok Sans")
    raise FileNotFoundError("Need Avenir Next, fonts/Montserrat-SemiBold.ttf, or TikTok Sans.")


def ensure_tiktok_font() -> FontChoice:
    return ensure_caption_font()
