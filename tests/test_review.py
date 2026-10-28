from unittest.mock import patch

from videocopier.knowledge import load_brief
from videocopier.models import CaptionLine
from videocopier.timeline import caption_plan


def test_unusable_ocr_still_opens_an_editable_timeline():
    junk = [
        CaptionLine(text="VBLLEY 8:08", start=0.1, end=0.5),
        CaptionLine(text="Sunnyvale Bar", start=0.5, end=0.9),
    ]
    with (
        patch("videocopier.timeline.ocr_captions", lambda *a, **k: junk),
        patch("videocopier.timeline.tiktok_cards", lambda cards: cards),
        patch("videocopier.timeline.coalesce_cards", lambda cards: cards),
        patch("videocopier.timeline._drop_garbled", lambda cards: []),
    ):
        source, draft = caption_plan("/tmp/x.mp4", 12.0, {"clientName": "MeloMelo"}, {"name": "MeloMelo"})
    assert source
    assert any("Sunnyvale" in c.text or "VBLLEY" in c.text for c in source)
    assert draft
    assert all(not (c.text or "").strip() for c in draft)
    assert draft[0].start == source[0].start
    assert draft[0].end == source[0].end


def test_review_draft_is_the_client_rewrite():
    cards = [
        CaptionLine(
            text="New in Sunnyvale: Must-Try\nRestaurant Alert!",
            start=0.1,
            end=2.0,
            kind="overlay",
            face="box",
        ),
        CaptionLine(
            text="definitely recommend\nto visit this place!\nValley Goat",
            start=20.0,
            end=22.0,
            kind="overlay",
        ),
    ]
    brief = load_brief("c6d6fc60a86e", "MeloMelo Kava Bar")
    with (
        patch("videocopier.timeline.ocr_captions", lambda *a, **k: cards),
        patch("videocopier.timeline.tiktok_cards", lambda rows: rows),
        patch("videocopier.timeline.coalesce_cards", lambda rows: rows),
        patch("videocopier.timeline._drop_garbled", lambda rows: rows),
    ):
        source, draft = caption_plan(
            "/tmp/x.mp4",
            22.0,
            {"hook": "New in Santa Cruz!!", "clientName": "MeloMelo Kava Bar"},
            brief,
        )
    joined = "\n".join(c.text for c in draft)
    assert any("Sunnyvale" in c.text for c in source)
    assert "Sunnyvale" not in joined
    assert "Valley Goat" not in joined
    assert draft[0].start == 0.1
    assert draft[1].end == 22.0
