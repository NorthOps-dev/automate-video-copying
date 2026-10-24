from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from videocopier.auth import ADMIN_EMAIL, ADMIN_PASSWORD

BOARD_URL = os.environ.get("NORTHOPS_BOARD_URL", "https://board-production-bd79.up.railway.app").rstrip("/")
APPROVED_STATUSES = {"Approved", "Shot", "Edited", "Scheduled", "Published"}
TOKEN_PATH = Path.home() / ".northops-prophet" / "board_token"


class BoardError(RuntimeError):
    pass


def _request(method: str, path: str, token: str | None = None, body: dict | None = None, timeout: int = 30) -> dict | bytes:
    url = path if path.startswith("http") else BOARD_URL + path
    data = None
    headers = {"User-Agent": "NorthOps-Prophet/0.1", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            if "json" in ctype or raw[:1] in {b"{", b"["}:
                return json.loads(raw.decode("utf-8"))
            return raw
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:400]
        try:
            parsed = json.loads(detail)
            detail = parsed.get("error") or parsed.get("detail") or detail
        except Exception:
            pass
        raise BoardError(f"{exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise BoardError(f"Could not reach the Board at {BOARD_URL}") from exc


def _save_token(token: str) -> None:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(token)


def login(email: str | None = None, password: str | None = None) -> str:
    payload = _request(
        "POST",
        "/api/login",
        body={"email": email or ADMIN_EMAIL, "password": password or ADMIN_PASSWORD},
    )
    if not isinstance(payload, dict) or not payload.get("token"):
        raise BoardError("Board login did not return a token.")
    token = str(payload["token"])
    _save_token(token)
    return token


def _token() -> str:
    if TOKEN_PATH.exists():
        existing = TOKEN_PATH.read_text().strip()
        if existing:
            return existing
    return login()


def authed(method: str, path: str, **kwargs):
    token = _token()
    try:
        return _request(method, path, token=token, **kwargs)
    except BoardError as exc:
        if str(exc).startswith("401"):
            token = login()
            return _request(method, path, token=token, **kwargs)
        raise


def board_status() -> dict:
    try:
        me = authed("GET", "/api/me")
        user = me.get("user") if isinstance(me, dict) else None
        return {"ok": True, "url": BOARD_URL, "user": user}
    except BoardError as exc:
        return {"ok": False, "url": BOARD_URL, "error": str(exc)}


def list_approved() -> list[dict]:
    clients = authed("GET", "/api/clients")
    rows = clients.get("clients") if isinstance(clients, dict) else []
    out: list[dict] = []
    for client in rows or []:
        cid = client.get("id")
        if not cid or client.get("exampleSeed"):
            continue
        try:
            detail = authed("GET", f"/api/clients/{cid}")
        except BoardError:
            continue
        if not isinstance(detail, dict):
            continue
        for slot in detail.get("slots") or []:
            if slot.get("status") not in APPROVED_STATUSES:
                continue
            if not (slot.get("sourceVideo") or slot.get("basedOnUrl")):
                continue
            thumbs = slot.get("adaptations") or []
            thumb = thumbs[0].get("src") if thumbs and isinstance(thumbs[0], dict) else None
            script = slot.get("scriptLines") or []
            brands = []
            if isinstance(script, list):
                for item in script:
                    if isinstance(item, dict):
                        text = (item.get("brand") or item.get("original") or "").strip()
                        if text:
                            brands.append(text)
            out.append(
                {
                    "id": slot.get("id"),
                    "clientId": cid,
                    "clientName": client.get("name") or cid,
                    "slotNumber": slot.get("slotNumber"),
                    "status": slot.get("status"),
                    "hook": (slot.get("hook") or slot.get("title") or "Untitled").strip(),
                    "caption": (slot.get("caption") or "").strip(),
                    "basedOn": (slot.get("basedOn") or "").strip(),
                    "basedOnUrl": slot.get("basedOnUrl") or "",
                    "sourceVideo": slot.get("sourceVideo") or "",
                    "shotDirection": (slot.get("shotDirection") or "").strip(),
                    "hasScript": bool(brands or (slot.get("clientScript") or "").strip()),
                    "scriptPreview": brands[:4],
                    "thumb": thumb,
                    "platform": slot.get("platform") or "",
                }
            )
    out.sort(key=lambda r: (r.get("clientName") or "", r.get("slotNumber") or 0))
    return out


def get_slot(slot_id: str) -> dict | None:
    """Full Board slot plus client name — includes the remake script."""
    clients = authed("GET", "/api/clients")
    rows = clients.get("clients") if isinstance(clients, dict) else []
    for client in rows or []:
        cid = client.get("id")
        if not cid or client.get("exampleSeed"):
            continue
        try:
            detail = authed("GET", f"/api/clients/{cid}")
        except BoardError:
            continue
        if not isinstance(detail, dict):
            continue
        for slot in detail.get("slots") or []:
            if slot.get("id") != slot_id:
                continue
            packed = dict(slot)
            packed["clientId"] = cid
            packed["clientName"] = client.get("name") or cid
            return packed
    return None


def find_slot(slot_id: str) -> dict | None:
    return get_slot(slot_id)


def download_source(slot_id: str, dest_dir: Path, progress=lambda m: None) -> Path:
    slot = find_slot(slot_id)
    if not slot:
        raise BoardError(f"No approved Board video matches {slot_id}.")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"board-{slot_id}.mp4"
    source = slot.get("sourceVideo") or ""
    if source:
        progress("Downloading approved video from the Board…")
        token = _token()
        url = source if source.startswith("http") else BOARD_URL + source
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {token}", "User-Agent": "NorthOps-Prophet/0.1"},
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                dest.write_bytes(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                token = login()
                req = urllib.request.Request(
                    url,
                    headers={"Authorization": f"Bearer {token}", "User-Agent": "NorthOps-Prophet/0.1"},
                )
                with urllib.request.urlopen(req, timeout=180) as resp:
                    dest.write_bytes(resp.read())
            else:
                raise BoardError(f"Board media download failed ({exc.code})") from exc
        if dest.exists() and dest.stat().st_size > 10_000:
            return dest
    url = slot.get("basedOnUrl") or ""
    if url:
        from videocopier.sources import _yt_dlp_download

        progress("Board file missing — downloading the original TikTok…")
        return _yt_dlp_download(url, dest_dir)
    raise BoardError("That Board slot has no source video.")
