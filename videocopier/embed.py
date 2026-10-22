from __future__ import annotations

import logging
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image

log = logging.getLogger("videocopier")

_CLIP_OK: bool | None = None
_CLIP_MODEL = None
_CLIP_PREPROCESS = None


def cosine(a: list[float] | np.ndarray, b: list[float] | np.ndarray) -> float:
    x = np.asarray(a, dtype=np.float32)
    y = np.asarray(b, dtype=np.float32)
    if x.size == 0 or y.size == 0 or x.size != y.size:
        return 0.0
    denom = float(np.linalg.norm(x) * np.linalg.norm(y))
    if denom == 0:
        return 0.0
    return float(np.clip(np.dot(x, y) / denom, -1.0, 1.0))


def histogram_embedding(bgr: np.ndarray) -> list[float]:
    img = cv2.resize(bgr, (64, 64), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1, 2], None, [12, 8, 8], [0, 180, 0, 256, 0, 256])
    hist = cv2.normalize(hist, hist).flatten().astype(np.float32)
    return hist.tolist()


def clip_available() -> bool:
    global _CLIP_OK
    if _CLIP_OK is not None:
        return _CLIP_OK
    try:
        import open_clip  # noqa: F401
        import torch  # noqa: F401

        _CLIP_OK = True
    except Exception:
        _CLIP_OK = False
        log.info("open-clip/torch not available — using color histogram matching")
    return _CLIP_OK


@lru_cache(maxsize=1)
def _load_clip():
    import open_clip
    import torch

    device = "cpu"
    if torch.backends.mps.is_available():
        device = "mps"
    elif torch.cuda.is_available():
        device = "cuda"
    model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-B-32", pretrained="openai"
    )
    model.eval()
    model.to(device)
    return model, preprocess, device


def clip_embedding(bgr: np.ndarray) -> list[float]:
    import torch

    model, preprocess, device = _load_clip()
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    image = preprocess(Image.fromarray(rgb)).unsqueeze(0).to(device)
    with torch.no_grad():
        feat = model.encode_image(image)
        feat = feat / feat.norm(dim=-1, keepdim=True)
    return feat.squeeze(0).cpu().numpy().astype(np.float32).tolist()


def embed_frame(bgr: np.ndarray) -> list[float]:
    if clip_available():
        try:
            return clip_embedding(bgr)
        except Exception as exc:
            log.warning("CLIP embed failed (%s); falling back to histogram", exc)
    return histogram_embedding(bgr)
