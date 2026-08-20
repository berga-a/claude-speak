# claude-speak

[![tests](https://github.com/berga-a/claude-speak/actions/workflows/tests.yml/badge.svg)](https://github.com/berga-a/claude-speak/actions/workflows/tests.yml)

Read Claude Code's replies out loud, on demand — with a pause that actually pauses.

Local neural TTS, no API keys, no audio leaving your machine.

> **This tool is entirely vibe coded with Claude.** Every line of it — the shell driver,
> the Python, the tests and this README — was written by Claude Code from conversation,
> not typed by hand. It is used daily and the test suite is real, but read it with that
> in mind before depending on it.

```
/speak            read the last reply
/speak pause      hold it, exactly mid-word
/speak resume     continue from the same sample
/speak stop       abandon it
/speak -n 3       read an earlier reply
/speak follow     watch the text scroll in time with the audio
/speak status     is it speaking, and where has it got to
/speak engine kokoro   switch engine, persistently
```

`resume` accepts `unpause`, and `stop` accepts `off`.

Every invocation reports how long it will take: `speaking [kokoro] 990 chars, ~1m0s`.

## What it does

`claude-speak` is a command, not an automatic `Stop` hook: nothing is spoken until you
ask for it.

- **A real pause.** Playback holds at the exact sample and continues from there.
- **Text synced to audio.** `follow` prints each sentence at the moment you hear it.
- **Markdown that sounds like speech.** Inline code is read as words; code blocks and
  tables become a short silence instead of being spelled out.
- **Fully local.** piper or Kokoro, running offline.

## Install

Requires `python3`, `jq`, and an audio player (`aplay`, `pw-cat`, `sox`, or `ffplay`).

```bash
git clone https://github.com/berga-a/claude-speak ~/dev/claude-speak
cd ~/dev/claude-speak
./install.sh --hook
```

`--hook` also stops playback whenever you submit a new prompt. Add `--kokoro` for the
second engine. Restart Claude Code so it picks up the `/speak` command.

## How it works

```
speak.py                    gate.py                aplay / pw-cat / sox
  transcript -> segments  ->  PCM pump  ->  audio device
  index: offset -> text       silence while paused
```

`speak.py` finds the session transcript, pulls the nth assistant reply, converts
markdown into speakable segments, and streams raw PCM. Alongside the audio it writes an
index mapping byte offsets to the text at that offset.

`gate.py` pumps that PCM into the system player and uses the index to print each line as
the audio it labels is handed over — which is why the text tracks the voice.

### The pause

Pausing keeps the audio device fed. On `SIGUSR1` the gate stops forwarding samples and
writes zeros instead, holding the real audio in the pipe; on `SIGUSR2` it resumes at the
exact byte. The device is never starved, so playback holds cleanly and continues
mid-word.

The loop is self-throttling: the player blocks once its buffer is full, so writing
silence paces itself to realtime.

## Engines

| | piper | Kokoro |
|---|---|---|
| quality | clear, audibly synthetic | noticeably more natural |
| speed | ~12x realtime | ~1.5x realtime |
| start-up | near-instant | ~1s model load, ~3s to first audio |
| size | ~110 MB | ~340 MB |

`claude-speak engine kokoro` switches persistently (stored in `.engine`);
`CLAUDE_SPEAK_ENGINE=kokoro` overrides for one invocation. piper is the default
on a fresh install, since it is the one `install.sh` sets up without `--kokoro`.

Kokoro's 1.5x margin over realtime is thin: start a heavy build mid-sentence and it can
stutter. piper has room to spare.

## Configuration

| variable | default | meaning |
|---|---|---|
| `CLAUDE_SPEAK_ENGINE` | `.engine`, else `piper` | `piper` or `kokoro` |
| `CLAUDE_SPEAK_VOICE` | `af_heart` | Kokoro voice name |
| `CLAUDE_SPEAK_MODEL` | bundled | path to a piper `.onnx` |
| `CLAUDE_SPEAK_SPEED` | `1.0` | >1 faster, <1 slower |
| `CLAUDE_SPEAK_MAX` | `0` | character cap; `0` reads the whole reply |
| `CLAUDE_SPEAK_QUIET` | unset | suppress echoing the text in the command output |

## Limitations

- Reads the transcript from disk, so it speaks whatever was last written — it cannot
  stream a reply as it is being generated.
- The synced text lags by the player's buffer (~300 ms).
- Linux is the tested platform. macOS should work through `sox` or `ffplay` but is
  untested.
- `-n` counts assistant replies, and short acknowledgements count as replies.
- The duration estimate is derived from a measured characters-per-second rate, so
  it is within about a second on normal replies but drifts on very short ones.

## Tests

```bash
python3 -m venv venv-dev && ./venv-dev/bin/python -m pip install -r requirements-dev.txt
./venv-dev/bin/python -m pytest
```

The suite covers the pure logic — markdown conversion, the character cap, transcript
extraction, and the karaoke index — with no audio device, engine, or model required, so
it runs anywhere in well under a second.

## Troubleshooting

**Nothing is spoken, and no error.** The command needs an audio player it can pipe raw
PCM into. Check with `aplay --version`, and install `alsa-utils`, `pipewire-utils`, `sox`
or `ffmpeg` if none is present.

**`/speak` is not a known command.** Slash commands are read when the session starts.
Restart Claude Code after `install.sh`.

**Speech does not stop when I send a new message.** The hook is registered in
`settings.json` but hooks are also loaded at session start, so it only takes effect in a
new session. Confirm with `jq '.hooks.UserPromptSubmit' ~/.claude/settings.json`.

**Kokoro stutters when the machine is busy.** Kokoro synthesises at roughly 1.5x
realtime, so a heavy build competing for CPU can starve playback. Switch with
`claude-speak engine piper`, which runs about 12x realtime.

**It speaks the wrong message.** `-n` counts assistant replies, and short
acknowledgements count. Use `-n 2`, `-n 3` to walk back, or `follow` to see what was read.

**`pip: cannot execute: required file not found` after moving the repo.** A virtualenv
records absolute paths, so its console scripts break when the directory moves. Delete
`venv-piper/` and `venv-kokoro/` and re-run `install.sh`; the models in `voices/` and
`models-kokoro/` are kept and will not be downloaded again.

## Contributing

```
bin/claude-speak     driver: state, playback control, engine selection
src/speak.py         transcript -> speakable segments -> PCM, plus the sync index
src/gate.py          PCM pump, silence-on-pause, karaoke output
tests/               pure logic only: no audio device, engine or model required
```

Run `./venv-dev/bin/python -m pytest` before opening a pull request. New markdown
handling belongs in `INLINE` or `segments()` in `src/speak.py`, with a case added to
`tests/test_markdown.py`.

## Credits

Speech by [piper](https://github.com/OHF-Voice/piper1-gpl) (GPL) and
[Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) (Apache-2.0), both installed at setup
time rather than vendored here.

Written end to end by Claude Code. MIT licensed — see [LICENSE](LICENSE).
