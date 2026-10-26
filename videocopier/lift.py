from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from videocopier.captions import HEIGHT, WIDTH
from videocopier.media import read_frame_bgr


def lift_card_png(reference: Path, t: float, y_ratio: float, dest: Path) -> Path | None:
    """Stamp the TikTok's own card pixels — same face, weight, tracking."""
    try:
        frame = read_frame_bgr(Path(reference), max(t, 0.05), width=720)
    except Exception:
        return None
    if frame is None or frame.size == 0:
        return None
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    top = max(0, int((max(y_ratio, 0.04) - 0.02) * h))
    # Card only — a 0.34 band reaches the original talent's hands.
    bot = min(h, int((y_ratio + 0.20) * h))
    if bot - top < 40:
        return None

    roi = gray[top:bot]
    mid = roi[(roi > 50) & (roi < 220)]
    if mid.size < 200:
        return None
    bg = int(np.median(mid))

    white = (gray >= 225).astype(np.uint8)
    white[:top] = 0
    white[bot:] = 0
    near = cv2.dilate(white, np.ones((9, 9), np.uint8), 1)
    black = ((gray <= 45) & (near > 0)).astype(np.uint8)
    core = cv2.dilate(white | black, np.ones((5, 5), np.uint8), 1)
    core[:top] = 0
    core[bot:] = 0

    dev = np.maximum(
        np.clip(gray.astype(np.int16) - bg, 0, 255),
        np.clip(bg - gray.astype(np.int16), 0, 255),
    ).astype(np.uint8)
    alpha = np.where(core > 0, np.clip((dev.astype(np.int16) - 18) * 4, 0, 255), 0).astype(np.uint8)
    alpha = np.maximum(alpha, np.maximum(white * 255, black * 255))
    center = white.copy()
    center[:, : int(w * 0.12)] = 0
    center[:, int(w * 0.88) :] = 0
    nlab, labels, stats, _ = cv2.connectedComponentsWithStats(center, connectivity=8)
    letters = np.zeros_like(center)
    text_floor = int((y_ratio + 0.20) * h)
    for i in range(1, nlab):
        area = int(stats[i, cv2.CC_STAT_AREA])
        cy = int(stats[i, cv2.CC_STAT_TOP] + stats[i, cv2.CC_STAT_HEIGHT] / 2)
        if area >= 30 and cy <= text_floor:
            letters[labels == i] = 1
    ys, xs = np.where(letters > 0)
    if ys.size < 80:
        return None
    near = cv2.dilate(letters, np.ones((13, 13), np.uint8), 1)
    alpha = np.where(near > 0, alpha, 0)
    alpha = _keep_text_blobs(alpha)
    if int((alpha > 80).sum()) < 400:
        return None

    bgr = frame.copy()
    bgr[white > 0] = (255, 255, 255)
    bgr[black > 0] = (0, 0, 0)
    rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
    rgba[:, :, 3] = alpha
    rgba = cv2.resize(rgba, (WIDTH, HEIGHT), interpolation=cv2.INTER_CUBIC)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(dest), rgba):
        return None
    return dest


def _keep_text_blobs(alpha: np.ndarray) -> np.ndarray:
    """Drop ceiling lines and specks; keep letter-sized blobs."""
    mask = (alpha > 40).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    keep = np.zeros_like(alpha)
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if area < 40:
            continue
        if bh <= 12 and bw > bh * 5:
            continue
        if bw <= 4 and bh > 80:
            continue
        keep[labels == i] = alpha[labels == i]
    return keep
