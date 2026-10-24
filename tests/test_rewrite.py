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
