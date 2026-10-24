from __future__ import annotations

import logging
import re
from functools import lru_cache

import numpy as np

from videocopier.media import read_frame_bgr
from videocopier.models import CaptionLine

log = logging.getLogger("videocopier")


@lru_cache(maxsize=1)
def _engine():
    try:
        from rapidocr_onnxruntime import RapidOCR

        return RapidOCR()
    except Exception as exc:
        log.info("OCR unavailable (%s)", exc)
        return None


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _similar(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if na == nb:
        return True
    if not na or not nb:
        return False
    if na in nb or nb in na:
        return True
    wa = set(re.findall(r"[a-z0-9]+", a.lower()))
    wb = set(re.findall(r"[a-z0-9]+", b.lower()))
    if not wa or not wb:
        return False
    return len(wa & wb) / len(wa | wb) >= 0.55


def ocr_captions(path, duration: float, progress=lambda m: None) -> list[CaptionLine]:
    engine = _engine()
    if engine is None or duration < 0.4:
        return []
    progress("Reading on-screen TikTok text…")
    step = 0.45
    samples: list[tuple[float, str, float]] = []
    t = 0.15
    while t < duration:
        try:
            frame = read_frame_bgr(path, t, width=720)
            result, _elapse = engine(frame)
        except Exception:
            t += step
            continue
        lines: list[str] = []
        ys: list[float] = []
        h = frame.shape[0]
        for item in result or []:
            box, text, conf = item[0], item[1], item[2]
            if not text or conf < 0.45 or len(text.strip()) < 2:
                continue
            text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text.strip())
            text = re.sub(r"\bI([a-z])", r"I \1", text)
            text = re.sub(r"([a-zA-Z])(\d)", r"\1 \2", text)
            text = re.sub(r"(\d)([a-zA-Z])", r"\1 \2", text)
            text = re.sub(r"([,:;!?])([A-Za-z])", r"\1 \2", text)
            text = (
                text.replace("don'tcomebacktowork", "don't come back to work")
                .replace("dontcomebacktowork", "don't come back to work")
                .replace("come backtowork", "come back to work")
                .replace("andI", "and I")
                .replace("Newin ", "New in ")
            )
            lines.append(text)
            pts = np.array(box, dtype=np.float32).reshape(-1, 2)
            ys.append(float(pts[:, 1].min() / max(h, 1)))
        text = "\n".join(lines).strip()
        y_ratio = float(min(ys)) if ys else 0.14
        samples.append((t, text, y_ratio))
        t += step

    events: list[CaptionLine] = []
    start = 0.0
    chunk = ""
    y_ratio = 0.14
    for t, text, y in samples:
        if _similar(text, chunk):
            if len(_norm(text)) > len(_norm(chunk)):
                chunk = text
                y_ratio = y
            continue
        if len(_norm(chunk)) >= 8:
            events.append(
                CaptionLine(
                    text=chunk,
                    start=round(start, 3),
                    end=round(t, 3),
                    kind="overlay",
                    y_ratio=round(y_ratio, 3),
                )
            )
        chunk = text
        start = t
        y_ratio = y
    if len(_norm(chunk)) >= 8:
        events.append(
            CaptionLine(
                text=chunk,
                start=round(start, 3),
                end=round(duration, 3),
                kind="overlay",
                y_ratio=round(y_ratio, 3),
            )
        )

    held: list[CaptionLine] = []
    events.sort(key=lambda e: e.start)
    for i, card in enumerate(events):
        nxt = events[i + 1].start if i + 1 < len(events) else duration
        end = max(card.end, card.start + 0.85)
        if i + 1 < len(events):
            end = min(end, nxt - 0.05)
        else:
            end = max(end, duration)
        if end <= card.start + 0.55:
            continue
        held.append(card.model_copy(update={"end": round(end, 3)}))
    progress(f"Found {len(held)} on-screen caption cards")
    return held
