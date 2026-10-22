from __future__ import annotations

import logging
from pathlib import Path

from videocopier.media import extract_audio_wav
from videocopier.models import Word

log = logging.getLogger("videocopier")

_MODEL = None


def _load_whisper():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    try:
        from faster_whisper import WhisperModel

        _MODEL = WhisperModel("base", device="cpu", compute_type="int8")
        return _MODEL
    except Exception as exc:
        log.info("faster-whisper unavailable (%s)", exc)
        return None


def transcribe(video: Path, wav_dest: Path) -> tuple[str, list[Word]]:
    wav = extract_audio_wav(video, wav_dest)
    if not wav:
        return "", []
    model = _load_whisper()
    if model is None:
        return "", []
    try:
        import numpy as np
        import soundfile as sf
        from scipy.signal import resample_poly

        audio, sr = sf.read(str(wav), always_2d=False)
        if getattr(audio, "ndim", 1) > 1:
            audio = audio.mean(axis=1)
        audio = np.asarray(audio, dtype=np.float32)
        if sr != 16000 and sr > 0:
            audio = resample_poly(audio, 16000, sr).astype(np.float32)
        segments, _info = model.transcribe(audio, word_timestamps=True)
    except Exception as exc:
        log.warning("Transcription failed: %s", exc)
        return "", []
    words: list[Word] = []
    parts: list[str] = []
    for seg in segments:
        if seg.text:
            parts.append(seg.text.strip())
        for w in getattr(seg, "words", None) or []:
            text = (w.word or "").strip()
            if not text:
                continue
            words.append(Word(text=text, start=float(w.start or 0), end=float(w.end or w.start or 0)))
    return " ".join(parts).strip(), words
