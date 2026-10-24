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
    text = (text or "").replace("—", ",").replace("–", ",").replace(" - ", ", ")
    lines = [re.sub(r"\s+", " ", ln).strip(" ,") for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def _similar_text(a: str, b: str) -> bool:
    na = re.sub(r"[^a-z0-9]+", "", a.lower())
    nb = re.sub(r"[^a-z0-9]+", "", b.lower())
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    wa, wb = set(re.findall(r"[a-z0-9]+", a.lower())), set(re.findall(r"[a-z0-9]+", b.lower()))
    return bool(wa and wb and len(wa & wb) / len(wa | wb) >= 0.7)


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
            longer = text if len(text) >= len(prev.text) else prev.text
            merged[-1] = prev.model_copy(update={"end": max(prev.end, card.end), "text": longer})
        else:
            merged.append(card.model_copy(update={"text": text, "kind": "overlay"}))
    out: list[CaptionLine] = []
    for i, card in enumerate(merged):
        end = card.end
        if i + 1 < len(merged) and end > merged[i + 1].start:
            end = merged[i + 1].start
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


def _usable_script(slot: dict) -> list[str]:
    rows: list[str] = []
    for item in slot.get("scriptLines") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("brand") or item.get("original") or "").strip()
        if len(_letters(text)) >= 8:
            rows.append(text)
    body = (slot.get("clientScript") or "").strip()
    if not rows and body:
        rows = [p.strip() for p in body.split("\n") if len(_letters(p)) >= 8]
    return rows


def _role(card: CaptionLine, index: int, n: int) -> str:
    t = card.text.lower()
    if TRY_RE.search(t):
        return "try"
    if REACT_RE.search(t) and len(card.text) < 60:
        return "react"
    if index == n - 1 or CTA_RE.search(t):
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


def _hook_card(slot: dict, brief: dict, n_lines: int) -> str:
    hook = (slot.get("hook") or "").strip() or f"New in {_city(brief, slot) or 'town'}!!"
    kind = _kind(brief)
    kind_label = " ".join(w.capitalize() for w in kind.split()) if kind else "Spot"
    lines = [hook]
    if n_lines >= 2:
        lines.append(f"{kind_label} Alert!")
    return classic_copy("\n".join(lines[:2]))


def _about_card(brief: dict, slot: dict, n_lines: int) -> str:
    name = _name(brief, slot)
    kind = _kind(brief)
    city = _city(brief, slot)
    one = (brief.get("one_liner") or "").strip()
    what = _short(brief.get("what") or "", 12)
    lines = []
    if name and kind:
        lines.append(f"{name} is a {kind.lower()}")
    elif name:
        lines.append(name)
    if city:
        lines.append(f"in {city}")
    elif one:
        lines.append(classic_copy(one).split(",")[0])
    if not lines:
        lines = [name or "this place"]
    return classic_copy("\n".join(lines[:2]))


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


def _cta_card(original: str, brief: dict, slot: dict) -> str:
    name = _name(brief, slot) or "this place"
    cta = (brief.get("cta") or "").strip()
    kept: list[str] = []
    for line in original.split("\n"):
        line = line.strip()
        if not line:
            continue
        if _venue_line(line):
            kept.append(name)
        else:
            kept.append(line)
    if not any(_venue_line(ln) or ln == name for ln in kept):
        kept.append(name)
    if cta and name.lower() not in " ".join(kept).lower():
        kept[-1] = name
    if not any("recommend" in ln.lower() or "visit" in ln.lower() or "come" in ln.lower() for ln in kept):
        kept = ["definitely recommend", "to visit this place!", name]
    return "\n".join(kept[:4])


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
    """Keep the sentence on the TikTok. Swap drinks / city / venue for the client."""
    drink, plural = _hero_drink(brief)
    kind = _kind(brief)
    city = _city(brief, slot)
    name = _name(brief, slot)
    out = text
    swaps = [
        (r"\bmargaritas\b", plural),
        (r"\bmargarita\b", drink),
        (r"\bcocktails\b", plural),
        (r"\bcocktail\b", drink),
        (r"\bbeers\b", plural),
        (r"\bbeer\b", drink),
        (r"\bshots\b", plural),
        (r"\bwine\b", drink),
        (r"\btequila\b", drink),
        (r"\bvodka\b", drink),
        (r"\bbooze\b", "kava"),
        (r"\bliquor\b", "kava"),
        (r"\balcohol\b", "kava"),
        (r"\bRestaurant Alert\b", f"{kind.title()} Alert"),
        (r"\brestaurants\b", f"{kind}s"),
        (r"\brestaurant\b", kind),
        (r"\bValley Goat\b", name or "MeloMelo"),
    ]
    for pat, repl in swaps:
        if repl:
            out = re.sub(pat, repl, out, flags=re.I)
    if city:
        out = re.sub(r"\bSunnyvale\b", city, out, flags=re.I)
    return classic_copy(out)


def remake_for_client(
    cards: list[CaptionLine],
    slot: dict,
    brief: dict,
) -> list[CaptionLine]:
    """Same words, cards, and timing as the TikTok."""
    if not cards:
        return []
    return coalesce_cards(
        [card.model_copy(update={"text": classic_copy(card.text), "kind": "overlay"}) for card in cards]
    )
