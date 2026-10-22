from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from videocopier.fonts import FontChoice
from videocopier.models import CaptionLine, Word

WIDTH = 1080
HEIGHT = 1920
CYAN = (0, 242, 234, 255)
WHITE = (255, 255, 255, 255)
BLACK = (0, 0, 0, 255)


def words_to_lines(words: list[Word], max_words: int = 4, max_chars: int = 22) -> list[CaptionLine]:
    lines: list[CaptionLine] = []
    bucket: list[Word] = []
    for word in words:
        trial = bucket + [word]
        text = " ".join(w.text for w in trial)
        if bucket and (len(trial) > max_words or len(text) > max_chars):
            lines.append(_line_from(bucket))
            bucket = [word]
        else:
            bucket = trial
    if bucket:
        lines.append(_line_from(bucket))
    return lines


def _line_from(bucket: list[Word]) -> CaptionLine:
    text = " ".join(w.text for w in bucket).strip()
    return CaptionLine(text=text, start=bucket[0].start, end=max(bucket[-1].end, bucket[0].start + 0.35), words=bucket)


def _ass_time(t: float) -> str:
    t = max(t, 0.0)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _classic_text(text: str) -> str:
    return text.replace("'", "’").replace("`", "’").replace("´", "’")


def build_ass(captions: list[CaptionLine], dest: Path, font: FontChoice, play_x: int = 1080, play_y: int = 1920) -> Path:
    """Classic TikTok look: Proxima-like Bold, white fill, thick black outline."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_x}
PlayResY: {play_y}
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TikTok,{font.ass_name},72,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,0,2,50,50,460,1
Style: WordOn,{font.ass_name},72,&H00EAF200,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,0,2,50,50,460,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    for line in captions:
        if not line.text.strip():
            continue
        start = _ass_time(line.start)
        end = _ass_time(max(line.end, line.start + 0.3))
        if line.words and len(line.words) > 1:
            # Full phrase in white, current word popped in TikTok cyan.
            for i, word in enumerate(line.words):
                colored = []
                for j, w in enumerate(line.words):
                    token = _escape(w.text)
                    if j == i:
                        colored.append(r"{\c&HEAF200&}" + token + r"{\c&HFFFFFF&}")
                    else:
                        colored.append(token)
                w_start = _ass_time(word.start)
                w_end = _ass_time(word.end if i < len(line.words) - 1 else line.end)
                events.append(f"Dialogue: 0,{w_start},{w_end},TikTok,,0,0,0,,{' '.join(colored)}")
        else:
            events.append(f"Dialogue: 0,{start},{end},TikTok,,0,0,0,,{_escape(line.text)}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return dest


@dataclass
class OverlayEvent:
    start: float
    end: float
    png: Path


def _axis_name(axis: dict) -> str:
    raw = axis.get("name") or axis.get("tag") or ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "ignore")
    return str(raw)


def _load_font(path: Path, size: int = 76, index: int = 0) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(path), size=size, index=index)
    name = ""
    try:
        name = " ".join(font.getname()).lower()
    except Exception:
        pass
    if "tiktok" not in name and "tiktok" not in path.name.lower():
        return font
    try:
        font.set_variation_by_name("ExtraBold")
        return font
    except Exception:
        pass
    try:
        axes = font.get_variation_axes()
        values = []
        for axis in axes:
            tag = _axis_name(axis).lower()
            if "weight" in tag or tag == "wght":
                values.append(800)
            elif "optical" in tag or tag == "opsz":
                values.append(axis.get("maximum", 36) or 36)
            elif "width" in tag or tag == "wdth":
                values.append(100)
            elif "slant" in tag or tag == "slnt":
                values.append(0)
            else:
                values.append(axis.get("default", 0) or 0)
        if values:
            font.set_variation_by_axes(values)
    except Exception:
        pass
    return font


def _draw_phrase(draw: ImageDraw.ImageDraw, words: list[str], highlight: int | None, font, y: float | None = None) -> None:
    words = [_classic_text(w) for w in words]
    space = font.getlength(" ")
    widths = [font.getlength(w) for w in words]
    total = sum(widths) + space * max(len(words) - 1, 0)
    x = (WIDTH - total) / 2
    y = HEIGHT - 520 if y is None else y
    for i, word in enumerate(words):
        fill = CYAN if highlight == i else WHITE
        draw.text((x, y), word, font=font, fill=fill, stroke_width=6, stroke_fill=BLACK)
        x += widths[i] + space


def _draw_block(draw: ImageDraw.ImageDraw, text: str, font, y_ratio: float) -> None:
    lines = [_classic_text(ln.strip()) for ln in text.split("\n") if ln.strip()]
    if not lines:
        return
    line_h = font.size + 14
    y = max(110, min(HEIGHT * min(y_ratio, 0.15), HEIGHT - line_h * len(lines) - 180))
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=7)
        tw = bbox[2] - bbox[0]
        x = (WIDTH - tw) / 2
        draw.text((x, y + i * line_h), line, font=font, fill=WHITE, stroke_width=7, stroke_fill=BLACK)


def render_caption_png(dest: Path, words: list[str], highlight: int | None, font_choice: FontChoice) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _load_font(font_choice.path, index=font_choice.index)
    _draw_phrase(draw, words, highlight, font)
    img.save(dest, "PNG")
    return dest


def render_block_png(dest: Path, text: str, font_choice: FontChoice, y_ratio: float) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    lines = [ln for ln in text.split("\n") if ln.strip()]
    size = 64 if len(lines) > 3 else 74
    font = _load_font(font_choice.path, size=size, index=font_choice.index)
    _draw_block(draw, text, font, y_ratio)
    img.save(dest, "PNG")
    return dest


def render_overlays(captions: list[CaptionLine], work: Path, font: FontChoice) -> list[OverlayEvent]:
    events: list[OverlayEvent] = []
    png_dir = work / "cap_png"
    png_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for line in captions:
        if not line.text.strip():
            continue
        if line.kind == "overlay" or "\n" in line.text:
            n += 1
            png = render_block_png(png_dir / f"{n:04d}.png", line.text, font, line.y_ratio)
            events.append(OverlayEvent(start=line.start, end=max(line.end, line.start + 0.8), png=png))
            continue
        tokens = [w.text for w in line.words] if line.words else line.text.split()
        if not tokens:
            continue
        n += 1
        png = render_caption_png(png_dir / f"{n:04d}.png", tokens, None, font)
        events.append(OverlayEvent(start=line.start, end=max(line.end, line.start + 0.5), png=png))
    return events
