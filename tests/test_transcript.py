"""Which parts of a session transcript get read, and in what order."""
import json
import os
from pathlib import Path

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


def test_asking_past_the_end_reports_nothing_to_read(transcript, assistant, text_block):
    f = transcript([assistant(text_block("only one"))])
    with pytest.raises(SystemExit) as e:
        speak.nth_reply(f, 5)
    assert str(e.value) == speak.NOTHING_TO_READ


# ---------- which conversation gets read ----------

@pytest.fixture
def projects(tmp_path, monkeypatch):
    """A config dir holding one project slug; returns (write_session, cwd)."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    cwd = Path("/work/repo")
    slug = "-work-repo"
    d = tmp_path / "projects" / slug
    d.mkdir(parents=True)

    def write(session_id, mtime=None):
        f = d / f"{session_id}.jsonl"
        f.write_text(json.dumps(
            {"type": "assistant", "message": {"content": [
                {"type": "text", "text": session_id}]}}))
        if mtime is not None:
            os.utime(f, (mtime, mtime))
        return f
    return write, cwd, tmp_path


def test_reads_the_calling_session_not_the_most_recent(projects, monkeypatch):
    """Two sessions share a project directory; the other one replied last."""
    write, cwd, _ = projects
    mine = write("mine", mtime=1000)
    write("theirs", mtime=2000)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "mine")
    assert speak.project_transcript(cwd) == mine


def test_no_session_id_means_no_conversation_to_read(projects, monkeypatch):
    write, cwd, _ = projects
    write("theirs")
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    assert speak.project_transcript(cwd) is None


def test_session_without_a_transcript_yet_reads_nothing(projects, monkeypatch):
    write, cwd, _ = projects
    write("theirs")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "brand-new")
    assert speak.project_transcript(cwd) is None


def test_session_started_in_another_directory_is_still_found(projects, monkeypatch):
    """The slug follows the session's start directory, not the current one."""
    write, cwd, root = projects
    elsewhere = root / "projects" / "-other-place"
    elsewhere.mkdir(parents=True)
    mine = elsewhere / "mine.jsonl"
    mine.write_text("")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "mine")
    assert speak.project_transcript(cwd) == mine
