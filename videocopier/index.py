from __future__ import annotations

from pathlib import Path

from videocopier.embed import embed_frame
from videocopier.media import (
    detect_cuts,
    frame_quality,
    list_videos,
    motion_stats,
    read_frame_bgr,
    shot_bounds,
    video_info,
)
from videocopier.models import FootageIndex, Scene


def index_footage(folder: Path, work: Path, progress=lambda m: None, max_scenes: int = 400) -> FootageIndex:
    files = list_videos(folder)
    progress(f"Found {len(files)} video files")
    scenes: list[Scene] = []
    for file_i, path in enumerate(files):
        if len(scenes) >= max_scenes:
            break
        try:
            info = video_info(path)
        except Exception:
            continue
        scene_work = work / "index_meta" / path.stem
        scene_work.mkdir(parents=True, exist_ok=True)
        try:
            cuts = detect_cuts(path, scene_work, threshold=0.32)
            bounds = shot_bounds(cuts, info["duration"], min_len=0.45)
        except Exception:
            bounds = [(0.0, info["duration"])]
        progress(f"Indexing {path.name} ({file_i + 1}/{len(files)}) — {len(bounds)} scenes")
        for start, end in bounds:
            if len(scenes) >= max_scenes:
                break
            dur = end - start
            if dur < 0.4:
                continue
            mid = start + min(dur * 0.3, 1.5)
            try:
                frame = read_frame_bgr(path, mid)
                quality, luma, sat, has_face, face_x = frame_quality(frame)
                embedding = embed_frame(frame)
            except Exception:
                quality, luma, sat, has_face, face_x = 0.3, 0.5, 0.3, False, 0.5
                embedding = []
            energy, motion = motion_stats(path, start, min(dur, 4.0))
            scenes.append(
                Scene(
                    path=str(path),
                    start=round(start, 3),
                    end=round(end, 3),
                    duration=round(dur, 3),
                    quality=round(quality, 4),
                    motion=motion,
                    energy=round(energy, 4),
                    has_face=has_face,
                    face_x=round(face_x, 4),
                    mean_luma=round(luma, 4),
                    embedding=embedding,
                )
            )
    return FootageIndex(scenes=scenes, files=[str(p) for p in files])
