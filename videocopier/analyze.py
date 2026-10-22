from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from videocopier.captions import words_to_lines
from videocopier.embed import embed_frame
from videocopier.ocr import ocr_captions
from videocopier.media import (
    detect_cuts,
    extract_audio_wav,
    frame_quality,
    motion_stats,
    read_frame_bgr,
    shot_bounds,
    video_info,
)
from videocopier.models import Blueprint, Shot
from videocopier.transcribe import transcribe


def _beats_from_wav(wav_path: Path) -> tuple[float | None, list[float]]:
    try:
        audio, sr = sf.read(str(wav_path), always_2d=False)
    except Exception:
        return None, []
    if getattr(audio, "ndim", 1) > 1:
        audio = audio.mean(axis=1)
    if audio.size < sr:
        return None, []
    audio = audio.astype(np.float32)
    hop = 512
    window = 2048
    if audio.size < window:
        return None, []
    rms = []
    for i in range(0, audio.size - window, hop):
        chunk = audio[i : i + window]
        rms.append(float(np.sqrt(np.mean(chunk * chunk))))
    env = np.array(rms, dtype=np.float32)
    env = env - np.median(env)
    env = np.clip(env, 0, None)
    if env.max() <= 0:
        return None, []
    env = env / env.max()
    # Peak-pick on the RMS envelope as a cheap beat grid.
    min_gap = max(int(0.25 * sr / hop), 2)
    peaks: list[int] = []
    for i in range(1, len(env) - 1):
        if env[i] > 0.35 and env[i] >= env[i - 1] and env[i] >= env[i + 1]:
            if not peaks or (i - peaks[-1]) >= min_gap:
                peaks.append(i)
    beats = [round(p * hop / sr, 3) for p in peaks]
    bpm = None
    if len(beats) >= 4:
        gaps = np.diff(beats)
        gaps = gaps[(gaps > 0.25) & (gaps < 1.5)]
        if len(gaps):
            bpm = float(np.clip(60.0 / np.median(gaps), 60, 200))
    return bpm, beats


def _role_for_shot(index: int, n: int, start: float, duration_total: float, has_face: bool, energy: float) -> str:
    if index == 0 or start < 3.0:
        return "hook"
    if start > max(duration_total - 3.5, duration_total * 0.85):
        return "cta"
    if has_face:
        return "talking_head"
    if energy < 0.1:
        return "text_card"
    return "broll"


def analyze_reference(path: Path, work: Path, progress=lambda m: None) -> Blueprint:
    work.mkdir(parents=True, exist_ok=True)
    info = video_info(path)
    progress("Detecting cuts in the reference…")
    cuts = detect_cuts(path, work)
    bounds = shot_bounds(cuts, info["duration"])
    progress(f"Found {len(bounds)} shots")

    progress("Transcribing reference (captions + script)…")
    transcript, words = transcribe(path, work / "ref_audio.wav")
    speech_caps = words_to_lines(words)
    overlay_caps = ocr_captions(path, info["duration"], progress=progress)
    captions = overlay_caps or speech_caps

    progress("Reading music energy…")
    bpm, beats = None, []
    wav = extract_audio_wav(path, work / "ref_audio.wav")
    if wav:
        bpm, beats = _beats_from_wav(wav)

    shots: list[Shot] = []
    for i, (start, end) in enumerate(bounds):
        dur = end - start
        mid = start + dur * 0.35
        try:
            frame = read_frame_bgr(path, mid)
            quality, luma, sat, has_face, _face_x = frame_quality(frame)
            embedding = embed_frame(frame)
        except Exception:
            quality, luma, sat, has_face = 0.4, 0.5, 0.4, False
            embedding = []
        energy, motion = motion_stats(path, start, dur)
        spoken = " ".join(w.text for w in words if w.start >= start - 0.05 and w.start < end).strip()
        shots.append(
            Shot(
                index=i,
                start=round(start, 3),
                end=round(end, 3),
                duration=round(dur, 3),
                role=_role_for_shot(i, len(bounds), start, info["duration"], has_face, energy),
                motion=motion,
                energy=round(energy, 4),
                mean_luma=round(luma, 4),
                saturation=round(sat, 4),
                has_face=has_face,
                transcript=spoken,
                embedding=embedding,
            )
        )

    return Blueprint(
        path=str(path),
        duration=round(info["duration"], 3),
        width=info["width"],
        height=info["height"],
        fps=round(info["fps"], 3),
        bpm=round(bpm, 1) if bpm else None,
        beats=beats,
        transcript=transcript,
        captions=captions,
        shots=shots,
    )
