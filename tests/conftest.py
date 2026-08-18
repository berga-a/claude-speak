import json
import tempfile
from pathlib import Path

import pytest

import speak


@pytest.fixture
def spoken():
    """The text a listener would actually hear, as one string."""
    return lambda md: " ".join(v for k, v in speak.segments(md) if k == "say")


@pytest.fixture
def kinds():
    """The segment sequence: 'say' for speech, 'pause' for inserted silence."""
    return lambda md: [k for k, _ in speak.segments(md)]


@pytest.fixture
def transcript(tmp_path):
    """Write JSONL records to a throwaway transcript and return its path."""
    def write(records):
        f = tmp_path / "session.jsonl"
        f.write_text("\n".join(json.dumps(r) for r in records))
        return f
    return write


@pytest.fixture
def assistant():
    return lambda *blocks: {"type": "assistant", "message": {"content": list(blocks)}}


@pytest.fixture
def text_block():
    return lambda t: {"type": "text", "text": t}
