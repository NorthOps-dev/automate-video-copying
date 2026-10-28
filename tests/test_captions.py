from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image

from videocopier.captions import TARGET_WIDTH_RATIO, render_block_png
from videocopier.fonts import ensure_caption_font
from videocopier.models import CaptionLine
from videocopier.ocr import _detect_face, _similar
from videocopier.rewrite import remake_for_client


def test_stacked_cards_keep_overlapping_times():
    from videocopier.rewrite import coalesce_cards

    cards = [
        CaptionLine(text="New in Sunnyvale: Must-Try\nRestaurant Alert!", start=0.1, end=4.6, kind="overlay", y_ratio=0.21, face="box"),
        CaptionLine(text="bright, plant-filled dining room with\ngoat-themed decor", start=1.1, end=7.0, kind="overlay", y_ratio=0.31, face="classic"),
    ]
    out = coalesce_cards(cards)
    assert len(out) == 2
    assert out[0].end > out[1].start
    assert out[0].face == "box"
    assert out[1].face == "classic"


def test_hook_is_not_glued_to_the_next_card():
    hook = "New in Sunnyvale: Must-Try\nRestaurant Alert!"
    later = "New in Sunnyvale: Must-Try\nRestaurant Alert!\nbright, plant-filled dining room with\ngoat-themed decor, spacious patio"
    assert not _similar(hook, later)
    assert _similar(
        "Proposition:\nYou and I get 4 margaritas\non our lunch break and\ndon't come back to work",
        "Proposition:\nYou and I get 4 margaritas\non our lunch break and",
    )


def test_detects_boxed_vs_classic_face():
    box = np.zeros((200, 400, 3), dtype=np.uint8)
    box[70:130, 40:360] = 255
    box[90:115, 80:160] = 0
    box_poly = [[[80, 90], [160, 90], [160, 115], [80, 115]]]
    assert _detect_face(box, box_poly) == "box"

    classic = np.zeros((200, 400, 3), dtype=np.uint8)
    classic[90:115, 80:160] = 255
    classic_poly = [[[80, 90], [160, 90], [160, 115], [80, 115]]]
    assert _detect_face(classic, classic_poly) == "classic"


def test_remake_keeps_the_measured_style():
    brief = {"name": "MeloMelo Kava Bar", "location": "Santa Cruz, CA", "what": "kava bar"}
    slot = {"hook": "New in Santa Cruz!!", "clientName": "MeloMelo Kava Bar"}
    card = CaptionLine(
        text="New in Sunnyvale: Must-Try\nRestaurant Alert!",
        start=0.1,
        end=2.0,
        kind="overlay",
        y_ratio=0.212,
        face="box",
        width_ratio=0.59,
        size_ratio=0.028,
    )
    out = remake_for_client([card], slot, brief)
    assert out
    assert out[0].face == "box"
    assert out[0].width_ratio == 0.59
    assert out[0].size_ratio == 0.028
    assert out[0].y_ratio == 0.212


def _opaque_bbox(path: Path):
    img = Image.open(path).convert("RGBA")
    arr = np.array(img)
    ys, xs = np.where(arr[:, :, 3] > 40)
    h, w = arr.shape[:2]
    return arr, xs.min() / w, xs.max() / w, ys.min() / h, ys.max() / h


def test_classic_card_matches_measured_width():
    font = ensure_caption_font()
    with TemporaryDirectory() as folder:
        dest = Path(folder) / "classic.png"
        render_block_png(
            dest,
            "Proposition:\nYou and I get 4 margaritas\non our lunch break and\ndon't come back to work",
            font,
            0.137,
            face="classic",
            width_ratio=0.767,
            size_ratio=0.038,
        )
        arr, x0, x1, y0, y1 = _opaque_bbox(dest)
        assert 0.72 <= (x1 - x0) <= 0.84
        assert 0.10 <= y0 <= 0.18
        assert TARGET_WIDTH_RATIO == 0.767
        core = arr[int(y0 * arr.shape[0]) + 20 : int(y1 * arr.shape[0]) - 20, int(x0 * arr.shape[1]) + 40 : int(x1 * arr.shape[1]) - 40]
        white = (core[:, :, 0] > 220) & (core[:, :, 3] > 200)
        assert float(white.mean()) < 0.55


def test_box_card_paints_a_white_pill():
    font = ensure_caption_font()
    with TemporaryDirectory() as folder:
        dest = Path(folder) / "box.png"
        render_block_png(
            dest,
            "New in Santa Cruz: Must-Try\nKava Bar Alert!",
            font,
            0.212,
            face="box",
            width_ratio=0.59,
            size_ratio=0.028,
        )
        arr, x0, x1, y0, y1 = _opaque_bbox(dest)
        band = arr[int(((y0 + y1) / 2) * arr.shape[0]), int(x0 * arr.shape[1]) : int(x1 * arr.shape[1])]
        opaque = band[band[:, 3] > 200]
        assert len(opaque) > 20
        assert float((opaque[:, 0] > 220).mean()) > 0.55
