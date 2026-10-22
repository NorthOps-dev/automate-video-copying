from __future__ import annotations

from pathlib import Path

from videocopier.embed import cosine
from videocopier.models import Blueprint, CutList, FootageIndex, Scene, Slot, Shot

MOTION_RANK = {"static": 0, "gentle": 1, "dynamic": 2, "whip": 3}


def _motion_sim(a: str, b: str) -> float:
    return max(0.0, 1.0 - abs(MOTION_RANK.get(a, 1) - MOTION_RANK.get(b, 1)) / 3.0)


def _overlaps(used: list[tuple[str, float, float]], path: str, start: float, end: float) -> bool:
    for p, a, b in used:
        if p != path:
            continue
        if start < b - 0.05 and end > a + 0.05:
            return True
    return False


def _score(shot: Shot, scene: Scene) -> float:
    visual = cosine(shot.embedding, scene.embedding)
    motion = _motion_sim(shot.motion, scene.motion)
    role = 0.0
    if shot.has_face and scene.has_face:
        role += 0.12
    if shot.role == "talking_head" and scene.has_face:
        role += 0.1
    if shot.role in {"broll", "hook"} and not shot.has_face and not scene.has_face:
        role += 0.04
    luma = 1.0 - min(abs(shot.mean_luma - scene.mean_luma), 1.0)
    hist_mode = len(shot.embedding) > 600
    visual_w = 0.28 if hist_mode else 0.58
    quality_w = 0.28 if hist_mode else 0.16
    return visual_w * visual + 0.16 * motion + quality_w * scene.quality + 0.06 * luma + role


def match_footage(
    blueprint: Blueprint,
    index: FootageIndex,
    threshold: float = 0.18,
) -> CutList:
    used: list[tuple[str, float, float]] = []
    slots: list[Slot] = []
    unfilled: list[str] = []

    for shot in blueprint.shots:
        best: tuple[float, Scene, float, float, float] | None = None  # score, scene, src_in, src_out, speed
        for scene in index.scenes:
            need = shot.duration
            if scene.duration < min(need * 0.45, 1.2):
                continue
            speed = 1.0
            take = min(need, scene.duration)
            src_in = scene.start
            # skip a beat of handle if the scene is long enough
            if scene.duration > take + 0.4:
                src_in = scene.start + 0.15
            src_out = src_in + take
            if src_out > scene.end:
                src_out = scene.end
                src_in = max(scene.start, src_out - take)
            only_one_clip = len({s.path for s in index.scenes}) <= 1
            if not only_one_clip and _overlaps(used, scene.path, src_in, src_out):
                continue
            score = _score(shot, scene)
            if best is None or score > best[0]:
                best = (score, scene, src_in, src_out, speed)

        if best is None or best[0] < threshold:
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
                    score=best[0] if best else 0.0,
                    reason="No clip in the folder was close enough — film this shot",
                )
            )
            continue

        score, scene, src_in, src_out, speed = best
        used.append((scene.path, src_in, src_out))
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

    return CutList(duration=blueprint.duration, slots=slots, unfilled=unfilled)
