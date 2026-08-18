"""The karaoke index turns byte offsets into lines printed in time with audio."""
import gate


def karaoke(tmp_path, lines, now=True):
    index = tmp_path / "index"
    index.write_text("".join(f"{off}\t{txt}\n" for off, txt in lines))
    return gate.Karaoke(str(index), str(tmp_path / "now.txt") if now else None)


def test_nothing_is_printed_before_the_audio_reaches_it(tmp_path, capsys):
    k = karaoke(tmp_path, [(100, "first"), (200, "second")])
    k.advance(50)
    assert capsys.readouterr().out == ""


def test_a_line_appears_once_its_audio_has_played(tmp_path, capsys):
    k = karaoke(tmp_path, [(100, "first"), (200, "second")])
    k.advance(150)
    assert capsys.readouterr().out == "first\n"


def test_lines_appear_in_order_as_playback_advances(tmp_path, capsys):
    k = karaoke(tmp_path, [(10, "one"), (20, "two"), (30, "three")])
    k.advance(15)
    k.advance(25)
    k.advance(35)
    assert capsys.readouterr().out == "one\ntwo\nthree\n"


def test_a_jump_flushes_everything_it_passed(tmp_path, capsys):
    k = karaoke(tmp_path, [(10, "one"), (20, "two"), (30, "three")])
    k.advance(999)
    assert capsys.readouterr().out == "one\ntwo\nthree\n"


def test_the_current_line_is_published_for_status(tmp_path):
    k = karaoke(tmp_path, [(10, "one"), (20, "two")])
    k.advance(25)
    assert (tmp_path / "now.txt").read_text().strip() == "two"


def test_the_end_marker_prints_nothing(tmp_path, capsys):
    k = karaoke(tmp_path, [(10, "one"), (20, "")])
    k.advance(999)
    assert capsys.readouterr().out == "one\n"


def test_a_partially_written_line_is_held_until_complete(tmp_path, capsys):
    """speak.py writes the index while the gate reads it."""
    index = tmp_path / "index"
    index.write_text("10\tcomplete\n20\tpartial")
    k = gate.Karaoke(str(index), None)
    k.advance(999)
    assert capsys.readouterr().out == "complete\n"

    with index.open("a") as fh:
        fh.write(" now finished\n")
    k.advance(999)
    assert capsys.readouterr().out == "partial now finished\n"


def test_multibyte_text_is_decoded_correctly(tmp_path, capsys):
    """Em-dashes are common in the text being read; a byte-offset seek would split them."""
    k = karaoke(tmp_path, [(10, "a — b — c"), (20, "naïve café")])
    k.advance(999)
    assert capsys.readouterr().out == "a — b — c\nnaïve café\n"


def test_no_index_means_no_output(tmp_path, capsys):
    k = gate.Karaoke(None, None)
    k.advance(999)
    assert capsys.readouterr().out == ""
