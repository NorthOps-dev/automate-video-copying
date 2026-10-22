from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".3gp", ".mts", ".m4p"}


class MediaError(RuntimeError):
    pass


def ffmpeg_bin() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise MediaError("ffmpeg is not installed. Try: brew install ffmpeg")
    return path


def ffprobe_bin() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise MediaError("ffprobe is not installed. Try: brew install ffmpeg")
    return path


def run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-2000:]
        raise MediaError(f"Command failed ({proc.returncode}): {' '.join(cmd[:6])}…\n{tail}")
    return proc


def probe(path: Path) -> dict:
    proc = run(
        [
            ffprobe_bin(),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    return json.loads(proc.stdout)


def video_info(path: Path) -> dict:
    data = probe(path)
    stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not stream:
        raise MediaError(f"No video stream in {path}")
    fps_raw = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "30/1"
    num, den = (fps_raw.split("/") + ["1"])[:2]
    fps = float(num) / max(float(den), 1.0)
    duration = float(stream.get("duration") or data.get("format", {}).get("duration") or 0)
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps if fps > 0 else 30.0,
        "has_audio": audio,
    }


def has_audio(path: Path) -> bool:
    return video_info(path)["has_audio"]


def list_videos(folder: Path, recursive: bool = True) -> list[Path]:
    if folder.is_file() and folder.suffix.lower() in VIDEO_EXTS:
        return [folder]
    if not folder.is_dir():
        return []
    iterator = folder.rglob("*") if recursive else folder.glob("*")
    files = [p for p in iterator if p.is_file() and p.suffix.lower() in VIDEO_EXTS]
    files.sort()
    return files


def detect_cuts_by_diff(path: Path, duration: float, fps: float = 10.0) -> list[float]:
    frames = sample_gray_frames(path, 0.0, duration, fps=fps, width=160)
    if len(frames) < 4:
        return [0.0]
    diffs = np.abs(frames[1:].astype(np.float32) - frames[:-1].astype(np.float32)).mean(axis=(1, 2))
    med = float(np.median(diffs))
    mad = float(np.median(np.abs(diffs - med))) + 1e-6
    thresh = max(med + 4.5 * mad, 11.0)
    cuts = [0.0]
    for i, d in enumerate(diffs, start=1):
        t = i / fps
        if d > thresh and (t - cuts[-1]) >= 0.28:
            cuts.append(round(t, 3))
    return cuts


def detect_cuts(path: Path, work: Path, threshold: float = 0.22) -> list[float]:
    """Return timestamps (seconds) where a hard cut occurs, plus 0."""
    meta_file = work / "scene_meta.txt"
    vf = f"select='gt(scene,{threshold})',metadata=print:file={meta_file.as_posix()}"
    run(
        [
            ffmpeg_bin(),
            "-hide_banner",
            "-i",
            str(path),
            "-vf",
            vf,
            "-an",
            "-f",
            "null",
            "-",
        ]
    )
    cuts = [0.0]
    if meta_file.exists():
        pts = None
        for line in meta_file.read_text(errors="ignore").splitlines():
            line = line.strip()
            if "pts_time:" in line:
                try:
                    pts = float(line.split("pts_time:")[-1].split()[0])
                except ValueError:
                    pts = None
            if line.startswith("lavfi.scene_score=") and pts is not None:
                cuts.append(pts)
                pts = None
    duration = video_info(path)["duration"]
    cuts += detect_cuts_by_diff(path, duration)
    cuts = sorted({round(c, 3) for c in cuts if c >= 0})
    return cuts


def shot_bounds(cuts: list[float], duration: float, min_len: float = 0.35) -> list[tuple[float, float]]:
    points = list(cuts)
    if not points or points[0] != 0:
        points = [0.0] + points
    if points[-1] < duration - 0.05:
        points.append(duration)
    else:
        points[-1] = duration
    raw: list[tuple[float, float]] = []
    for a, b in zip(points, points[1:]):
        if b - a >= 0.05:
            raw.append((a, b))
    if not raw:
        return [(0.0, duration)]
    merged: list[tuple[float, float]] = [raw[0]]
    for start, end in raw[1:]:
        prev_s, prev_e = merged[-1]
        if (prev_e - prev_s) < min_len:
            merged[-1] = (prev_s, end)
        else:
            merged.append((start, end))
    if len(merged) >= 2 and (merged[-1][1] - merged[-1][0]) < min_len:
        a, _ = merged[-2]
        merged[-2] = (a, merged[-1][1])
        merged.pop()
    return merged


def extract_frame(path: Path, t: float, dest: Path, width: int = 320) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            ffmpeg_bin(),
            "-hide_banner",
            "-y",
            "-ss",
            f"{max(t, 0):.3f}",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-vf",
            f"scale={width}:-2",
            str(dest),
        ]
    )
    return dest


def read_frame_bgr(path: Path, t: float, width: int = 320) -> np.ndarray:
    tmp = path.parent / f".frame_{path.stem}_{int(t * 1000)}.jpg"
    try:
        extract_frame(path, t, tmp, width=width)
        img = cv2.imread(str(tmp))
        if img is None:
            raise MediaError(f"Could not read frame at {t:.2f}s from {path}")
        return img
    finally:
        if tmp.exists():
            tmp.unlink()


def sample_gray_frames(path: Path, start: float, duration: float, fps: float = 4.0, width: int = 160) -> np.ndarray:
    height = 90
    cmd = [
        ffmpeg_bin(),
        "-hide_banner",
        "-ss",
        f"{max(start, 0):.3f}",
        "-t",
        f"{max(duration, 0.1):.3f}",
        "-i",
        str(path),
        "-vf",
        f"fps={fps},scale={width}:{height}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=120)
    if proc.returncode != 0 or not proc.stdout:
        return np.zeros((1, height, width), dtype=np.uint8)
    n = len(proc.stdout) // (width * height)
    if n <= 0:
        return np.zeros((1, height, width), dtype=np.uint8)
    return np.frombuffer(proc.stdout[: n * width * height], dtype=np.uint8).reshape(n, height, width)


def motion_stats(path: Path, start: float, duration: float) -> tuple[float, str]:
    frames = sample_gray_frames(path, start, duration)
    if len(frames) < 2:
        return 0.0, "static"
    diffs = np.abs(frames[1:].astype(np.float32) - frames[:-1].astype(np.float32)).mean(axis=(1, 2))
    energy = float(np.clip(diffs.mean() / 40.0, 0.0, 1.0))
    if energy < 0.08:
        label = "static"
    elif energy < 0.22:
        label = "gentle"
    elif energy < 0.45:
        label = "dynamic"
    else:
        label = "whip"
    return energy, label


def frame_quality(bgr: np.ndarray) -> tuple[float, float, float, bool, float]:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    luma = float(gray.mean() / 255.0)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    sat = float(hsv[:, :, 1].mean() / 255.0)
    sharp_n = float(np.clip(sharp / 400.0, 0.0, 1.0))
    exposure = 1.0 - abs(luma - 0.5) * 1.6
    quality = float(np.clip(0.6 * sharp_n + 0.4 * max(exposure, 0.0), 0.0, 1.0))
    face = False
    face_x = 0.5
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    if cascade_path.exists():
        cascade = cv2.CascadeClassifier(str(cascade_path))
        faces = cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=4, minSize=(24, 24))
        if len(faces) > 0:
            face = True
            x, _y, w, h = max(faces, key=lambda f: f[2] * f[3])
            face_x = float((x + w / 2) / max(gray.shape[1], 1))
    return quality, luma, sat, face, face_x


def extract_audio_wav(path: Path, dest: Path) -> Path | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        run(
            [
                ffmpeg_bin(),
                "-hide_banner",
                "-y",
                "-i",
                str(path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "22050",
                str(dest),
            ]
        )
    except MediaError:
        return None
    return dest if dest.exists() and dest.stat().st_size > 1000 else None


def concat_file_line(path: Path) -> str:
    posix = path.resolve().as_posix().replace("'", r"'\''")
    return f"file '{posix}'"


def filter_path(path: Path) -> str:
    """Escape a filesystem path for an FFmpeg filter argument."""
    return path.resolve().as_posix().replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
