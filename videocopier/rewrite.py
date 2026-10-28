from __future__ import annotations

import re

from videocopier.models import CaptionLine

HOOK_RE = re.compile(r"\b(new in|must-try|must try|alert|just opened|introducing|now open)\b", re.I)
TRY_RE = re.compile(r"\b(we tried|i tried|ordered|got the|tasted|ate|drank)\b", re.I)
REACT_RE = re.compile(r"\b(delicious|amazing|obsessed|sooo|so good|unreal|insane|love this|the vibe)\b", re.I)
CTA_RE = re.compile(r"\b(recommend|visit this|come through|you need to|pull up|check it out)\b", re.I)
CRED_RE = re.compile(r"\b(chef|award|founded|owner|first|champion|winner|beard)\b", re.I)


def _letters(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "", text)


def classic_copy(text: str) -> str:
    """Classic TikTok cards: short lines, no em dashes."""
    from videocopier.ocr import _tidy, _unglue

    text = (text or "").replace("—", ",").replace("–", ",").replace(" - ", ", ")
    text = _tidy(_unglue(text))
    lines = [re.sub(r"\s+", " ", ln).strip(" ,") for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def _similar_text(a: str, b: str) -> bool:
    from videocopier.ocr import _similar

    return _similar(a, b)


def coalesce_cards(cards: list[CaptionLine]) -> list[CaptionLine]:
    """One card on screen at a time. Merge repeats. No overlaps."""
    ordered = sorted(cards, key=lambda c: (c.start, c.end))
    merged: list[CaptionLine] = []
    for card in ordered:
        text = classic_copy(card.text)
        if not text:
            continue
        if merged and _similar_text(merged[-1].text, text):
            prev = merged[-1]
            take_new = len(text) >= len(prev.text)
            longer = text if take_new else prev.text
            src = card if take_new else prev
            merged[-1] = prev.model_copy(
                update={
                    "end": max(prev.end, card.end),
                    "text": longer,
                    "face": src.face or prev.face,
                    "width_ratio": src.width_ratio or prev.width_ratio,
                    "size_ratio": src.size_ratio or prev.size_ratio,
                    "y_ratio": src.y_ratio or prev.y_ratio,
                }
            )
        else:
            merged.append(card.model_copy(update={"text": text, "kind": "overlay"}))
    out: list[CaptionLine] = []
    for i, card in enumerate(merged):
        end = card.end
        for later in merged[i + 1 :]:
            if later.start >= end:
                break
            same_band = abs(later.y_ratio - card.y_ratio) < 0.07
            if same_band and end > later.start:
                end = later.start
                break
        if end - card.start < 0.55:
            continue
        out.append(card.model_copy(update={"end": round(end, 3)}))
    return out


def _city(brief: dict, slot: dict) -> str:
    loc = brief.get("location") or ""
    for part in [p.strip() for p in loc.split(",")]:
        if not part or re.search(r"\d", part):
            continue
        if part.upper() in {"CA", "NY", "TX", "USA", "US"} or part.lower().startswith("suite"):
            continue
        if len(part) > 2:
            return part
    hook = slot.get("hook") or ""
    m = re.search(r"New in ([A-Za-z ]+)", hook)
    if m:
        return m.group(1).strip(" !")
    return ""


def _kind(brief: dict) -> str:
    what = (brief.get("what") or "").split(".")[0].split(",")[0].strip()
    if "/" in what:
        what = what.split("/")[0].strip()
    return what or "spot"


def _name(brief: dict, slot: dict) -> str:
    return (brief.get("name") or slot.get("clientName") or "").strip()


def _products(brief: dict) -> list[str]:
    raw = brief.get("products") or []
    if isinstance(raw, str):
        raw = [p.strip() for p in re.split(r"[,/]", raw) if p.strip()]
    out = []
    for item in raw:
        text = str(item).strip()
        if text:
            item = text.split("/")[0].strip()
            item = re.sub(r"\s+kava$", "", item, flags=re.I).strip()
            if item:
                out.append(" ".join(w.capitalize() for w in item.split()))
    return out


def _hero_drink(brief: dict) -> tuple[str, str]:
    raw = (_products(brief) or ["kava"])[0]
    drink = " ".join(w.capitalize() for w in raw.split()) or "Kava"
    plural = drink if drink.lower().endswith("s") else f"{drink}s"
    return drink, plural


def _short(text: str, words: int = 8) -> str:
    bits = [b for b in re.split(r"\s+", (text or "").strip()) if b]
    return " ".join(bits[:words]).strip(" ,.")


VIRAL_LEAK = re.compile(
    r"\b(sunnyvale|valley\s*goat|vblley|gpat|stephanie|izard|james\s*beard|"
    r"eggplant|goat[- ]?themed|wood-fired|top chef|plant[- ]?filled|"
    r"spacious\s*patio|lively bar|dining room|definitely recommend|"
    r"visit this place)\b",
    re.I,
)


def _usable_script(slot: dict) -> list[str]:
    """Board brand lines only. Never the viral OCR sitting in `original`."""
    rows: list[str] = []
    for item in slot.get("scriptLines") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("brand") or "").strip()
        if len(_letters(text)) >= 8 and not VIRAL_LEAK.search(text):
            rows.append(text)
    body = (slot.get("clientScript") or "").strip()
    if not rows and body and not VIRAL_LEAK.search(body):
        rows = [p.strip() for p in body.split("\n") if len(_letters(p)) >= 8]
    return rows


def _role(card: CaptionLine, index: int, n: int) -> str:
    t = card.text.lower()
    if TRY_RE.search(t):
        return "try"
    if REACT_RE.search(t) and len(card.text) < 60:
        return "react"
    if CTA_RE.search(t) or _venue_line(card.text.replace("\n", " ").strip()):
        return "cta"
    if index == 0 or HOOK_RE.search(t):
        return "hook"
    if CRED_RE.search(t) or index == 1:
        return "about"
    return "about"


def _venue_line(line: str) -> bool:
    words = [w for w in re.split(r"\s+", line.strip()) if w]
    if not (1 <= len(words) <= 4):
        return False
    if REACT_RE.search(line) or CTA_RE.search(line) or TRY_RE.search(line):
        return False
    return words[0][:1].isupper()


def _kind_label(brief: dict) -> str:
    kind = _kind(brief)
    return " ".join(w.capitalize() for w in kind.split()) if kind else "Spot"


def _short_name(brief: dict, slot: dict) -> str:
    name = _name(brief, slot)
    kind = _kind(brief)
    if name and kind and name.lower().endswith(kind.lower()):
        return name[: -len(kind)].strip() or name
    return name


def _hook_card(slot: dict, brief: dict, n_lines: int, original: str = "") -> str:
    """Keep the TikTok's hook template. Fill in this client."""
    city = _city(brief, slot)
    label = _kind_label(brief)
    orig = original.lower()
    if city and re.search(r"\bnew in\b", orig):
        line1 = f"New in {city}: Must-Try" if "must" in orig else f"New in {city}!!"
        lines = [line1]
        if n_lines >= 2:
            lines.append(f"{label} Alert!")
        return classic_copy("\n".join(lines[: max(n_lines, 1)]))
    hook = (slot.get("hook") or "").strip() or (f"New in {city}!!" if city else "")
    lines = [hook] if hook else [f"{label} Alert!"]
    if n_lines >= 2 and "alert" not in hook.lower():
        lines.append(f"{label} Alert!")
    return classic_copy("\n".join(lines[: max(n_lines, 1)]))


_HOURS = re.compile(
    r"\b(open daily|hours|\d+\s*-\s*\d+|a\.?m\.?|p\.?m\.?|noon|midnight)\b",
    re.I,
)


def _split_one_liner(brief: dict) -> list[str]:
    one = classic_copy((brief.get("one_liner") or "").replace("—", ",").replace("–", ","))
    bits = [b.strip(" ,.") for b in re.split(r"[,]", one) if len(_letters(b)) >= 8]
    return bits


def _about_card(brief: dict, slot: dict, n_lines: int) -> str:
    """Same cadence as the dining-room card: what this place is, not a wikipedia lede."""
    lines = _split_one_liner(brief)
    city = _city(brief, slot)
    kind = _kind(brief)
    if not lines:
        if kind and city:
            lines = [f"{kind} in {city}"]
        else:
            lines = [_short_name(brief, slot) or _name(brief, slot) or "this place"]
    elif len(lines) < n_lines and city and not any(city.lower() in ln.lower() for ln in lines):
        lines.append(f"in {city}")
    return classic_copy("\n".join(lines[: max(n_lines, 1)]))


def _cred_card(brief: dict, slot: dict, n_lines: int) -> str:
    """Don't copy the viral's chef. Don't dump hours. Who this client is."""
    lines: list[str] = []
    what = (brief.get("what") or "").replace("–", "-").replace("—", ". ")
    for chunk in re.split(r"[.]", what):
        chunk = re.sub(r"\s+", " ", chunk).strip(" /")
        if len(chunk) < 8 or _HOURS.search(chunk):
            continue
        if chunk.lower().startswith("kava bar") or chunk.lower().startswith(_kind(brief).lower()):
            continue
        chunk = chunk.split("(")[0].strip(" ,")
        lines.append(_short(chunk, 8))
        if len(lines) >= n_lines:
            break
    if not lines:
        lines = _split_one_liner(brief)
    if not lines:
        return _about_card(brief, slot, n_lines)
    return classic_copy("\n".join(lines[: max(n_lines, 1)]))


def _try_card(brief: dict, n_lines: int) -> str:
    products = _products(brief)
    if len(products) >= 2:
        lines = [f"we tried the {products[0]}", f"and a {products[1]}"]
    elif products:
        lines = [f"we tried the {products[0]}"]
    else:
        lines = ["we tried the house pour"]
    return "\n".join(lines[: max(n_lines, 1)])


def _react_card(original: str) -> str:
    if REACT_RE.search(original) and len(original) < 60:
        return original.strip()
    return "it was sooo delicious!"


def _cta_card(original: str, brief: dict, slot: dict, n_lines: int = 3) -> str:
    name = _name(brief, slot) or "this place"
    if _venue_line(original.replace("\n", " ").strip()) or (
        n_lines == 1 and _venue_line((original.split("\n") or [""])[0])
    ):
        return name
    cta = classic_copy(brief.get("cta") or "")
    if cta:
        words = cta.replace(".", " ").split()
        if n_lines >= 2 and len(words) > 4:
            mid = max(2, len(words) // 2)
            return classic_copy(" ".join(words[:mid]) + "\n" + " ".join(words[mid:]))
        return classic_copy(cta)
    if n_lines >= 2:
        return classic_copy(f"come through\n{name}")
    return name


def _from_script(script: list[str], cards: list[CaptionLine]) -> list[CaptionLine]:
    if not script or not cards:
        return []
    if len(script) == len(cards):
        texts = script
    elif len(script) > len(cards):
        texts = []
        per = max(1, len(script) // len(cards))
        for i in range(len(cards)):
            chunk = script[i * per : (i + 1) * per] if i < len(cards) - 1 else script[i * per :]
            texts.append("\n".join(chunk))
    else:
        texts = script + [script[-1]] * (len(cards) - len(script))
    out = []
    for card, text in zip(cards, texts):
        out.append(card.model_copy(update={"text": text.strip(), "kind": "overlay"}))
    return out


def clientize_on_screen(text: str, brief: dict, slot: dict) -> str:
    """Same sentence. Swap city / venue / alert type for the client — not the joke."""
    kind = _kind(brief)
    city = _city(brief, slot)
    name = _name(brief, slot)
    out = text
    if kind:
        out = re.sub(r"\bRestaurant Alert\b", f"{kind.title()} Alert", out, flags=re.I)
    if name:
        out = re.sub(r"\bValley Goat\b", name, out, flags=re.I)
    if city:
        out = re.sub(r"\bSunnyvale\b", city, out, flags=re.I)
        out = re.sub(r"\bNew in [A-Z][A-Za-z .]{1,24}", f"New in {city}", out)
    return classic_copy(out)


_REVIEW = re.compile(
    r"\b(dining|patio|decor|chef|award|restaurant|bar area|plant-filled|"
    r"skewers|wood-fired|must-try|alert)\b",
    re.I,
)


def _keep_joke(card: CaptionLine, n: int) -> bool:
    """The drinking-proposal format IS the joke. Don't turn it into a kava ad."""
    t = card.text.lower()
    if re.search(r"\bproposition\b", t):
        return True
    if HOOK_RE.search(t) or CTA_RE.search(t) or TRY_RE.search(t) or CRED_RE.search(t):
        return False
    if _REVIEW.search(t):
        return False
    if n == 1:
        return True
    return False


def _has_client(brief: dict, slot: dict) -> bool:
    return bool(_name(brief, slot) or _city(brief, slot) or (brief.get("what") or "").strip())


def _rewrite_card(card: CaptionLine, index: int, n: int, slot: dict, brief: dict) -> str:
    original = classic_copy(card.text)
    n_lines = max(1, original.count("\n") + 1)
    role = _role(card, index, n)
    if role == "hook":
        return _hook_card(slot, brief, n_lines, original)
    if role == "try":
        return classic_copy(_try_card(brief, n_lines))
    if role == "react":
        return classic_copy(_react_card(original))
    if role == "cta":
        return classic_copy(_cta_card(original, brief, slot, n_lines))
    if CRED_RE.search(original):
        return _cred_card(brief, slot, n_lines)
    return _about_card(brief, slot, n_lines)


def _peel_glued_hook(cards: list[CaptionLine]) -> list[CaptionLine]:
    """If OCR stacked the dining-room copy onto the alert, split it back into two cards."""
    out: list[CaptionLine] = []
    for card in cards:
        lines = [ln.strip() for ln in classic_copy(card.text).split("\n") if ln.strip()]
        if len(lines) == 1 and HOOK_RE.search(lines[0]):
            m = re.search(r"(?i)(.*\balert!?)[\s,]+(.{12,})$", lines[0])
            if m:
                lines = [m.group(1).strip(), m.group(2).strip()]
        hook_at = -1
        for i, ln in enumerate(lines):
            if HOOK_RE.search(ln) or re.search(r"\balert!?\b", ln, re.I):
                hook_at = i
        if hook_at >= 0 and hook_at < len(lines) - 1:
            head, tail = lines[: hook_at + 1], lines[hook_at + 1 :]
            if len(_letters(" ".join(tail))) >= 12 and not HOOK_RE.search(" ".join(tail)):
                out.append(card.model_copy(update={"text": "\n".join(head), "face": card.face or "box"}))
                out.append(
                    card.model_copy(
                        update={
                            "text": "\n".join(tail),
                            "kind": "overlay",
                            "face": "classic",
                            "y_ratio": min(card.y_ratio + 0.10, 0.52),
                        }
                    )
                )
                continue
        out.append(card)
    return out


def remake_for_client(
    cards: list[CaptionLine],
    slot: dict,
    brief: dict,
) -> list[CaptionLine]:
    """Keep the TikTok's cards and timing. Write those cards for this client."""
    if not cards:
        return []
    cards = _peel_glued_hook(cards)
    n = len(cards)
    out = []
    for i, card in enumerate(cards):
        joke = _keep_joke(card, n)
        if joke or not _has_client(brief, slot):
            text = clientize_on_screen(classic_copy(card.text), brief, slot)
        else:
            text = _rewrite_card(card, i, n, slot, brief)
        if _has_client(brief, slot) and not joke and VIRAL_LEAK.search(text):
            text = _rewrite_card(card, i, n, slot, brief)
        out.append(
            card.model_copy(
                update={"text": text, "kind": "overlay", "start": card.start, "end": card.end}
            )
        )
    return drop_unburnable(coalesce_cards(_drop_echoes(out)), brief, slot)


def _drop_echoes(cards: list[CaptionLine]) -> list[CaptionLine]:
    """A short leftover OCR card should not repeat a longer one."""
    ranked = sorted(cards, key=lambda c: -len(_letters(c.text)))
    keep: list[CaptionLine] = []
    seen: list[str] = []
    for card in ranked:
        n = _letters(card.text).lower()
        if n and any(n != other and n in other for other in seen):
            continue
        keep.append(card)
        seen.append(n)
    return sorted(keep, key=lambda c: (c.start, c.y_ratio))


def drop_unburnable(
    cards: list[CaptionLine],
    brief: dict | None = None,
    slot: dict | None = None,
) -> list[CaptionLine]:
    """Last gate: never burn clocks, glued OCR, or the viral's venue."""
    from videocopier.ocr import _ocr_junk_line, strip_junk_lines

    brief = brief or {}
    slot = slot or {}
    n = max(len(cards), 1)
    keep: list[CaptionLine] = []
    for card in cards:
        text = strip_junk_lines(classic_copy(card.text))
        if not text:
            continue
        joke = _keep_joke(card.model_copy(update={"text": text}), n)
        if not joke:
            lines = []
            for ln in text.split("\n"):
                if _ocr_junk_line(ln) or VIRAL_LEAK.search(ln):
                    continue
                lines.append(ln)
            text = "\n".join(lines)
        if not text or _ocr_junk_line(text):
            continue
        if not joke and VIRAL_LEAK.search(text):
            continue
        keep.append(card.model_copy(update={"text": text}))
    return keep
