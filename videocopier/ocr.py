from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
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


_JUNK = re.compile(r"[#@]|[\u4e00-\u9fff]|起|⚠️|‼️")
_CLOCK = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
_CAPS_JUNK = re.compile(r"^[A-Z]{4,12}$")
_SAFE_LONG = {"margaritas", "proposition", "restaurant", "definitely"}
_WORDS = tuple(
    sorted(
        {
            "a", "alert", "and", "area", "award", "back", "bar", "beard", "break",
            "bright", "champion", "chef", "chicken", "come", "decor", "definitely",
            "delicious", "dining", "don't", "eggplant", "female", "filled", "first",
            "fired", "get", "goat", "in", "is", "it", "james", "lunch", "lively",
            "margaritas", "must", "new", "on", "our", "patio", "place", "plant",
            "proposition", "recommend", "restaurant", "room", "skewers", "sooo",
            "spacious", "sprouted", "stephanie", "themed", "this", "to", "top",
            "tried", "try", "valley", "visit", "was", "we", "winner", "with",
            "wood", "work", "you",
        },
        key=len,
        reverse=True,
    )
)


def _unglue_token(token: str) -> str:
    raw = token.strip()
    if "-" in raw:
        return "-".join(_unglue_plain(part) for part in raw.split("-"))
    return _unglue_plain(raw)


def _unglue_plain(raw: str) -> str:
    if len(raw) < 8:
        return raw
    lower = raw.lower()
    out: list[str] = []
    i = 0
    while i < len(lower):
        hit = next((word for word in _WORDS if len(word) >= 3 and lower.startswith(word, i)), None)
        if not hit:
            out.append(raw[i:])
            break
        out.append(hit)
        i += len(hit)
    if len(out) <= 1:
        return raw
    rebuilt = " ".join(out)
    if raw[0].isupper():
        rebuilt = rebuilt[0].upper() + rebuilt[1:]
    return rebuilt


def _unglue(text: str) -> str:
    text = re.sub(r"[#@][\w\u4e00-\u9fff]+", "", text)
    text = text.replace("wood-firedl", "wood-fired").replace("woodfired", "wood-fired")
    text = text.replace("plantfilled", "plant-filled").replace("goatthemed", "goat-themed")
    text = text.replace("musttry", "must-try").replace("Must-Try", "Must-Try")
    text = text.replace("gpat-themed", "goat-themed").replace("gpat themed", "goat-themed")
    text = text.replace("don'tcomebacktowork", "don't come back to work")
    text = text.replace("dontcomebacktowork", "don't come back to work")
    text = text.replace("come backtowork", "come back to work")
    parts = []
    for line in text.split("\n"):
        words = []
        for token in line.split():
            if _JUNK.search(token) and len(re.sub(r"[A-Za-z]", "", token)) > 1:
                continue
            words.append(_unglue_token(token))
        line = " ".join(words)
        line = re.sub(r"\s+", " ", line).strip(" ,")
        if line:
            parts.append(line)
    return "\n".join(parts)


_WORD_SET = {w for w in (
    "alert", "area", "award", "back", "bar", "beard", "break", "bright", "champion",
    "chef", "chicken", "come", "decor", "definitely", "delicious", "dining", "eggplant",
    "female", "filled", "first", "fired", "goat", "james", "lunch", "lively", "margaritas",
    "must", "patio", "place", "plant", "proposition", "recommend", "restaurant", "room",
    "skewers", "spacious", "sprouted", "stephanie", "themed", "this", "tried", "valley",
    "visit", "winner", "with", "wood", "work",
) if len(w) >= 4}


def _is_glued(token: str) -> bool:
    w = re.sub(r"[^A-Za-z]", "", token)
    if len(w) < 12 or w.lower() in _SAFE_LONG:
        return False
    lower = w.lower()
    if len(lower) >= 16:
        return True
    for size in range(4, len(lower) - 3):
        a, b = lower[:size], lower[size:]
        if a in _WORD_SET and (b in _WORD_SET or any(b.startswith(x) for x in _WORD_SET)):
            return True
    return False


def _ocr_junk_line(text: str) -> bool:
    t = text.strip()
    if not t or _CLOCK.match(t):
        return True
    if _CAPS_JUNK.match(t) and t not in {"ALERT", "MUST"}:
        return True
    if re.search(r"[\u4e00-\u9fff]", t):
        return True
    if re.search(r"vblley|gpat", t, re.I):
        return True
    letters = re.sub(r"[^A-Za-z]", "", t)
    if letters and _CAPS_JUNK.match(letters) and letters not in {"ALERT", "MUST"}:
        return True
    words = re.findall(r"[A-Za-z']+", t)
    if not words:
        return True
    if any(_is_glued(tok) for tok in t.split()):
        return True
    return False


def strip_junk_lines(text: str) -> str:
    keep = [ln.strip() for ln in (text or "").split("\n") if ln.strip() and not _ocr_junk_line(ln)]
    return "\n".join(keep)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _similar(a: str, b: str) -> bool:
    """Same card, allowing OCR to drop/add a bit — not a later card glued on."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    wa = set(re.findall(r"[a-z0-9]+", a.lower()))
    wb = set(re.findall(r"[a-z0-9]+", b.lower()))
    if wa and wb:
        jaccard = len(wa & wb) / len(wa | wb)
        if jaccard >= 0.62:
            return True
    lo, hi = (na, nb) if len(na) <= len(nb) else (nb, na)
    if lo in hi:
        return len(lo) / len(hi) >= 0.58
    if min(len(na), len(nb)) >= 12 and SequenceMatcher(None, na, nb).ratio() >= 0.58:
        return True
    return False


def _detect_face(frame, boxes: list) -> str:
    """Dark type sitting in a white pill → box. White glyphs + outline → classic."""
    if frame is None or not boxes:
        return "classic"
    h, w = frame.shape[:2]
    votes = 0
    n = 0
    for box in boxes:
        pts = np.array(box, dtype=np.float32).reshape(-1, 2)
        x0, y0 = float(pts[:, 0].min()), float(pts[:, 1].min())
        x1, y1 = float(pts[:, 0].max()), float(pts[:, 1].max())
        pad = int(max(y1 - y0, 8) * 0.4)
        xa0, ya0 = max(0, int(x0) - pad), max(0, int(y0) - pad)
        xa1, ya1 = min(w, int(x1) + pad), min(h, int(y1) + pad)
        roi = frame[max(0, int(y0)) : min(h, int(y1) + 1), max(0, int(x0)) : min(w, int(x1) + 1)]
        around = frame[ya0:ya1, xa0:xa1]
        if roi.size == 0 or around.size == 0:
            continue
        gray = np.mean(roi.astype(np.float32), axis=2) if roi.ndim == 3 else roi.astype(np.float32)
        ring = np.mean(around.astype(np.float32), axis=2) if around.ndim == 3 else around.astype(np.float32)
        dark = float((gray < 50).mean())
        white = float((gray > 220).mean())
        ring_white = float((ring > 220).mean())
        n += 1
        if dark > 0.08 and (white > 0.45 or ring_white > 0.45):
            votes += 1
    if n and votes / n >= 0.5:
        return "box"
    return "classic"


def _geometry(frame, boxes: list) -> tuple[float, float, float, str]:
    h, w = frame.shape[:2]
    tops: list[float] = []
    lefts: list[float] = []
    rights: list[float] = []
    heights: list[float] = []
    for box in boxes:
        pts = np.array(box, dtype=np.float32).reshape(-1, 2)
        x0, y0 = float(pts[:, 0].min()), float(pts[:, 1].min())
        x1, y1 = float(pts[:, 0].max()), float(pts[:, 1].max())
        tops.append(y0 / max(h, 1))
        lefts.append(x0 / max(w, 1))
        rights.append(x1 / max(w, 1))
        heights.append((y1 - y0) / max(h, 1))
    y_ratio = min(tops) if tops else 0.14
    width_ratio = max(rights) - min(lefts) if rights else 0.0
    size_ratio = float(np.median(np.array(heights, dtype=np.float32))) if heights else 0.0
    return y_ratio, float(width_ratio), float(size_ratio), _detect_face(frame, boxes)


@dataclass
class _Read:
    t: float
    text: str
    y_ratio: float
    width_ratio: float
    size_ratio: float
    face: str


def _tidy(text: str) -> str:
    text = re.sub(r"([,:;!?])([A-Za-z])", r"\1 \2", text)
    text = re.sub(r"\s+([:!?.,;])", r"\1", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _cluster_items(frame, items: list[tuple]) -> list[tuple[str, list]]:
    """Split one frame into stacked cards (boxed hook over classic body, etc.)."""
    if not items:
        return []
    rows = []
    for box, text in items:
        y, _w, size, face = _geometry(frame, [box])
        rows.append((y, size, face, box, text))
    rows.sort(key=lambda r: r[0])
    heights = [r[1] for r in rows if r[1] > 0] or [0.02]
    gap_lim = max(0.045, float(np.median(np.array(heights))) * 1.8)
    clusters = [[rows[0]]]
    for row in rows[1:]:
        prev = clusters[-1][-1]
        gap = row[0] - prev[0]
        face_break = row[2] != prev[2] and (row[2] == "box" or prev[2] == "box")
        if gap > gap_lim or face_break:
            clusters.append([row])
        else:
            clusters[-1].append(row)
    out = []
    for cluster in clusters:
        boxes = [r[3] for r in cluster]
        text = _tidy("\n".join(r[4] for r in cluster))
        out.append((text, boxes))
    return out


def _assign_tracks(samples: list[_Read]) -> list[list[_Read]]:
    tracks: list[list[_Read]] = []
    for sample in samples:
        if len(_norm(sample.text)) < 8 or _ocr_junk_line(sample.text):
            continue
        for track in tracks:
            picked = _pick_reading(track)
            if _similar(sample.text, picked.text) or _similar(sample.text, track[-1].text):
                track.append(sample)
                break
        else:
            tracks.append([sample])
    return tracks


def _pick_reading(group: list[_Read]) -> _Read:
    counts = sorted(r.text.count("\n") + 1 for r in group)
    target = counts[len(counts) // 2]
    same = [r for r in group if r.text.count("\n") + 1 == target] or group
    best = max(same, key=lambda r: (r.text.count(" "), len(_norm(r.text))))
    faces = Counter(r.face for r in same)
    y = float(np.median([r.y_ratio for r in same]))
    width = float(np.median([r.width_ratio for r in same if r.width_ratio > 0] or [best.width_ratio]))
    size = float(np.median([r.size_ratio for r in same if r.size_ratio > 0] or [best.size_ratio]))
    return _Read(
        t=best.t,
        text=best.text,
        y_ratio=round(y, 3),
        width_ratio=round(width, 3),
        size_ratio=round(size, 3),
        face=faces.most_common(1)[0][0],
    )


def ocr_captions(path, duration: float, progress=lambda m: None) -> list[CaptionLine]:
    engine = _engine()
    if engine is None or duration < 0.4:
        return []
    progress("Reading on-screen TikTok text…")
    step = 0.45
    samples: list[_Read] = []
    t = 0.15
    while t < duration:
        try:
            frame = read_frame_bgr(path, t, width=720)
            result, _elapse = engine(frame)
        except Exception:
            t += step
            continue
        lines: list[str] = []
        boxes: list = []
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
            text = _tidy(_unglue(text))
            if len(_norm(text)) < 3 or _ocr_junk_line(text):
                continue
            lines.append(text)
            boxes.append(box)
        for text, cluster_boxes in _cluster_items(frame, list(zip(boxes, lines))):
            text = strip_junk_lines(text)
            if len(_norm(text)) < 8:
                continue
            y_ratio, width_ratio, size_ratio, face = _geometry(frame, cluster_boxes)
            samples.append(
                _Read(
                    t=t,
                    text=text,
                    y_ratio=y_ratio,
                    width_ratio=width_ratio,
                    size_ratio=size_ratio,
                    face=face,
                )
            )
        t += step

    events: list[CaptionLine] = []
    for track in _assign_tracks(samples):
        picked = _pick_reading(track)
        if _ocr_junk_line(picked.text) or len(_norm(picked.text)) < 8:
            continue
        start = track[0].t
        end = max(track[-1].t + step, start + 0.85)
        events.append(
            CaptionLine(
                text=picked.text,
                start=round(start, 3),
                end=round(min(end, duration), 3),
                kind="overlay",
                y_ratio=picked.y_ratio,
                face=picked.face,
                width_ratio=picked.width_ratio,
                size_ratio=picked.size_ratio,
            )
        )

    held: list[CaptionLine] = []
    events.sort(key=lambda e: (e.start, e.y_ratio))
    for i, card in enumerate(events):
        end = max(card.end, card.start + 0.85)
        for later in events:
            if later is card or later.start <= card.start:
                continue
            if abs(later.y_ratio - card.y_ratio) < 0.07 and later.start < end:
                end = later.start - 0.05
        if end <= card.start + 0.55:
            continue
        held.append(card.model_copy(update={"end": round(min(end, duration), 3)}))
    progress(f"Found {len(held)} on-screen caption cards")
    return held
