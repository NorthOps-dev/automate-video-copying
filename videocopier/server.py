from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from videocopier.auth import ADMIN_EMAIL, AuthMiddleware, credentials_ok, session_secret
from videocopier.drive import (
    DriveError,
    drive_connected,
    find_local_google_drive,
    finish_oauth,
    oauth_configured,
    start_oauth_url,
)
from videocopier.models import JobSpec, JobState
from videocopier.pick import PickCancelled, folder_info, pick_file, pick_folder
from videocopier.pipeline import job_dir, load_state, run_job, save_state

STATIC = Path(__file__).resolve().parent / "static"
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

app = FastAPI(title="NorthOps Prophet", version="0.1.0")
app.add_middleware(AuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret(),
    session_cookie="prophet",
    same_site="lax",
    https_only=False,
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
    return {"email": request.session.get("user")}


@app.get("/api/health")
def health():
    mounts = [str(p) for p in find_local_google_drive()]
    return {
        "ok": True,
        "drive_connected": drive_connected(),
        "drive_oauth_ready": oauth_configured(),
        "google_drive_desktop": mounts,
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


@app.post("/api/jobs")
async def create_job(spec: JobSpec):
    job_id = uuid.uuid4().hex[:12]
    state = JobState(id=job_id, spec=spec, status="queued", step="queued")
    save_state(state)
    threading.Thread(target=run_job, args=(job_id,), daemon=True).start()
    return state


@app.post("/api/jobs/upload")
async def create_job_upload(
    footage: str = Form(...),
    caption_mode: str = Form("auto"),
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
        raise HTTPException(400, "Provide a reference file or URL")
    spec = JobSpec(reference=reference, footage=footage, music=music or None, caption_mode=caption_mode)  # type: ignore[arg-type]
    state = JobState(id=job_id, spec=spec, status="queued", step="queued")
    save_state(state)
    threading.Thread(target=run_job, args=(job_id,), daemon=True).start()
    return state


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
    return FileResponse(path, media_type=mime, filename=filename)


@app.get("/api/drive/status")
def drive_status():
    return health()


@app.get("/api/drive/connect")
def drive_connect(base: str = Query(default="http://127.0.0.1:8000")):
    try:
        url = start_oauth_url(_redirect_uri(base))
    except DriveError as exc:
        raise HTTPException(400, str(exc))
    return {"url": url}


@app.get("/api/drive/callback")
def drive_callback(code: str | None = None, error: str | None = None):
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
