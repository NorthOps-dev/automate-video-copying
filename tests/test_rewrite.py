from videocopier.captions import STROKE, TRACKING, _load_font
from videocopier.fonts import ensure_caption_font
from videocopier.knowledge import load_brief
from videocopier.models import CaptionLine
from videocopier.rewrite import remake_for_client


def test_keeps_the_words_on_the_tiktok():
    brief = load_brief("c6d6fc60a86e", "MeloMelo Kava Bar")
    slot = {"hook": "Drinking proposal", "clientName": "MeloMelo Kava Bar", "scriptLines": [{"brand": "Thank you."}]}
    text = "Proposition:\nYou and I get 4 margaritas\non our lunch break and\ndon't come back to work"
    out = remake_for_client(
        [CaptionLine(text=text, start=0.1, end=13.4, kind="overlay", y_ratio=0.22)],
        slot,
        brief,
    )
    joined = "\n".join(c.text for c in out)
    assert "Proposition" in joined
    assert "4 margaritas" in joined
    assert "Thank you" not in joined
    assert "High Tide" not in joined


def test_classic_caption_face_is_not_extrabold():
    font = ensure_caption_font()
    loaded = _load_font(font.path, size=56, index=font.index)
    style = loaded.getname()[1].lower()
    assert "extra" not in style
    assert STROKE <= 5
    assert TRACKING <= 1.5
