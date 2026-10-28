from __future__ import annotations

import re
from pathlib import Path

from videocopier.adapt import tiktok_cards
from videocopier.models import CaptionLine
from videocopier.ocr import ocr_captions
from videocopier.rewrite import coalesce_cards, drop_unburnable, remake_for_client

_TINY = {"a", "i", "to", "in", "we", "it", "of", "on", "and", "the", "or"}
_FRAG = {"brigh", "lant", "tht", "ned", "gpat", "vblley", "piuat", "dinimg"}


_REACT = re.compile(r"sooo|delicious|obsessed|unreal|insane|amazing", re.I)


def _fragment(word: str) -> bool:
    w = word.lower()
    if w in _TINY:
        return False
    if w in _FRAG:
        return True
    if len(w) <= 2:
        return True
    return len(w) <= 4 and not re.search(r"[aeiouy]", w)


def _garbled(text: str) -> bool:
    from videocopier.ocr import _ocr_junk_line

    t = text.strip()
    if _ocr_junk_line(t):
        return True
    words = re.findall(r"[A-Za-z']+", text)
    if len(words) < 2:
        return True
    broken = sum(1 for w in words if _fragment(w))
    if broken / len(words) >= 0.25:
        return True
    return False


def _flicker(card: CaptionLine) -> bool:
    words = re.findall(r"[A-Za-z']+", card.text)
    span = card.end - card.start
    return span < 1.15 and len(words) <= 2 and not _REACT.search(card.text)


def _drop_garbled(cards: list[CaptionLine]) -> list[CaptionLine]:
    from videocopier.ocr import strip_junk_lines

    keep: list[CaptionLine] = []
    for card in cards:
        text = strip_junk_lines(card.text)
        if not text:
            continue
        card = card.model_copy(update={"text": text})
        if _garbled(card.text) or _flicker(card):
            if keep and abs(keep[-1].y_ratio - card.y_ratio) < 0.07:
                keep[-1] = keep[-1].model_copy(update={"end": max(keep[-1].end, card.end)})
            continue
        keep.append(card)
    return keep


def caption_timeline(
    reference: Path,
    duration: float,
    slot: dict,
    brief: dict,
    progress=lambda m: None,
) -> list[CaptionLine]:
    _source, remade = caption_plan(reference, duration, slot, brief, progress=progress)
    return remade


def caption_plan(
    reference: Path,
    duration: float,
    slot: dict,
    brief: dict,
    progress=lambda m: None,
) -> tuple[list[CaptionLine], list[CaptionLine]]:
    """OCR the format, remake for the client, stop before burn so a human can edit."""
    progress("Finding the words on the TikTok…")
    raw = ocr_captions(reference, duration, progress=progress)
    progress("Locking the original caption cadence…")
    cards = coalesce_cards(tiktok_cards(raw))
    timed = _drop_garbled(cards)
    source = cards or raw
    if not timed:
        progress("OCR is unusable — write the cards yourself.")
        draft = [
            c.model_copy(update={"text": "", "kind": "overlay"})
            for c in source[:8]
        ]
        if not draft:
            draft = [
                CaptionLine(
                    text="",
                    start=0.0,
                    end=round(min(3.0, max(duration, 1.0)), 3),
                    kind="overlay",
                )
            ]
        return source, draft
    progress("Rewriting those cards for the client…")
    client = remake_for_client(timed, slot or {}, brief or {})
    client = drop_unburnable(client, brief or {}, slot or {})
    if not client:
        client = [c.model_copy(update={"text": "", "kind": "overlay"}) for c in timed]
    for card in client:
        preview = card.text.replace("\n", " / ") or "(empty — write the client line)"
        progress(f"  {card.start:.1f}–{card.end:.1f}s  {preview[:90]}")
    return source, client
