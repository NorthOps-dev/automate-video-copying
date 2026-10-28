from videocopier.captions import STROKE, TRACKING, _load_font
from videocopier.fonts import ensure_caption_font
from videocopier.knowledge import load_brief
from videocopier.models import CaptionLine
from videocopier.ocr import _ocr_junk_line, strip_junk_lines
from videocopier.rewrite import drop_unburnable, remake_for_client


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
    assert "margaritas" in joined


def test_restaurant_cards_move_to_the_client():
    brief = load_brief("c6d6fc60a86e", "MeloMelo Kava Bar")
    slot = {"hook": "New in Santa Cruz!!", "clientName": "MeloMelo Kava Bar"}
    out = remake_for_client(
        [
            CaptionLine(text="New in Sunnyvale: Must-Try\nRestaurant Alert!", start=0.1, end=2.0, kind="overlay"),
            CaptionLine(text="definitely recommend\nto visit this place!\nValley Goat", start=20.0, end=22.0, kind="overlay"),
        ],
        slot,
        brief,
    )
    joined = "\n".join(c.text for c in out)
    assert "Sunnyvale" not in joined
    assert "Santa Cruz" in joined
    assert "Valley Goat" not in joined
    assert "MeloMelo" in joined
    assert out[0].start == 0.1
    assert out[1].start == 20.0
    assert out[1].end == 22.0


def test_glued_ocr_hook_is_rewritten_for_the_client():
    brief = load_brief("c6d6fc60a86e", "MeloMelo Kava Bar")
    slot = {"hook": "New in Santa Cruz!!", "clientName": "MeloMelo Kava Bar"}
    out = remake_for_client(
        [
            CaptionLine(
                text="New in Sunnyvale: Must-Try\nRestaurant Alert!\nbright, plant-filled dining room with\ngoat-themeddecor, spaciouspatio",
                start=0.1,
                end=4.6,
                kind="overlay",
            )
        ],
        slot,
        brief,
    )
    joined = "\n".join(c.text for c in out).lower()
    assert "sunnyvale" not in joined
    assert "vblley" not in joined
    assert "goat" not in joined
    assert "santa cruz" in joined
    assert "kava" in joined
    assert out[0].text.count("\n") <= 1


def test_restaurant_body_is_the_client_not_the_viral():
    brief = load_brief("c6d6fc60a86e", "MeloMelo Kava Bar")
    slot = {"hook": "New in Santa Cruz!!", "clientName": "MeloMelo Kava Bar"}
    out = remake_for_client(
        [
            CaptionLine(text="New in Sunnyvale: Must-Try\nRestaurant Alert!", start=0.1, end=4.2, kind="overlay", face="box"),
            CaptionLine(
                text="bright, plant-filled dining room with\ngoat-themed decor, spacious patio\nand a lively bar area",
                start=1.1,
                end=7.3,
                kind="overlay",
            ),
            CaptionLine(
                text="Chef Stephanie Izard is James Beard\nAward winner and the first female\nTop Chef champion",
                start=9.6,
                end=13.6,
                kind="overlay",
            ),
            CaptionLine(text="we tried wood-fired sprouted\neggplant and chicken skewers", start=13.7, end=17.2, kind="overlay"),
            CaptionLine(text="it was sooo delicious!", start=18.1, end=19.0, kind="overlay"),
            CaptionLine(text="definitely recommend\nto visit this place!", start=20.4, end=22.0, kind="overlay"),
            CaptionLine(text="Valley Goat", start=20.4, end=22.0, kind="overlay", y_ratio=0.56),
        ],
        slot,
        brief,
    )
    joined = "\n".join(c.text for c in out).lower()
    assert "sunnyvale" not in joined
    assert "santa cruz" in joined
    assert "kava bar alert" in joined
    assert "goat-themed" not in joined
    assert "stephanie" not in joined
    assert "eggplant" not in joined
    assert "high tide" in joined
    assert "melomelo" in joined
    assert "sooo delicious" in joined
    assert "definitely recommend" not in joined
    assert "visit this place" not in joined
    assert "come through" in joined or "melomelo" in joined
    assert "open daily" not in joined
    assert "noon-midnight" not in joined
    assert "is a kava bar" not in joined
    assert "buzz without the alcohol" in joined
    assert out[0].face == "box"
    assert out[0].start == 0.1


def test_ocr_crumb_cards_are_dropped():
    from videocopier.timeline import _drop_garbled

    keep = _drop_garbled(
        [
            CaptionLine(text="New in Santa Cruz!!\nKava Bar Alert!", start=0.1, end=4.6, kind="overlay"),
            CaptionLine(
                text="brigh\nlant-filled dining room with\ngoat-tht\nned decor, spacious patio\nda lively bar area",
                start=4.65,
                end=5.5,
                kind="overlay",
            ),
            CaptionLine(text="it was sooo delicious!", start=18.1, end=19.0, kind="overlay"),
        ]
    )
    joined = "\n".join(c.text for c in keep).lower()
    assert "santa cruz" in joined
    assert "sooo delicious" in joined
    assert "brigh" not in joined
    assert "goat-tht" not in joined


def test_ocr_garbage_is_not_a_caption():
    assert _ocr_junk_line("8:08")
    assert _ocr_junk_line("VBLLEY")
    assert _ocr_junk_line("gpat-themeddecor")
    assert _ocr_junk_line("spaciouspatio")
    assert strip_junk_lines("8:08\nNew in Sunnyvale: Must-Try\nVBLLEY") == "New in Sunnyvale: Must-Try"


def test_viral_ocr_never_ships_for_the_client():
    brief = load_brief("c6d6fc60a86e", "MeloMelo Kava Bar")
    slot = {"hook": "New in Santa Cruz!!", "clientName": "MeloMelo Kava Bar"}
    out = remake_for_client(
        [
            CaptionLine(text="8:08", start=0.0, end=1.2, kind="overlay"),
            CaptionLine(text="VBLLEY", start=0.2, end=1.4, kind="overlay"),
            CaptionLine(
                text="New in Sunnyvale: Must-Try\nRestaurant Alert!",
                start=0.1,
                end=4.2,
                kind="overlay",
                face="box",
            ),
            CaptionLine(
                text="bright, plant-filled dining room with\ngoat-themeddecor, spaciouspatio\nand a lively bar area",
                start=1.1,
                end=7.3,
                kind="overlay",
            ),
            CaptionLine(
                text="Chef Stephanie Izard is James Beard\nAward winner and the first female\nTop Chef champion",
                start=9.6,
                end=13.6,
                kind="overlay",
            ),
            CaptionLine(text="we tried wood-fired sprouted\neggplant and chicken skewers", start=13.7, end=17.2, kind="overlay"),
            CaptionLine(text="it was sooo delicious!", start=18.1, end=19.0, kind="overlay"),
            CaptionLine(text="definitely recommend\nto visit this place!", start=20.4, end=22.0, kind="overlay"),
            CaptionLine(text="Valley Goat", start=20.4, end=22.0, kind="overlay", y_ratio=0.56),
        ],
        slot,
        brief,
    )
    joined = "\n".join(c.text for c in out).lower()
    for leak in (
        "sunnyvale",
        "vblley",
        "8:08",
        "goat",
        "stephanie",
        "izard",
        "eggplant",
        "spaciouspatio",
        "gpat",
        "wood-fired",
        "plant-filled",
        "dining room",
    ):
        assert leak not in joined, leak
    assert "santa cruz" in joined
    assert "melomelo" in joined
    burned = drop_unburnable(out, brief, slot)
    leftover = "\n".join(c.text for c in burned).lower()
    assert "sunnyvale" not in leftover
    assert "valley goat" not in leftover


def test_classic_caption_face_is_not_extrabold():
    font = ensure_caption_font()
    loaded = _load_font(font.path, size=56, index=font.index)
    style = loaded.getname()[1].lower()
    assert "extra" not in style
    assert STROKE <= 5
    assert TRACKING <= 1.5
