from __future__ import annotations

import io
import zipfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = ROOT / "fonts"

# CapCut/TikTok "Classic" is Proxima Nova Semibold. We cannot bundle that
# commercial face, so on macOS we use Avenir Next Bold (closest system match)
# and fall back to OFL Montserrat Bold everywhere else.
AVENIR_NEXT = Path("/System/Library/Fonts/Avenir Next.ttc")
AVENIR_NEXT_BOLD_INDEX = 0  # ('Avenir Next', 'Bold')

MONTSERRAT_URLS = [
    "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Bold.ttf",
    "https://github.com/google/fonts/raw/main/ofl/montserrat/static/Montserrat-Bold.ttf",
]

TIKTOK_FONT_URLS = [
    "https://github.com/google/fonts/raw/main/ofl/tiktoksans/static/TikTokSans_36pt-ExtraBold.ttf",
    "https://github.com/tiktok/TikTokSans/raw/main/fonts/ttf/TikTokSans36pt-ExtraBold.ttf",
    "https://github.com/google/fonts/raw/main/ofl/tiktoksans/TikTokSans%5Bopsz%2Cslnt%2Cwdth%2Cwght%5D.ttf",
]

MAC_FALLBACKS = [
    Path("/System/Library/Fonts/Supplemental/Arial Black.ttf"),
    Path("/System/Library/Fonts/Supplemental/Impact.ttf"),
    Path("/Library/Fonts/Arial Bold.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
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
        req = urllib.request.Request(url, headers={"User-Agent": "VideoCopier/0.1"})
        with urllib.request.urlopen(req, timeout=30) as resp:
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
        req = urllib.request.Request(url, headers={"User-Agent": "VideoCopier/0.1"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            blob = io.BytesIO(resp.read())
        with zipfile.ZipFile(blob) as zf:
            for name in zf.namelist():
                if name.endswith("TikTokSans36pt-ExtraBold.ttf"):
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(zf.read(name))
                    return dest.stat().st_size > 10_000
    except Exception:
        return False
    return False


def ensure_caption_font() -> FontChoice:
    """Classic TikTok/CapCut caption face: Proxima-like Bold + thick outline."""
    if AVENIR_NEXT.exists():
        return FontChoice(AVENIR_NEXT, "Avenir Next", AVENIR_NEXT_BOLD_INDEX)

    montserrat = FONTS_DIR / "Montserrat-Bold.ttf"
    if montserrat.exists() and montserrat.stat().st_size > 10_000:
        return FontChoice(montserrat, "Montserrat Bold")
    for url in MONTSERRAT_URLS:
        if _download(url, montserrat):
            return FontChoice(montserrat, "Montserrat Bold")

    for bundled in (
        FONTS_DIR / "TikTokSans-ExtraBold.ttf",
        FONTS_DIR / "TikTokSans-Black.ttf",
        FONTS_DIR / "TikTokSans.ttf",
    ):
        if bundled.exists() and bundled.stat().st_size > 10_000:
            return FontChoice(bundled, "TikTok Sans ExtraBold")
    dest = FONTS_DIR / "TikTokSans-ExtraBold.ttf"
    for url in TIKTOK_FONT_URLS:
        if _download(url, dest):
            return FontChoice(dest, "TikTok Sans ExtraBold")
    if _download_from_release(dest):
        return FontChoice(dest, "TikTok Sans ExtraBold")
    for path in MAC_FALLBACKS:
        if path.exists():
            name = "Arial Black" if "Black" in path.name else path.stem
            if "Impact" in path.name:
                name = "Impact"
            elif "Bold" in path.name:
                name = "Arial"
            return FontChoice(path, name)
    raise FileNotFoundError(
        "No caption font found. Connect to the internet once so Montserrat Bold can download, "
        "or place a .ttf at fonts/Montserrat-Bold.ttf"
    )


def ensure_tiktok_font() -> FontChoice:
    return ensure_caption_font()
