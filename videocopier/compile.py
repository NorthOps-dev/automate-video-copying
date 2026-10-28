from __future__ import annotations

from pathlib import Path

from videocopier.captions import build_ass, render_overlays, words_to_lines
from videocopier.fonts import ensure_caption_font
from videocopier.media import concat_file_line, ffmpeg_bin, has_audio, run, video_info
from videocopier.models import Blueprint, CaptionLine, CutList, Slot
from videocopier.rewrite import drop_unburnable
from videocopier.transcribe import transcribe

WIDTH = 1080
HEIGHT = 1920
FPS = 30


def _layout_filter(path: Path, face_x: float) -> str:
    info = video_info(path)
    ow = max(info["width"], 1)
    oh = max(info["height"], 1)
    if ow / oh > 0.72:
        # Landscape iPhone clip → 9:16 like TikTok: full clip, blurred fill behind.
        return (
            f"split[bg][fg];[bg]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},boxblur=24:1[bg];"
            f"[fg]scale={WIDTH}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,"
            f"fps={FPS},setsar=1,format=yuv420p"
        )
    scale = max(WIDTH / ow, HEIGHT / oh)
    sw = max(int(round(ow * scale)), WIDTH)
    sh = max(int(round(oh * scale)), HEIGHT)
    cx = int(round(sw * face_x - WIDTH / 2))
    cx = max(0, min(cx, sw - WIDTH))
    # Center the 9:16 window. A 0.42 top bias turned hanging lights into the hook.
    cy = int(round((sh - HEIGHT) / 2))
    cy = max(0, min(cy, sh - HEIGHT))
    return f"scale={sw}:{sh},crop={WIDTH}:{HEIGHT}:{cx}:{cy},fps={FPS},setsar=1,format=yuv420p"


def _render_filled(slot: Slot, dest: Path) -> None:
    assert slot.source_path and slot.source_in is not None and slot.source_out is not None
    duration = max(slot.duration, 0.1)
    src_dur = max(slot.source_out - slot.source_in, 0.1)
    short = duration - src_dur
    vf = _layout_filter(Path(slot.source_path), slot.face_x)
    # Play the real clip. If it's short, loop the take — never freeze a still.
    loop = ["-stream_loop", "-1"] if short > 0.05 else []
    audio_in = [
        *loop,
        "-ss",
        f"{slot.source_in:.3f}",
        "-i",
        slot.source_path,
        "-t",
        f"{duration:.3f}",
    ]
    cmd = [ffmpeg_bin(), "-hide_banner", "-y", *audio_in]
    uses_complex = "split[" in vf
    if has_audio(Path(slot.source_path)):
        af = "aresample=48000,aformat=channel_layouts=stereo,apad=pad_dur=2"
        if uses_complex:
            cmd += ["-filter_complex", vf, "-af", af]
        else:
            cmd += ["-vf", vf, "-af", af]
    else:
        cmd += [
            "-f",
            "lavfi",
            "-t",
            f"{duration:.3f}",
            "-i",
            "anullsrc=r=48000:cl=stereo",
        ]
        if uses_complex:
            cmd += ["-filter_complex", vf, "-map", "0:v", "-map", "1:a"]
        else:
            cmd += ["-vf", vf, "-map", "0:v:0", "-map", "1:a:0"]
    cmd += [
        "-t",
        f"{duration:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(dest),
    ]
    run(cmd)


def _render_slate(slot: Slot, dest: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    font_choice = ensure_caption_font()
    img = Image.new("RGB", (WIDTH, HEIGHT), (10, 10, 12))
    draw = ImageDraw.Draw(img)
    title = ImageFont.truetype(str(font_choice.path), size=72, index=font_choice.index)
    body = ImageFont.truetype(str(font_choice.path), size=40, index=font_choice.index)
    lines = [
        ("FILM THIS", title),
        (slot.role.replace("_", " ").upper(), body),
        (f"{max(slot.duration, 0.1):.1f}s", body),
    ]
    y = HEIGHT * 0.4
    for text, face in lines:
        bbox = draw.textbbox((0, 0), text, font=face)
        tw = bbox[2] - bbox[0]
        draw.text(((WIDTH - tw) / 2, y), text, font=face, fill=(244, 244, 245))
        y += face.size + 18
    png = dest.with_suffix(".png")
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(png)
    duration = max(slot.duration, 0.1)
    run(
        [
            ffmpeg_bin(),
            "-hide_banner",
            "-y",
            "-loop",
            "1",
            "-i",
            str(png),
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(dest),
        ]
    )


def _dodge_faces(captions: list[CaptionLine], video: Path) -> list[CaptionLine]:
    """Park alert cards at the top. Don't copy a restaurant's mid-frame y onto a close-up face."""
    if not captions:
        return captions
    boxes = [c for c in captions if c.face == "box"]
    split: list[CaptionLine] = []
    for card in captions:
        if card.face == "box":
            split.append(card)
            continue
        overlap = [b for b in boxes if b.start < card.end - 0.05 and b.end > card.start + 0.05]
        hook_end = max((b.end for b in overlap), default=0.0)
        if overlap and hook_end < card.end - 0.7 and hook_end > card.start + 0.4:
            split.append(card.model_copy(update={"end": round(hook_end, 3)}))
            split.append(card.model_copy(update={"start": round(hook_end, 3), "y_ratio": 0.13, "face": "classic"}))
        else:
            split.append(card)
    placed: list[CaptionLine] = []
    for card in split:
        y = card.y_ratio
        if card.face == "box":
            y = 0.10
        else:
            overlap = [b for b in boxes if b.start < card.end - 0.05 and b.end > card.start + 0.05]
            if overlap:
                hook_h = 0.052 * (overlap[0].text.count("\n") + 1) + 0.048
                y = 0.10 + hook_h
        placed.append(card.model_copy(update={"y_ratio": round(float(y), 3)}))
    ordered = sorted(placed, key=lambda c: (c.start, c.y_ratio))
    for i, card in enumerate(ordered):
        if card.face == "box":
            continue
        for prev in ordered[:i]:
            if prev.end <= card.start + 0.08:
                continue
            prev_h = 0.052 * (prev.text.count("\n") + 1) + (0.05 if prev.face == "box" else 0.02)
            floor = prev.y_ratio + prev_h
            if card.y_ratio < floor:
                ordered[i] = card.model_copy(update={"y_ratio": round(min(floor, 0.58), 3)})
                card = ordered[i]
    return ordered


def _pick_captions(
    blueprint: Blueprint,
    cutlist: CutList,
    work: Path,
    mode: str,
    concat_path: Path,
) -> list[CaptionLine]:
    overlay = [c for c in blueprint.captions if c.kind == "overlay"]
    speech = [c for c in blueprint.captions if c.kind != "overlay"]
    if mode in {"client", "auto", "reference"} and overlay:
        return overlay
    if mode == "reference":
        return overlay or speech
    if mode == "footage":
        _transcript, words = transcribe(concat_path, work / "out_audio.wav")
        return words_to_lines(words) if words else overlay or speech
    return overlay or speech


def compile_cut(
    blueprint: Blueprint,
    cutlist: CutList,
    work: Path,
    dest: Path,
    caption_mode: str = "client",
    music: Path | None = None,
    progress=lambda m: None,
    brief: dict | None = None,
    slot: dict | None = None,
    approved: bool = False,
) -> Path:
    slots_dir = work / "slots"
    slots_dir.mkdir(parents=True, exist_ok=True)
    slot_files: list[Path] = []
    for item in cutlist.slots:
        out = slots_dir / f"{item.shot_index:03d}.mp4"
        progress(f"Rendering slot {item.shot_index + 1}/{len(cutlist.slots)} ({item.status})")
        sig = out.with_suffix(".sig")
        want = f"{item.source_path}|{item.source_in}|{item.source_out}|{item.duration:.3f}|{item.face_x:.3f}"
        if item.status == "filled" and out.exists() and out.stat().st_size > 1000 and sig.exists() and sig.read_text() == want:
            slot_files.append(out)
            continue
        if item.status == "filled":
            _render_filled(item, out)
            sig.write_text(want)
        else:
            _render_slate(item, out)
        slot_files.append(out)

    concat_list = work / "concat.txt"
    concat_list.write_text("\n".join(concat_file_line(p) for p in slot_files) + "\n")
    concat_path = work / "concat.mp4"
    run(
        [
            ffmpeg_bin(),
            "-hide_banner",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            str(concat_path),
        ]
    )

    progress("Burning client captions on the TikTok cards…")
    captions = _pick_captions(blueprint, cutlist, work, caption_mode, concat_path)
    if approved:
        captions = [c.model_copy(update={"text": c.text.strip()}) for c in captions if (c.text or "").strip()]
    else:
        captions = drop_unburnable(captions, brief or {}, slot or {})
    captions = _dodge_faces(captions, concat_path)
    font = ensure_caption_font()
    build_ass(captions, work / "captions.ass", font)
    overlays = render_overlays(captions, work, font, reference=Path(blueprint.path) if blueprint.path else None)

    dest.parent.mkdir(parents=True, exist_ok=True)
    duration = video_info(concat_path)["duration"]
    encode = [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        "-t",
        f"{duration:.3f}",
        str(dest),
    ]

    if not overlays and not (music and music.exists()):
        run(
            [
                ffmpeg_bin(),
                "-hide_banner",
                "-y",
                "-i",
                str(concat_path),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(dest),
            ]
        )
        return dest

    cmd = [ffmpeg_bin(), "-hide_banner", "-y", "-i", str(concat_path)]
    music_idx = None
    if music and music.exists():
        cmd += ["-i", str(music)]
        music_idx = 1
    overlay_base = (music_idx or 0) + 1
    for ev in overlays:
        cmd += ["-loop", "1", "-t", f"{duration:.3f}", "-i", str(ev.png)]

    filters: list[str] = []
    maps: list[str]
    if overlays:
        vlabel = "0:v"
        for i, ev in enumerate(overlays):
            src = f"{overlay_base + i}:v"
            out = "vout" if i == len(overlays) - 1 else f"v{i}"
            filters.append(
                f"[{vlabel}][{src}]overlay=0:0:enable='between(t,{ev.start:.3f},{ev.end:.3f})'[{out}]"
            )
            vlabel = out
        maps = ["-map", "[vout]"]
    else:
        maps = ["-map", "0:v"]

    if music_idx is not None:
        filters.append(
            f"[0:a][{music_idx}:a]amix=inputs=2:duration=first:dropout_transition=2:weights=0.9 0.35[aout]"
        )
        maps += ["-map", "[aout]"]
    else:
        maps += ["-map", "0:a"]

    if filters:
        cmd += ["-filter_complex", ";".join(filters)]
    cmd += maps + encode
    run(cmd)
    return dest
