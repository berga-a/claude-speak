"""The character cap trims on sentence boundaries, and 0 disables it."""
import pytest

import speak

PROSE = "First sentence here. Second sentence here. Third one here."


@pytest.mark.parametrize("maxchars", [0, -1])
def test_non_positive_cap_reads_everything(maxchars):
    _, used, total = speak.cap(speak.segments(PROSE), maxchars)
    assert used == total


def test_trims_on_a_sentence_boundary():
    kept, used, total = speak.cap(speak.segments(PROSE), 40)
    text = " ".join(v for k, v in kept if k == "say")
    assert used < total
    assert text.rstrip().endswith("."), f"cut mid-sentence: {text!r}"


def test_never_ends_on_silence():
    segs = speak.segments("Words here.\n\n```\ncode\n```\n\nMore words here.")
    kept, _, _ = speak.cap(segs, 12)
    assert kept[-1][0] != "pause"


def test_reports_the_untrimmed_total():
    _, used, total = speak.cap(speak.segments(PROSE), 20)
    assert total == len(PROSE) and used < total
