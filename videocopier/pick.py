from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from videocopier.media import list_videos


class PickCancelled(Exception):
    pass


def _osascript(script: str) -> str:
    proc = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=600,
    )
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        if "User canceled" in err or "User cancelled" in err or proc.returncode == 1:
            raise PickCancelled()
        raise RuntimeError(err or "Folder picker failed")
    path = (proc.stdout or "").strip()
    if not path:
        raise PickCancelled()
    return path


def pick_folder() -> Path:
    if sys.platform == "darwin":
        script = (
            'tell application "System Events" to activate\n'
            'POSIX path of (choose folder with prompt "Select your raw footage folder")'
        )
        return Path(_osascript(script)).expanduser().resolve()
    from tkinter import Tk, filedialog

    root = Tk()
    root.withdraw()
    root.wm_attributes("-topmost", 1)
    chosen = filedialog.askdirectory(title="Select your raw footage folder")
    root.destroy()
    if not chosen:
        raise PickCancelled()
    return Path(chosen).expanduser().resolve()


def pick_file(prompt: str = "Select a video") -> Path:
    if sys.platform == "darwin":
        script = (
            'tell application "System Events" to activate\n'
            f'POSIX path of (choose file with prompt "{prompt}" of type '
            '{"public.movie", "public.mpeg-4", "com.apple.quicktime-movie", "mp4", "mov", "m4v", "mp3", "m4a", "wav", "aac"})'
        )
        return Path(_osascript(script)).expanduser().resolve()
    from tkinter import Tk, filedialog

    root = Tk()
    root.withdraw()
    root.wm_attributes("-topmost", 1)
    chosen = filedialog.askopenfilename(title=prompt)
    root.destroy()
    if not chosen:
        raise PickCancelled()
    return Path(chosen).expanduser().resolve()


def folder_info(path: Path) -> dict:
    videos = list_videos(path)
    return {
        "path": str(path),
        "videos": len(videos),
        "names": [p.name for p in videos[:12]],
    }
