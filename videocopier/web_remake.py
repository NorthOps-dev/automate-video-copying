from __future__ import annotations

from pathlib import Path

from videocopier.adapt import tiktok_cards
from videocopier.media import list_videos, video_info
from videocopier.models import Blueprint, CaptionLine, CutList, Shot, Slot
from videocopier.ocr import ocr_captions
from videocopier.rewrite import coalesce_cards, remake_for_client


def _captions(reference: Path, duration: float, slot: dict, brief: dict, progress=lambda m: None) -> list[CaptionLine]:
    cards = coalesce_cards(tiktok_cards(ocr_captions(reference, duration, progress=progress)))
    if not cards:
        return []
    return remake_for_client(cards, slot or {}, brief or {}) or cards


def _cutlist(videos: list[Path], want: float) -> CutList:
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


def remake_from_uploads(
    reference: Path,
    footage_dir: Path,
    slot: dict,
    brief: dict,
    progress=lambda m: None,
) -> tuple[Blueprint, CutList]:
    videos = list_videos(footage_dir)
    if not videos:
        raise FileNotFoundError("Upload at least one video.")
    info = video_info(reference)
    duration = float(info["duration"])
    progress("Reading the words on the TikTok…")
    captions = _captions(reference, duration, slot, brief, progress=progress)
    if captions:
        for card in captions:
            preview = card.text.replace("\n", " / ")
            progress(f"  {card.start:.1f}s  {preview[:80]}")
    cutlist = _cutlist(videos, duration)
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
    return blueprint, cutlist
