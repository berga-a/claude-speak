#!/usr/bin/env python3
"""Audio gate: pump raw PCM from stdin to the system player, feeding silence while paused.

Stopping the player process does not stop the sound device: its DMA ring buffer
keeps cycling the last chunk it was handed, which is audible as a high-frequency
stutter. So pausing means keeping the device continuously supplied with zeros
while the real samples wait in the pipe.

  SIGUSR1 -> pause      SIGUSR2 -> resume

Given an index file (byte offset -> text, written by speak.py), it also prints
each line at the moment that audio actually reaches the player, so a terminal
tailing the output stays in sync with what you hear.
"""
import shutil
import signal
import subprocess
import sys

CHUNK = 2048  # bytes; ~21 ms of 24 kHz mono s16le

_paused = False


def _players(rate):
    """Player command lines that accept raw s16le mono on stdin, best first."""
    return [
        # A small buffer keeps the synced text close to what is actually audible;
        # too small and a busy CPU causes underruns.
        (["aplay", "-q", "--buffer-time=300000", "-t", "raw", "-f", "S16_LE",
          "-c", "1", "-r", str(rate)], "aplay"),
        (["pw-cat", "-p", "--format", "s16", "--rate", str(rate), "--channels", "1", "-"], "pw-cat"),
        (["play", "-q", "-t", "raw", "-r", str(rate), "-e", "signed", "-b", "16", "-c", "1", "-"], "play"),
        (["ffplay", "-hide_banner", "-loglevel", "quiet", "-nodisp", "-autoexit",
          "-f", "s16le", "-ar", str(rate), "-ac", "1", "-"], "ffplay"),
    ]


def _pick_player(rate):
    for cmd, exe in _players(rate):
        if shutil.which(exe):
            return cmd
    sys.exit("no usable audio player found (tried aplay, pw-cat, sox play, ffplay)")


def _pause(_s, _f):
    global _paused
    _paused = True


def _resume(_s, _f):
    global _paused
    _paused = False


class Karaoke:
    """Emits each line when the audio it labels has been handed to the player."""

    def __init__(self, index_path, now_path):
        self.fh = open(index_path) if index_path else None
        self.now_path = now_path
        self.pending = []

    def _refill(self):
        if not self.fh:
            return
        while True:
            line = self.fh.readline()
            if not line:
                return
            if not line.endswith("\n"):      # partial write; rewind and retry later
                self.fh.seek(self.fh.tell() - len(line))
                return
            offset, _, text = line.rstrip("\n").partition("\t")
            try:
                self.pending.append((int(offset), text))
            except ValueError:
                pass

    def advance(self, written):
        if not self.fh:
            return
        self._refill()
        while self.pending and self.pending[0][0] <= written:
            _, text = self.pending.pop(0)
            if not text:
                continue
            print(text, flush=True)
            if self.now_path:
                try:
                    with open(self.now_path, "w") as f:
                        f.write(text + "\n")
                except OSError:
                    pass


def main():
    rate = int(sys.argv[1])
    karaoke = Karaoke(sys.argv[2] if len(sys.argv) > 2 else None,
                      sys.argv[3] if len(sys.argv) > 3 else None)
    written = 0
    signal.signal(signal.SIGUSR1, _pause)
    signal.signal(signal.SIGUSR2, _resume)

    player = subprocess.Popen(_pick_player(rate), stdin=subprocess.PIPE)
    src = sys.stdin.buffer
    silence = b"\0" * CHUNK
    pending = b""

    try:
        while True:
            if _paused:
                # The player blocks once its buffer is full, so this self-throttles
                # to realtime rather than spinning.
                player.stdin.write(silence)
                player.stdin.flush()
                continue
            data = pending or src.read(CHUNK)
            pending = b""
            if not data:
                break
            if _paused:  # signal landed mid-read: hold this data for resume
                pending = data
                continue
            player.stdin.write(data)
            player.stdin.flush()
            written += len(data)
            karaoke.advance(written)
    except (BrokenPipeError, KeyboardInterrupt):
        pass
    finally:
        try:
            player.stdin.close()
        except Exception:
            pass
        player.wait()


if __name__ == "__main__":
    main()
