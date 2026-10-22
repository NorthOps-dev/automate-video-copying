from __future__ import annotations

import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

from videocopier.drive import (
    DriveError,
    download_drive_file,
    download_drive_folder,
    drive_connected,
    extract_drive_id,
    is_drive_ref,
    try_public_download,
)
from videocopier.media import VIDEO_EXTS, list_videos

URL_RE = re.compile(r"^https?://", re.I)


def _yt_dlp_download(url: str, dest_dir: Path) -> Path:
    from yt_dlp import YoutubeDL

    dest_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "outtmpl": str(dest_dir / "reference.%(ext)s"),
        "format": "mp4/best[ext=mp4]/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
    path = Path(filename)
    if path.exists():
        return path
    found = list(dest_dir.glob("reference.*"))
    if found:
        return found[0]
    raise FileNotFoundError(f"Download finished but no file landed in {dest_dir}")


def resolve_reference(spec: str, work: Path, progress=lambda m: None) -> Path:
    text = spec.strip().strip('"')
    local = Path(text).expanduser()
    if local.exists() and local.is_file():
        return local.resolve()

    dest = work / "reference_src"
    dest.mkdir(parents=True, exist_ok=True)

    if is_drive_ref(text) or extract_drive_id(text):
        progress("Fetching reference from Google Drive…")
        kind_id = extract_drive_id(text)
        if drive_connected() and kind_id:
            kind, did = kind_id
            if kind == "folder":
                raise DriveError("Reference must be a single video file, not a Drive folder.")
            return download_drive_file(did, dest)
        path = try_public_download(text, dest)
        if path.is_dir():
            vids = list_videos(path)
            if not vids:
                raise DriveError("That Drive folder has no video files.")
            return vids[0]
        return path

    if URL_RE.match(text):
        progress("Downloading reference video…")
        parsed = urlparse(text)
        if parsed.path.lower().endswith(tuple(VIDEO_EXTS)):
            return _yt_dlp_download(text, dest)
        return _yt_dlp_download(text, dest)

    raise FileNotFoundError(
        f"Cannot find reference video: {spec}. Use a local path, TikTok/YouTube URL, or Google Drive link."
    )


def resolve_footage(spec: str, work: Path, progress=lambda m: None) -> Path:
    text = spec.strip().strip('"')
    local = Path(text).expanduser()
    if local.exists():
        return local.resolve()

    dest = work / "footage_src"
    dest.mkdir(parents=True, exist_ok=True)

    if is_drive_ref(text) or extract_drive_id(text):
        progress("Fetching footage folder from Google Drive…")
        kind_id = extract_drive_id(text)
        if drive_connected() and kind_id:
            kind, did = kind_id
            if kind == "file":
                download_drive_file(did, dest)
                return dest
            return download_drive_folder(did, dest, progress=progress)
        return try_public_download(text, dest)

    if URL_RE.match(text):
        progress("Downloading footage URL…")
        _yt_dlp_download(text, dest)
        return dest

    drive_hint = Path.home() / "Library" / "CloudStorage"
    raise FileNotFoundError(
        f"Cannot find footage folder: {spec}. Use a local directory"
        + (f" (Google Drive Desktop lives under {drive_hint})" if drive_hint.exists() else "")
        + ", or paste a Google Drive folder link."
    )


def copy_if_uploaded(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest
