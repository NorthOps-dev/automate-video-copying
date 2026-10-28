from __future__ import annotations

import re

from videocopier.knowledge import brief_blurb
from videocopier.models import CaptionLine
from videocopier.rewrite import remake_for_client


def _line_text(item: dict) -> str:
    return str(item.get("brand") or item.get("text") or "").strip()


def _letters(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "", text)


def _clean_card_text(text: str) -> str:
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
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
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def tiktok_cards(fallback: list[CaptionLine]) -> list[CaptionLine]:
    """On-screen text actually burned into the reference TikTok."""
    cards = []
    for card in fallback:
        if card.kind != "overlay":
            continue
        text = _clean_card_text(card.text)
        if len(_letters(text)) < 6:
            continue
        cards.append(card.model_copy(update={"text": text}))
    return cards


def captions_from_design(
    slot: dict,
    brief: dict,
    fallback: list[CaptionLine],
    duration: float,
) -> list[CaptionLine]:
    """TikTok card timing, rewritten for the client. Board script only if OCR is empty."""
    on_video = tiktok_cards(fallback)
    if on_video:
        return remake_for_client(on_video, slot, brief)

    script = slot.get("scriptLines") or []
    cards: list[CaptionLine] = []
    if isinstance(script, list) and script:
        for item in script:
            if not isinstance(item, dict):
                continue
            text = _line_text(item)
            if not text:
                continue
            start = float(item.get("start") or 0)
            end = float(item.get("end") or start + 1.2)
            cards.append(
                CaptionLine(
                    text=text,
                    start=round(start, 3),
                    end=round(max(end, start + 0.35), 3),
                    kind="overlay",
                    y_ratio=0.14,
                )
            )
        if cards:
            return cards

    body = (slot.get("clientScript") or "").strip()
    if body:
        parts = [p.strip() for p in body.replace("\r", "").split("\n") if p.strip()]
        if not parts:
            parts = [body]
        span = max(duration, 1.0) / max(len(parts), 1)
        for i, part in enumerate(parts):
            cards.append(
                CaptionLine(
                    text=part,
                    start=round(i * span, 3),
                    end=round(min(duration, (i + 1) * span), 3),
                    kind="overlay",
                    y_ratio=0.14,
                )
            )
        return cards

    hook = (slot.get("hook") or "").strip()
    caption = (slot.get("caption") or "").strip()
    name = (brief.get("name") or slot.get("clientName") or "").strip()
    if hook or caption:
        text = hook
        if caption and caption.lower() not in hook.lower():
            text = f"{hook}\n{caption}" if hook else caption
        if name and name.lower() not in text.lower() and brief.get("cta"):
            text = f"{text}\n{brief['cta']}"
        if fallback:
            return [
                CaptionLine(
                    text=text,
                    start=fallback[0].start,
                    end=max(fallback[-1].end, fallback[0].start + 1.5),
                    kind="overlay",
                    y_ratio=0.14,
                )
            ]
        return [CaptionLine(text=text, start=0.1, end=max(duration, 2.0), kind="overlay", y_ratio=0.14)]

    if fallback:
        return remake_for_client(fallback, slot, brief)
    blurb = brief_blurb(brief)
    if blurb:
        return [CaptionLine(text=blurb, start=0.1, end=max(duration, 2.0), kind="overlay", y_ratio=0.14)]
    return []
