from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRIEFS = ROOT / "clients"

DEFAULTS = {
    "id": "",
    "name": "",
    "one_liner": "",
    "location": "",
    "what": "",
    "voice": "",
    "products": [],
    "cta": "",
    "avoid": "",
    "notes": "",
}


def _path(client_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in client_id)
    return BRIEFS / f"{safe}.json"


def load_brief(client_id: str, name: str = "") -> dict:
    path = _path(client_id)
    data = dict(DEFAULTS)
    data["id"] = client_id
    data["name"] = name
    if path.exists():
        try:
            saved = json.loads(path.read_text())
            if isinstance(saved, dict):
                data.update({k: saved.get(k, data[k]) for k in DEFAULTS})
                data["id"] = client_id
                if name and not data.get("name"):
                    data["name"] = name
        except json.JSONDecodeError:
            pass
    return data


def save_brief(client_id: str, payload: dict) -> dict:
    BRIEFS.mkdir(parents=True, exist_ok=True)
    current = load_brief(client_id, str(payload.get("name") or ""))
    for key in DEFAULTS:
        if key == "id":
            continue
        if key in payload:
            current[key] = payload[key]
    current["id"] = client_id
    _path(client_id).write_text(json.dumps(current, indent=2) + "\n")
    return current


def brief_blurb(brief: dict) -> str:
    bits = [
        brief.get("name") or "",
        brief.get("one_liner") or "",
        brief.get("location") or "",
        brief.get("what") or "",
        brief.get("voice") or "",
        brief.get("cta") or "",
    ]
    return " · ".join(b for b in bits if b)
