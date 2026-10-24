from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from videocopier.embed import cosine
from videocopier.models import Blueprint, CutList, FootageIndex, Scene, Slot, Shot

MOTION_RANK = {"static": 0, "gentle": 1, "dynamic": 2, "whip": 3}


def _motion_sim(a: str, b: str) -> float:
    return max(0.0, 1.0 - abs(MOTION_RANK.get(a, 1) - MOTION_RANK.get(b, 1)) / 3.0)


def _next_window(
    used: list[tuple[str, float, float]],
    path: str,
    scene_start: float,
    scene_end: float,
    need: float,
) -> tuple[float, float] | None:
    """Next unused stretch of this clip that can cover the shot (prefer the take, not the leftover tail)."""
    busy = sorted((a, b) for p, a, b in used if p == path)
    cursor = scene_start
    gaps: list[tuple[float, float]] = []
    for a, b in busy:
        if cursor < a - 0.02:
            gaps.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < scene_end - 0.02:
        gaps.append((cursor, scene_end))
    min_take = min(max(need * 0.4, 0.35), need)
    picked: tuple[tuple[float, float], float, float] | None = None
    for a, b in gaps:
        avail = b - a
        if avail < min_take:
            continue
        take = min(need, avail)
        src_in = a + 0.06 if avail > take + 0.18 else a
        src_out = min(src_in + take, b)
        if src_out - src_in < min_take:
            continue
        # Prefer a full unused take. Leftover tails are usually the worst bits.
        freshness = 1.0 - min(src_in / max(scene_end, 1.0), 1.0)
        full = 1.0 if avail >= need * 0.92 else avail / max(need, 0.1)
        rank = (full, freshness, -a)
        if picked is None or rank > picked[0]:
            picked = (rank, src_in, src_out)
    if picked:
        return picked[1], picked[2]
    return None


def _direction_bonus(direction: str, scene: Scene) -> float:
    d = (direction or "").lower()
    if not d:
        return 0.0
    if any(w in d for w in ("talk", "speak", "face", "straight-on", "straight on")) and scene.has_face:
        return 0.18
    if any(w in d for w in ("macro", "close", "product", "drink", "pour", "shell", "leaf")) and not scene.has_face:
        return 0.14
    if any(w in d for w in ("aerial", "street", "establishing", "downtown", "exterior")) and not scene.has_face:
        return 0.12
    if any(w in d for w in ("interior", "plant", "wide", "patio", "outdoor")):
        return 0.1
    return 0.0


def _score(shot: Shot, scene: Scene, src_in: float, used_sec: float, uses: int, clip_len: float, direction: str) -> float:
    visual = cosine(shot.embedding, scene.embedding)
    motion = _motion_sim(shot.motion, scene.motion)
    role = 0.0
    if shot.has_face and scene.has_face:
        role += 0.22
    elif shot.has_face and not scene.has_face:
        role -= 0.08
    if shot.role == "talking_head" and scene.has_face:
        role += 0.14
    if shot.role in {"broll", "hook"} and not shot.has_face and not scene.has_face:
        role += 0.05
    luma = 1.0 - min(abs(shot.mean_luma - scene.mean_luma), 1.0)
    hist_mode = len(shot.embedding) > 600
    visual_w = 0.22 if hist_mode else 0.32
    quality = scene.quality
    used_frac = used_sec / max(clip_len, 0.5)
    diversity = 0.28 if used_sec < 0.05 else -0.50 * used_frac
    if uses >= 2:
        diversity -= 0.20 * (uses - 1)
    freshness = 0.12 * (1.0 - min(src_in / max(scene.end, 1.0), 1.0))
    reject = 0.0
    if scene.mean_luma < 0.08:
        reject -= 0.32
    if quality < 0.22:
        reject -= 0.22
    return (
        visual_w * visual
        + 0.12 * motion
        + 0.22 * quality
        + 0.05 * luma
        + role
        + diversity
        + freshness
        + reject
        + _direction_bonus(direction, scene)
    )


def match_footage(
    blueprint: Blueprint,
    index: FootageIndex,
    threshold: float = 0.08,
    shot_direction: str = "",
) -> CutList:
    used: list[tuple[str, float, float]] = []
    used_sec: dict[str, float] = defaultdict(float)
    uses: dict[str, int] = defaultdict(int)
    clip_len: dict[str, float] = defaultdict(float)
    for path, dur in (index.durations or {}).items():
        clip_len[path] = max(clip_len[path], float(dur))
    for scene in index.scenes:
        clip_len[scene.path] = max(clip_len[scene.path], scene.end)
    slots: list[Slot] = []
    unfilled: list[str] = []
    only_one_clip = len({s.path for s in index.scenes}) <= 1
    directions = [ln.strip() for ln in re.split(r"\n+", shot_direction) if ln.strip()] if shot_direction else []

    def pick(shot: Shot, direction: str, full_only: bool) -> tuple[float, Scene, float, float, float] | None:
        best: tuple[float, Scene, float, float, float] | None = None
        need = shot.duration
        for scene in index.scenes:
            file_end = clip_len[scene.path]
            # Play a real stretch of the file. Index windows are only for scoring.
            window = _next_window(used, scene.path, 0.0, file_end, need)
            if window is None:
                continue
            src_in, src_out = window
            cover = (src_out - src_in) / max(need, 0.1)
            if full_only and cover < 0.85:
                continue
            if src_out - src_in < min(need * 0.4, 0.35):
                continue
            score = _score(shot, scene, src_in, used_sec[scene.path], uses[scene.path], clip_len[scene.path], direction)
            if score < threshold and best is not None:
                continue
            if best is None or score > best[0]:
                best = (score, scene, src_in, src_out, 1.0)
        return best

    for shot in blueprint.shots:
        direction = directions[shot.index] if shot.index < len(directions) else shot_direction
        best = None if only_one_clip else pick(shot, direction, full_only=True)
        if best is None:
            best = pick(shot, direction, full_only=False)

        if best is None:
            label = (
                f"{shot.duration:.1f}s {shot.role} ({shot.motion}"
                + (", face" if shot.has_face else "")
                + ")"
            )
            unfilled.append(label)
            slots.append(
                Slot(
                    shot_index=shot.index,
                    start=shot.start,
                    end=shot.end,
                    duration=shot.duration,
                    role=shot.role,
                    status="unfilled",
                    score=0.0,
                    reason="Ran out of unused footage",
                )
            )
            continue

        score, scene, src_in, src_out, speed = best
        used.append((scene.path, src_in, src_out))
        used_sec[scene.path] += src_out - src_in
        uses[scene.path] += 1
        slots.append(
            Slot(
                shot_index=shot.index,
                start=shot.start,
                end=shot.end,
                duration=shot.duration,
                role=shot.role,
                status="filled",
                score=round(score, 4),
                reason=f"{Path(scene.path).name} {src_in:.2f}–{src_out:.2f}s",
                source_path=scene.path,
                source_in=round(src_in, 3),
                source_out=round(src_out, 3),
                speed=round(speed, 3),
                face_x=scene.face_x,
            )
        )

    if only_one_clip and len(slots) == 1 and slots[0].status == "filled":
        slot = slots[0]
        play = max((slot.source_out or 0) - (slot.source_in or 0), 0.1)
        slots[0] = slot.model_copy(
            update={"duration": round(play, 3), "end": round(slot.start + play, 3)}
        )
        return CutList(duration=round(slot.start + play, 3), slots=slots, unfilled=unfilled)

    return CutList(duration=blueprint.duration, slots=slots, unfilled=unfilled)
