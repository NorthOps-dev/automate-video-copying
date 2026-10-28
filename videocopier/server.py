from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path

from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from videocopier.auth import ADMIN_EMAIL, AuthMiddleware, credentials_ok, session_secret
from videocopier.board import BoardError, board_status, download_source, get_slot, list_approved
from videocopier.knowledge import load_brief, save_brief
from videocopier.models import JobSpec, JobState
from videocopier.pick import PickCancelled, folder_info, pick_file, pick_files, pick_folder
from videocopier.pipeline import ROOT, job_dir, load_state, save_state

STATIC = Path(__file__).resolve().parent / "static"
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

HOSTED = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_PUBLIC_DOMAIN"))
NO_STORE = {"Cache-Control": "no-store"}

app = FastAPI(title="NorthOps Prophet", version="0.1.0")
app.add_middleware(AuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret(),
    session_cookie="prophet",
    same_site="lax",
    https_only=HOSTED,
    max_age=60 * 60 * 24 * 14,
)


def _redirect_uri(request_base: str) -> str:
    return request_base.rstrip("/") + "/api/drive/callback"


@app.get("/login")
def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/", status_code=302)
    return FileResponse(STATIC / "login.html")


@app.post("/api/login")
async def login(request: Request):
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        body = await request.json()
        email = str(body.get("email") or "")
        password = str(body.get("password") or "")
    else:
        form = await request.form()
        email = str(form.get("email") or "")
        password = str(form.get("password") or "")
    if not credentials_ok(email, password):
        raise HTTPException(401, "Invalid email or password")
    request.session["user"] = ADMIN_EMAIL
    return {"ok": True, "email": ADMIN_EMAIL}


@app.post("/api/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    return {"email": request.session.get("user"), "hosted": HOSTED}


def _on_vercel() -> bool:
    return bool(os.environ.get("VERCEL"))


@app.get("/api/health")
def health():
    try:
        from videocopier.drive import drive_connected, find_local_google_drive, oauth_configured

        mounts = [str(p) for p in find_local_google_drive()]
        return {
            "ok": True,
            "drive_connected": drive_connected(),
            "drive_oauth_ready": oauth_configured(),
            "google_drive_desktop": mounts,
        }
    except ImportError:
        return {
            "ok": True,
            "drive_connected": False,
            "drive_oauth_ready": False,
            "google_drive_desktop": [],
        }


@app.post("/api/pick/folder")
def api_pick_folder():
    try:
        path = pick_folder()
    except PickCancelled:
        return {"cancelled": True}
    except Exception as exc:
        raise HTTPException(400, str(exc))
    return {"cancelled": False, **folder_info(path)}


@app.post("/api/pick/files")
def api_pick_files():
    try:
        paths = pick_files()
    except PickCancelled:
        return {"cancelled": True}
    except Exception as exc:
        raise HTTPException(400, str(exc))
    return {
        "cancelled": False,
        "paths": [str(p) for p in paths],
        "names": [p.name for p in paths],
        "videos": len(paths),
    }


INBOX = ROOT / ".work" / "inbox"


def _inbox_file(path: str) -> Path:
    dest = Path(path).expanduser().resolve()
    root = INBOX.resolve()
    if root not in dest.parents:
        raise HTTPException(400, "Unknown clip")
    if not dest.is_file():
        raise HTTPException(404, "Clip gone")
    return dest


@app.post("/api/clips/inspect")
async def api_inspect_clips(request: Request):
    form = await request.form()
    batch = uuid.uuid4().hex[:10]
    dest_dir = INBOX / batch
    dest_dir.mkdir(parents=True, exist_ok=True)
    from videocopier.media import inspect_clip, list_videos

    clips: list[dict] = []
    uploads = form.getlist("footage")
    for item in uploads:
        filename = getattr(item, "filename", None)
        if filename:
            dest = dest_dir / _safe_upload_name(filename)
            dest.write_bytes(await item.read())
        else:
            src = Path(str(item)).expanduser()
            if not src.is_file():
                continue
            dest = dest_dir / _safe_upload_name(src.name)
            dest.write_bytes(src.read_bytes())
        thumb = dest.with_suffix(".jpg")
        meta = inspect_clip(dest, thumb)
        clips.append(
            {
                "id": f"{batch}/{dest.name}",
                "name": dest.name,
                "path": str(dest),
                "thumb": f"/api/clips/thumb?path={quote(str(dest))}",
                **meta,
            }
        )
    if not clips:
        for path in list_videos(dest_dir):
            thumb = path.with_suffix(".jpg")
            meta = inspect_clip(path, thumb)
            clips.append(
                {
                    "id": f"{batch}/{path.name}",
                    "name": path.name,
                    "path": str(path),
                    "thumb": f"/api/clips/thumb?path={quote(str(path))}",
                    **meta,
                }
            )
    if not clips:
        raise HTTPException(400, "Upload at least one video.")
    return {"ok": True, "batch": batch, "clips": clips}


@app.get("/api/clips/thumb")
def api_clip_thumb(path: str = Query(...)):
    dest = _inbox_file(path)
    thumb = dest.with_suffix(".jpg")
    if not thumb.exists():
        raise HTTPException(404, "No thumbnail")
    return FileResponse(thumb, media_type="image/jpeg", headers=NO_STORE)


@app.get("/api/board/status")
def api_board_status():
    return board_status()


@app.get("/api/board/approved")
def api_board_approved():
    try:
        slots = list_approved()
    except BoardError as exc:
        raise HTTPException(502, str(exc))
    seen: dict[str, str] = {}
    for slot in slots:
        seen[slot["clientId"]] = slot["clientName"]
    return {
        "ok": True,
        "slots": slots,
        "clients": [{"id": cid, "name": name} for cid, name in seen.items()],
    }


@app.get("/api/board/slot/{slot_id}")
def api_board_slot(slot_id: str):
    try:
        slot = get_slot(slot_id)
    except BoardError as exc:
        raise HTTPException(502, str(exc))
    if not slot:
        raise HTTPException(404, "Unknown Board slot")
    brief = load_brief(slot.get("clientId") or "", slot.get("clientName") or "")
    return {"ok": True, "slot": slot, "brief": brief}


@app.get("/api/briefs/{client_id}")
def api_get_brief(client_id: str, name: str = Query(default="")):
    return load_brief(client_id, name)


@app.put("/api/briefs/{client_id}")
async def api_put_brief(client_id: str, request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "Brief must be a JSON object")
    return save_brief(client_id, body)


@app.get("/api/board/slot/{slot_id}/video")
def api_board_slot_video(slot_id: str):
    cache = Path(__file__).resolve().parent.parent / ".work" / "board_cache"
    dest = cache / f"board-{slot_id}.mp4"
    if not (dest.exists() and dest.stat().st_size > 10_000):
        try:
            dest = download_source(slot_id, cache)
        except BoardError as exc:
            raise HTTPException(502, str(exc))
    return FileResponse(dest, media_type="video/mp4", filename=f"original-{slot_id}.mp4")


@app.get("/api/local/video")
def api_local_video(path: str = Query(...)):
    dest = Path(path).expanduser().resolve()
    if dest.suffix.lower() not in {".mp4", ".mov", ".m4v", ".webm", ".mkv"}:
        raise HTTPException(400, "Not a video")
    if not dest.is_file():
        raise HTTPException(404, "Video not found")
    return FileResponse(dest, media_type="video/mp4", filename=dest.name)


@app.get("/api/board/thumb")
def api_board_thumb(src: str = Query(...)):
    if not src.startswith("/api/media/"):
        raise HTTPException(400, "Invalid thumbnail")
    from videocopier.board import authed

    try:
        payload = authed("GET", src, timeout=30)
    except BoardError as exc:
        raise HTTPException(502, str(exc))
    if not isinstance(payload, bytes):
        raise HTTPException(404, "No thumbnail")
    return Response(content=payload, media_type="image/jpeg")


@app.post("/api/pick/file")
def api_pick_file(kind: str = Query(default="video")):
    prompts = {
        "music": "Select your music track",
        "footage": "Select a raw footage video",
        "video": "Select the reference video",
    }
    prompt = prompts.get(kind, "Select a video")
    try:
        path = pick_file(prompt)
    except PickCancelled:
        return {"cancelled": True}
    except Exception as exc:
        raise HTTPException(400, str(exc))
    return {"cancelled": False, "path": str(path), "name": path.name}


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html", headers=NO_STORE)


@app.get("/app.js")
def app_js():
    return FileResponse(STATIC / "app.js", media_type="application/javascript", headers=NO_STORE)


@app.get("/styles.css")
def styles_css():
    return FileResponse(STATIC / "styles.css", media_type="text/css", headers=NO_STORE)


@app.get("/api/jobs/latest")
def latest_job():
    root = Path(__file__).resolve().parent.parent / ".work" / "jobs"
    newest = None
    newest_mtime = -1.0
    if root.exists():
        for path in root.glob("*/job.json"):
            try:
                state = load_state(path.parent.name)
            except Exception:
                continue
            if state.status != "done" or not state.output_mp4:
                continue
            mtime = path.stat().st_mtime
            if mtime > newest_mtime:
                newest = state
                newest_mtime = mtime
    return {"ok": True, "job": newest}


@app.get("/api/board/slot/{slot_id}/cards")
def api_board_cards(slot_id: str):
    cache = Path(__file__).resolve().parent.parent / ".work" / "board_cache"
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / f"board-{slot_id}.mp4"
    cards_path = cache / f"board-{slot_id}.cards.json"
    if cards_path.exists() and cards_path.stat().st_size > 20:
        try:
            return json.loads(cards_path.read_text())
        except json.JSONDecodeError:
            pass
    if not (dest.exists() and dest.stat().st_size > 10_000):
        try:
            dest = download_source(slot_id, cache)
        except BoardError as exc:
            raise HTTPException(502, str(exc))
    from videocopier.media import video_info
    from videocopier.ocr import ocr_captions

    cards = ocr_captions(dest, video_info(dest)["duration"])
    payload = {
        "ok": True,
        "cards": [{"text": c.text, "start": c.start, "end": c.end} for c in cards],
    }
    cards_path.write_text(json.dumps(payload))
    return payload


def _start_job(job_id: str) -> None:
    if _on_vercel():
        raise HTTPException(
            501,
            "Vercel cannot remake videos. Use the Railway / Prophet URL, or run it on a Mac.",
        )
    from videocopier.pipeline import run_job

    threading.Thread(target=run_job, args=(job_id,), daemon=True).start()


def _safe_upload_name(name: str) -> str:
    import re

    base = Path(name or "clip.mp4").name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base)[:120] or "clip.mp4"


@app.post("/api/jobs")
async def create_job(request: Request):
    ctype = request.headers.get("content-type", "")
    job_id = uuid.uuid4().hex[:12]
    work = job_dir(job_id)
    work.mkdir(parents=True, exist_ok=True)
    extra: list[str] = []
    reference = ""
    client_id = ""
    caption_mode = "client"
    music = None
    if "multipart/form-data" in ctype:
        form = await request.form()
        reference = str(form.get("reference") or "").strip()
        client_id = str(form.get("client_id") or "").strip()
        caption_mode = str(form.get("caption_mode") or "client")
        music = str(form.get("music") or "").strip() or None
        footage_dir = work / "footage_pick"
        footage_dir.mkdir(parents=True, exist_ok=True)
        uploads = form.getlist("footage")
        for item in uploads:
            filename = getattr(item, "filename", None)
            if not filename:
                path = str(item).strip()
                if path:
                    src = _inbox_file(path)
                    dest = footage_dir / _safe_upload_name(src.name)
                    dest.write_bytes(src.read_bytes())
                    extra.append(str(dest))
                continue
            dest = footage_dir / _safe_upload_name(filename)
            dest.write_bytes(await item.read())
            extra.append(str(dest))
        ref_file = form.get("reference_file")
        if ref_file is not None and getattr(ref_file, "filename", None):
            dest = work / "reference_src"
            dest.mkdir(parents=True, exist_ok=True)
            out = dest / _safe_upload_name(ref_file.filename)
            out.write_bytes(await ref_file.read())
            if not reference:
                reference = str(out)
    else:
        spec = JobSpec.model_validate(await request.json())
        if not spec.reference.strip():
            raise HTTPException(400, "Pick the approved format to remake.")
        if not spec.footage.strip() and not spec.footage_paths:
            raise HTTPException(400, "Upload the client's footage.")
        state = JobState(id=job_id, spec=spec, status="queued", step="queued")
        save_state(state)
        _start_job(job_id)
        return state

    if not reference:
        raise HTTPException(400, "Pick the approved format to remake.")
    if not extra:
        raise HTTPException(400, "Upload the client's footage.")
    spec = JobSpec(
        reference=reference,
        footage="",
        footage_paths=extra,
        music=music,
        caption_mode=caption_mode,  # type: ignore[arg-type]
        client_id=client_id,
    )
    state = JobState(id=job_id, spec=spec, status="queued", step="queued")
    save_state(state)
    _start_job(job_id)
    return state


@app.post("/api/jobs/upload")
async def create_job_upload(
    footage: str = Form(""),
    footage_paths: str | None = Form(None),
    caption_mode: str = Form("client"),
    music: str | None = Form(None),
    reference_url: str | None = Form(None),
    reference_file: UploadFile | None = File(None),
):
    job_id = uuid.uuid4().hex[:12]
    work = job_dir(job_id)
    work.mkdir(parents=True, exist_ok=True)
    reference = (reference_url or "").strip()
    if reference_file and reference_file.filename:
        dest = work / f"upload_{reference_file.filename}"
        dest.write_bytes(await reference_file.read())
        reference = str(dest)
    if not reference:
        raise HTTPException(400, "Pick the approved format to remake.")
    extra: list[str] = []
    if footage_paths:
        try:
            parsed = json.loads(footage_paths)
            if isinstance(parsed, list):
                extra = [str(p) for p in parsed if str(p).strip()]
        except json.JSONDecodeError:
            extra = [ln.strip() for ln in footage_paths.splitlines() if ln.strip()]
    if not (footage or "").strip() and not extra:
        raise HTTPException(400, "Pick the client's footage.")
    spec = JobSpec(reference=reference, footage=footage, footage_paths=extra, music=music or None, caption_mode=caption_mode)  # type: ignore[arg-type]
    state = JobState(id=job_id, spec=spec, status="queued", step="queued")
    save_state(state)
    _start_job(job_id)
    return state


@app.post("/api/jobs/{job_id}/approve")
async def approve_job(job_id: str, request: Request):
    try:
        state = load_state(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Unknown job")
    if state.status not in {"review", "error"}:
        raise HTTPException(400, "This remake is not waiting for approval.")
    body = await request.json()
    captions = body.get("captions") if isinstance(body, dict) else None
    if not isinstance(captions, list) or not any(str((c or {}).get("text") or "").strip() for c in captions if isinstance(c, dict)):
        raise HTTPException(400, "Approve at least one caption line.")
    state.status = "queued"
    state.step = "queued"
    state.error = None
    save_state(state)

    def _run() -> None:
        from videocopier.pipeline import burn_job

        burn_job(job_id, captions)

    if _on_vercel():
        raise HTTPException(501, "Vercel cannot remake videos.")
    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    try:
        return load_state(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Unknown job")


@app.get("/api/jobs/{job_id}/file/{kind}")
def job_file(job_id: str, kind: str):
    state = load_state(job_id)
    mapping = {
        "mp4": (state.output_mp4, "video/mp4", f"prophet-{job_id}.mp4"),
        "xml": (state.output_xml, "application/xml", f"prophet-{job_id}.fcpxml"),
        "cutlist": (state.output_cutlist, "application/json", f"prophet-{job_id}.json"),
    }
    if kind not in mapping:
        raise HTTPException(404, "Unknown file")
    path, mime, filename = mapping[kind]
    if not path or not Path(path).exists():
        raise HTTPException(404, "Not ready")
    return FileResponse(path, media_type=mime, filename=filename, headers=NO_STORE)


@app.get("/api/drive/status")
def drive_status():
    return health()


@app.get("/api/drive/connect")
def drive_connect(base: str = Query(default="http://127.0.0.1:8000")):
    from videocopier.drive import DriveError, start_oauth_url

    try:
        url = start_oauth_url(_redirect_uri(base))
    except DriveError as exc:
        raise HTTPException(400, str(exc))
    return {"url": url}


@app.get("/api/drive/callback")
def drive_callback(code: str | None = None, error: str | None = None):
    from videocopier.drive import finish_oauth

    if error:
        return RedirectResponse("/?drive=error")
    if not code:
        raise HTTPException(400, "Missing code")
    try:
        finish_oauth(code, "http://127.0.0.1:8000/api/drive/callback")
    except Exception as exc:
        raise HTTPException(400, str(exc))
    return RedirectResponse("/?drive=connected")


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
