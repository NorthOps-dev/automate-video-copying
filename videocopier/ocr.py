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
            text = (
                text.replace("don'tcomebacktowork", "don't come back to work")
                .replace("dontcomebacktowork", "don't come back to work")
                .replace("come backtowork", "come back to work")
            )
            lines.append(text)
            pts = np.array(box, dtype=np.float32).reshape(-1, 2)
            ys.append(float(pts[:, 1].mean() / max(h, 1)))
        text = "\n".join(lines).strip()
        y_ratio = float(np.median(ys)) if ys else 0.22
        samples.append((t, text, y_ratio))
        t += step

    events: list[CaptionLine] = []
    prev_norm = ""
    start = 0.0
    chunk = ""
    y_ratio = 0.22
    for t, text, y in samples:
        n = _norm(text)
        if n == prev_norm:
            if text.count(" ") > chunk.count(" "):
                chunk = text
                y_ratio = y
            continue
        if prev_norm and len(chunk) >= 8:
            events.append(
                CaptionLine(
                    text=chunk,
                    start=round(start, 3),
                    end=round(t, 3),
                    kind="overlay",
                    y_ratio=round(y_ratio, 3),
                )
            )
        prev_norm = n
        chunk = text
        start = t
        y_ratio = y
    if prev_norm and len(chunk) >= 8:
        events.append(
            CaptionLine(
                text=chunk,
                start=round(start, 3),
                end=round(duration, 3),
                kind="overlay",
                y_ratio=round(y_ratio, 3),
            )
        )
    # Keep overlay cards that stay up at least 0.8s
    kept = [e for e in events if (e.end - e.start) >= 0.8]
    progress(f"Found {len(kept)} on-screen caption cards")
    return kept
