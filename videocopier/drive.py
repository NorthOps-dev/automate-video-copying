from __future__ import annotations

import io
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME_CFG = Path.home() / ".videocopier"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
TOKEN_PATHS = [ROOT / "token.json", HOME_CFG / "token.json"]
SECRET_PATHS = [
    ROOT / "client_secret.json",
    ROOT / "credentials.json",
    HOME_CFG / "client_secret.json",
    HOME_CFG / "credentials.json",
]


class DriveError(RuntimeError):
    pass


def extract_drive_id(value: str) -> tuple[str, str] | None:
    """Return ('file'|'folder', id) if this looks like a Google Drive URL or id."""
    text = value.strip()
    folder = re.search(r"/drive/folders/([a-zA-Z0-9_-]+)", text)
    if folder:
        return "folder", folder.group(1)
    file_m = re.search(r"/file/d/([a-zA-Z0-9_-]+)", text)
    if file_m:
        return "file", file_m.group(1)
    open_m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", text)
    if open_m and "google.com" in text:
        return "file", open_m.group(1)
    if re.fullmatch(r"[a-zA-Z0-9_-]{25,}", text) and " " not in text:
        return "unknown", text
    return None


def is_drive_ref(value: str) -> bool:
    text = value.strip().lower()
    return "drive.google.com" in text or "docs.google.com" in text or text.startswith("gdrive:")


def find_local_google_drive() -> list[Path]:
    cloud = Path.home() / "Library" / "CloudStorage"
    if not cloud.exists():
        return []
    return sorted(p for p in cloud.glob("GoogleDrive-*") if p.is_dir())


def _secret_path() -> Path | None:
    for p in SECRET_PATHS:
        if p.exists():
            return p
    return None


def _token_path() -> Path:
    HOME_CFG.mkdir(parents=True, exist_ok=True)
    return HOME_CFG / "token.json"


def load_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_file = next((p for p in TOKEN_PATHS if p.exists()), None)
    creds = None
    if token_file:
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _token_path().write_text(creds.to_json())
        return creds
    return None


def start_oauth_url(redirect_uri: str) -> str:
    from google_auth_oauthlib.flow import Flow

    secret = _secret_path()
    if not secret:
        raise DriveError(
            "No Google OAuth client found. Put client_secret.json in ~/.videocopier/ "
            "or the project root, or just paste a public Drive link / local Drive folder path."
        )
    flow = Flow.from_client_secrets_file(str(secret), scopes=SCOPES, redirect_uri=redirect_uri)
    url, _state = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    HOME_CFG.mkdir(parents=True, exist_ok=True)
    (HOME_CFG / "oauth_redirect.json").write_text(json.dumps({"redirect_uri": redirect_uri}))
    return url


def finish_oauth(code: str, redirect_uri: str):
    from google_auth_oauthlib.flow import Flow

    secret = _secret_path()
    if not secret:
        raise DriveError("Missing client_secret.json")
    flow = Flow.from_client_secrets_file(str(secret), scopes=SCOPES, redirect_uri=redirect_uri)
    flow.fetch_token(code=code)
    creds = flow.credentials
    _token_path().write_text(creds.to_json())
    return creds


def drive_connected() -> bool:
    try:
        return load_credentials() is not None
    except Exception:
        return False


def oauth_configured() -> bool:
    return _secret_path() is not None


def _service(creds=None):
    from googleapiclient.discovery import build

    creds = creds or load_credentials()
    if not creds:
        raise DriveError("Google Drive is not connected.")
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _download_file(service, file_id: str, dest: Path) -> Path:
    from googleapiclient.http import MediaIoBaseDownload

    dest.parent.mkdir(parents=True, exist_ok=True)
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(dest, "wb")
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return dest


def download_drive_file(file_id: str, dest: Path) -> Path:
    service = _service()
    meta = service.files().get(fileId=file_id, fields="id,name,mimeType").execute()
    name = meta.get("name") or f"{file_id}.mp4"
    path = dest / name if dest.is_dir() else dest
    return _download_file(service, file_id, path)


def download_drive_folder(folder_id: str, dest: Path, progress=lambda m: None) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    service = _service()
    queue = [(folder_id, dest)]
    video_mimes = ("video/",)
    while queue:
        fid, folder = queue.pop(0)
        page_token = None
        while True:
            resp = (
                service.files()
                .list(
                    q=f"'{fid}' in parents and trashed=false",
                    fields="nextPageToken, files(id, name, mimeType)",
                    pageSize=200,
                    pageToken=page_token,
                )
                .execute()
            )
            for f in resp.get("files", []):
                mime = f.get("mimeType") or ""
                name = f.get("name") or f["id"]
                if mime == "application/vnd.google-apps.folder":
                    queue.append((f["id"], folder / name))
                elif mime.startswith(video_mimes) or Path(name).suffix.lower() in {
                    ".mp4",
                    ".mov",
                    ".m4v",
                    ".webm",
                    ".mkv",
                }:
                    progress(f"Downloading {name} from Drive…")
                    _download_file(service, f["id"], folder / name)
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    return dest


def try_public_download(url: str, dest: Path) -> Path:
    """Public 'anyone with the link' files/folders via gdown — no OAuth."""
    import gdown

    dest.mkdir(parents=True, exist_ok=True)
    kind = extract_drive_id(url)
    if kind and kind[0] == "folder":
        gdown.download_folder(url=url, output=str(dest), quiet=True, use_cookies=False, remaining_ok=True)
        return dest
    out = dest / "reference_drive"
    gdown.download(url=url, output=str(out), quiet=True, fuzzy=True)
    # gdown may add an extension
    matches = list(dest.glob("reference_drive*"))
    if matches:
        return matches[0]
    if out.exists():
        return out
    raise DriveError("Could not download that public Drive link.")
