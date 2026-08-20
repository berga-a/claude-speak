"""Markdown reaching the voice must sound like speech, not like source."""
import pytest


@pytest.mark.parametrize("md,expected", [
    ("Run `ls -la` now.",            "Run ls -la now."),
    ("Edit `gate.py` now.",          "Edit gate point py now."),
    ("`a.b.c`",                      "a point b point c."),
    ("One. Two.",                    "One. Two."),
    ("**Bold** here.",               "Bold here."),
    ("***Both*** here.",             "Both here."),
    ("See [the docs](https://x.io).", "See the docs."),
    ("Math 2 * 3 stays.",            "Math 2 times 3 stays."),
])
def test_inline_markup_reads_as_words(spoken, md, expected):
    assert spoken(md) == expected


@pytest.mark.parametrize("md", [
    "**Bold spanning\ntwo lines** here.",   # emphasis is matched per line
    "**Bold with * star** inside.",         # body excludes stars
    "***Bold italic*** across.",
    "A **bold** and **another** on one line.",
])
def test_no_asterisk_ever_reaches_the_voice(spoken, md):
    assert "*" not in spoken(md)


@pytest.mark.parametrize("identifier", ["a_b_c", "file_name.py", "CLAUDE_SPEAK_MAX"])
def test_underscores_survive_so_identifiers_stay_intact(spoken, identifier):
    assert identifier.split(".")[0] in spoken(f"Use {identifier} here.")


@pytest.mark.parametrize("md,shape", [
    ("Before.\n\n```python\nprint('x')\n```\n\nAfter.", ["say", "pause", "say"]),
    ("Before.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nAfter.", ["say", "pause", "say"]),
    ("Before.\n\n---\n\nAfter.", ["say", "say"]),
])
def test_unspeakable_blocks_become_silence(kinds, md, shape):
    assert kinds(md) == shape


def test_code_block_contents_are_never_spoken(spoken):
    assert "print" not in spoken("Before.\n\n```python\nprint('x')\n```\n\nAfter.")


def test_headings_and_bullets_lose_their_markers(spoken):
    out = spoken("## Title\n\n- first\n- second")
    assert "#" not in out and "- " not in out
    assert "Title" in out


@pytest.mark.parametrize("sentence,expected", [
    ("Short one.", 1),
    ("A" * 99, 1),
])
def test_short_sentences_render_as_one_unit(sentence, expected):
    import speak
    assert len(speak.clauses(sentence)) == expected


def test_long_sentences_are_split_for_rendering():
    """Coarse render units stall playback before any lead is built up."""
    import speak
    long_s = ("This clause is the first of several, and here is the second one, "
              "followed by a third that keeps going, then a fourth to be sure, "
              "and finally a fifth clause that pushes it well past the limit.")
    parts = speak.clauses(long_s)
    assert len(parts) > 1
    assert all(len(p) <= speak.RENDER_CHUNK + 40 for p in parts)
    assert " ".join(parts) == long_s          # nothing lost or duplicated


def test_splitting_happens_at_clause_boundaries():
    import speak
    long_s = "First part here, second part here, third part here, " * 4
    for part in speak.clauses(long_s)[:-1]:
        assert part.rstrip().endswith(","), f"split mid-clause: {part!r}"
