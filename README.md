# claude-speak

Read Claude Code's replies out loud, on demand — with a pause that actually pauses.

Local neural TTS, no API keys, no audio leaving your machine.

```
/speak            read the last reply
/speak pause      hold it, exactly mid-word
/speak resume     continue from the same sample
/speak stop       abandon it
/speak -n 3       read an earlier reply
/speak follow     watch the text scroll in time with the audio
/speak engine kokoro   switch engine, persistently
```

Every invocation reports how long it will take: `speaking [kokoro] 990 chars, ~1m0s`.

## Why another one

Most Claude Code TTS tools are `Stop` hooks: every reply is spoken, automatically.
That is great until you are reading along faster than it talks.

`claude-speak` is a **command**. Nothing is spoken until you ask for it, and once it
is speaking you stay in control:

- **A real pause.** Not "stop and restart the sentence" — playback holds at the exact
  sample and continues from there.
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

The obvious implementation, `SIGSTOP` on the player, is wrong. Freezing the process does
not stop the sound device: its DMA ring buffer keeps cycling whatever it was last given,
which you hear as a high-frequency stutter of the final few milliseconds.

So pausing means **keeping the device fed**. On `SIGUSR1` the gate stops forwarding real
samples and writes zeros instead; the audio waits in the pipe. On `SIGUSR2` it resumes at
the exact byte. The player never starves, so there is nothing to stutter.

This also self-throttles: the player blocks when its buffer is full, so the silence loop
paces itself to realtime rather than spinning.

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

## Credits

Speech by [piper](https://github.com/OHF-Voice/piper1-gpl) (GPL) and
[Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) (Apache-2.0), both installed at setup
time rather than vendored here.

MIT licensed — see [LICENSE](LICENSE).
