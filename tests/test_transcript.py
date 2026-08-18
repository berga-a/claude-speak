"""Which parts of a session transcript get read, and in what order."""
import json

import pytest

import speak


def test_most_recent_reply_is_n_equals_one(transcript, assistant, text_block):
    f = transcript([assistant(text_block("older")), assistant(text_block("newer"))])
    assert speak.nth_reply(f, 1) == "newer"
    assert speak.nth_reply(f, 2) == "older"


def test_plans_are_read(transcript, assistant, text_block):
    """A plan is the argument of an ExitPlanMode call, not a text block."""
    plan = {"type": "tool_use", "name": "ExitPlanMode",
            "input": {"plan": "## Plan\n\n1. Step one"}}
    f = transcript([assistant(text_block("prose")), assistant(plan)])
    assert "Step one" in speak.nth_reply(f, 1)


@pytest.mark.parametrize("tool,args", [
    ("Bash", {"command": "rm -rf /tmp/x"}),
    ("Read", {"file_path": "/etc/passwd"}),
])
def test_ordinary_tool_calls_are_neither_spoken_nor_counted(
        transcript, assistant, text_block, tool, args):
    call = {"type": "tool_use", "name": tool, "input": args}
    f = transcript([assistant(text_block("prose")), assistant(call)])
    assert speak.nth_reply(f, 1) == "prose"


def test_subagent_output_is_skipped(transcript, assistant, text_block):
    side = dict(assistant(text_block("subagent")), isSidechain=True)
    f = transcript([assistant(text_block("main")), side])
    assert speak.nth_reply(f, 1) == "main"


def test_user_messages_are_skipped(transcript, assistant, text_block):
    user = {"type": "user", "message": {"content": [text_block("my question")]}}
    f = transcript([assistant(text_block("reply")), user])
    assert speak.nth_reply(f, 1) == "reply"


def test_blank_replies_are_not_counted(transcript, assistant, text_block):
    f = transcript([assistant(text_block("real")), assistant(text_block("   "))])
    assert speak.nth_reply(f, 1) == "real"


def test_malformed_lines_do_not_abort_the_scan(tmp_path, assistant, text_block):
    f = tmp_path / "session.jsonl"
    f.write_text("not json at all\n" + json.dumps(assistant(text_block("fine"))))
    assert speak.nth_reply(f, 1) == "fine"


def test_multiple_text_blocks_in_one_reply_are_joined(transcript, assistant, text_block):
    f = transcript([assistant(text_block("first"), text_block("second"))])
    assert speak.nth_reply(f, 1) == "first\nsecond"


def test_asking_past_the_end_exits_rather_than_crashing(transcript, assistant, text_block):
    f = transcript([assistant(text_block("only one"))])
    with pytest.raises(SystemExit):
        speak.nth_reply(f, 5)
