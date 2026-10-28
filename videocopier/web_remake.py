from __future__ import annotations

from pathlib import Path

from videocopier.media import (
    detect_cuts,
    frame_quality,
    list_videos,
    read_frame_bgr,
    shot_bounds,
    video_info,
)
from videocopier.models import Blueprint, CaptionLine, CutList, Shot, Slot
from videocopier.timeline import caption_plan, caption_timeline


def _captions(reference: Path, duration: float, slot: dict, brief: dict, progress=lambda m: None) -> list[CaptionLine]:
    return caption_timeline(reference, duration, slot or {}, brief or {}, progress=progress)


def _clip_score(path: Path) -> float:
    """People and rooms first. Lamp / plant / flat-art close-ups last."""
    try:
        dur = float(video_info(path)["duration"])
        t = min(1.0, max(0.35, dur * 0.2))
        frame = read_frame_bgr(path, t, width=180)
    except Exception:
        return 0.0
    quality, luma, sat, face, _face_x = frame_quality(frame)
    gray = frame.mean(axis=2) if frame.ndim == 3 else frame
    dark = float((gray < 35).mean())
    mid = float(((gray > 40) & (gray < 200)).mean())
    var = float(gray.var()) / (255.0 ** 2)
    score = luma * 2.0 + var * 40.0 + mid * 0.5 + quality * 0.3
    if face:
        score += 2.0
    if dark > 0.45:
        score -= 2.0
    if var < 0.012 and luma < 0.16:
        score -= 1.8
    if sat > 0.92 and var < 0.015:
        score -= 1.0
    return score


def _rank_videos(videos: list[Path]) -> list[Path]:
    """Keep every clip the user picked. Prefer people/rooms, then stable takes."""
    if len(videos) <= 1:
        return list(videos)
    return [p for p, _ in sorted(((p, _clip_score(p)) for p in videos), key=lambda item: -item[1])]


def _cutlist_linear(videos: list[Path], want: float) -> CutList:
    slots: list[Slot] = []
    t = 0.0
    for i, path in enumerate(videos):
        info = video_info(path)
        take = min(float(info["duration"]), max(want - t, 0.1) if want > 0 else float(info["duration"]))
        if take < 0.2:
            continue
        slots.append(
            Slot(
                shot_index=i,
                start=round(t, 3),
                end=round(t + take, 3),
                duration=round(take, 3),
                role="hook" if i == 0 else "broll",
                status="filled",
                score=1.0,
                reason=f"{path.name} 0.00–{take:.2f}s",
                source_path=str(path),
                source_in=0.0,
                source_out=round(take, 3),
            )
        )
        t += take
        if want > 0 and t >= want - 0.05:
            break
    if not slots:
        raise FileNotFoundError("Those uploads were not usable videos.")
    return CutList(duration=round(t, 3), slots=slots)


def _cutlist(videos: list[Path], want: float, reference: Path | None = None) -> CutList:
    if reference and reference.exists() and len(videos) > 1 and want > 6:
        try:
            cuts = detect_cuts(reference, reference.parent)
            bounds = shot_bounds(cuts, want, min_len=0.7)
        except Exception:
            bounds = []
        if len(bounds) >= 3:
            ranked = _rank_videos(videos)
            slots: list[Slot] = []
            for i, (a, b) in enumerate(bounds):
                need = max(b - a, 0.2)
                path = ranked[i % len(ranked)]
                dur = float(video_info(path)["duration"])
                take = min(need, dur)
                offset = 0.0
                if dur > take + 0.3:
                    offset = min((i // len(videos)) * take, dur - take)
                slots.append(
                    Slot(
                        shot_index=i,
                        start=round(a, 3),
                        end=round(a + take, 3),
                        duration=round(take, 3),
                        role="hook" if i == 0 else "broll",
                        status="filled",
                        score=1.0,
                        reason=f"{path.name} {offset:.2f}–{offset + take:.2f}s",
                        source_path=str(path),
                        source_in=round(offset, 3),
                        source_out=round(offset + take, 3),
                    )
                )
            end = slots[-1].end if slots else want
            return CutList(duration=round(end, 3), slots=slots)
    return _cutlist_linear(videos, want)


def remake_from_uploads(
    reference: Path,
    footage_dir: Path,
    slot: dict,
    brief: dict,
    progress=lambda m: None,
) -> tuple[Blueprint, CutList, list[CaptionLine], list[CaptionLine]]:
    videos = _rank_videos(list_videos(footage_dir))
    if not videos:
        raise FileNotFoundError("Upload at least one video.")
    info = video_info(reference)
    duration = float(info["duration"])
    progress("Reading the words on the TikTok…")
    source, captions = caption_plan(reference, duration, slot, brief, progress=progress)
    cutlist = _cutlist(videos, duration, reference=reference)
    if captions:
        captions = [
            c.model_copy(update={"end": min(c.end, cutlist.duration)})
            for c in captions
            if c.start < cutlist.duration - 0.2
        ]
    blueprint = Blueprint(
        path=str(reference),
        duration=cutlist.duration,
        width=info["width"],
        height=info["height"],
        fps=round(float(info["fps"]), 3),
        captions=captions,
        shots=[
            Shot(
                index=0,
                start=0.0,
                end=cutlist.duration,
                duration=cutlist.duration,
                role="hook",
            )
        ],
    )
    return blueprint, cutlist, source, captions
