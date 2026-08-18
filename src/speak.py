#!/usr/bin/env python3
"""Extract Claude Code's last reply, turn it into speakable segments, stream raw PCM to stdout.

Code blocks and tables become literal silence rather than being read out; inline
code is read normally. With --index, an offset->text map is written alongside the
audio so a downstream player can show each line as it is actually heard.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

PAUSE_BLOCK = 2.0  # seconds of silence standing in for a code block / table


def config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))


# ---------- transcript ----------

def project_transcript(cwd: Path) -> Path:
    slug = re.sub(r"[^a-zA-Z0-9]", "-", str(cwd))
    d = config_dir() / "projects" / slug
    if not d.is_dir():
        d = config_dir() / "projects"
    files = list(d.glob("**/*.jsonl"))
    if not files:
        sys.exit(f"no transcript under {d}")
    return max(files, key=lambda f: f.stat().st_mtime)


def nth_reply(transcript: Path, nth: int) -> str:
    """nth == 1 is the most recent assistant message containing prose."""
    found = 0
    for line in reversed(transcript.read_text(errors="replace").splitlines()):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("type") != "assistant" or rec.get("isSidechain"):
            continue
        parts = [c.get("text", "") for c in rec.get("message", {}).get("content", [])
                 if isinstance(c, dict) and c.get("type") == "text"]
        text = "\n".join(p for p in parts if p.strip())
        if text.strip():
            found += 1
            if found == nth:
                return text
    sys.exit("no assistant text found")


# ---------- markdown -> segments ----------

INLINE = [
    (re.compile(r"!?\[([^\]]*)\]\([^)]*\)"), r"\1"),          # links/images -> label
    (re.compile(r"`([^`]+)`"), r"\1"),                        # inline code: read the content
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),
    (re.compile(r"(?<!\w)[*_]([^*_]+)[*_](?!\w)"), r"\1"),
    (re.compile(r"^\s{0,3}#{1,6}\s*"), ""),                   # heading marker
    (re.compile(r"^\s*[-*+]\s+"), ""),                        # bullet marker
    (re.compile(r"^\s*\d+\.\s+"), ""),                        # numbered marker
]


def segments(md: str):
    """Yield ('say', text) and ('pause', seconds)."""
    lines = md.splitlines()
    buf, out = [], []

    def flush():
        if buf:
            out.append(("say", " ".join(buf)))
            buf.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):                                # fenced code block
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                i += 1
            i += 1
            flush()
            out.append(("pause", PAUSE_BLOCK))
            continue

        if stripped.startswith("|") and stripped.endswith("|"):       # table
            while i < len(lines) and lines[i].strip().startswith("|"):
                i += 1
            flush()
            out.append(("pause", PAUSE_BLOCK))
            continue

        if re.fullmatch(r"\s*([-*_])\s*\1\s*\1[\s\-*_]*", line):      # horizontal rule
            i += 1
            continue

        if not stripped:
            flush()
            i += 1
            continue

        text = line
        for pat, rep in INLINE:
            text = pat.sub(rep, text)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            if not re.search(r"[.!?:,]$", text):
                text += "."          # headings and bullets need a boundary to breathe
            buf.append(text)
        i += 1

    flush()
    return [s for s in out if s[0] == "pause" or s[1].strip()]


def cap(segs, maxchars):
    """Trim to maxchars on a sentence boundary. Returns (segs, spoken, total)."""
    total = sum(len(t) for k, t in segs if k == "say")
    if maxchars <= 0 or total <= maxchars:
        return segs, total, total
    kept, used = [], 0
    for kind, val in segs:
        if kind == "pause":
            kept.append((kind, val))
            continue
        room = maxchars - used
        if room <= 0:
            break
        if len(val) <= room:
            kept.append((kind, val))
            used += len(val)
            continue
        head = val[:room]
        m = list(re.finditer(r"[.!?]\s", head))
        head = head[:m[-1].end()] if m and m[-1].end() > room // 3 else head
        kept.append(("say", head))
        used += len(head)
        break
    while kept and kept[-1][0] == "pause":
        kept.pop()
    return kept, used, total


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?:])\s+", text) if s.strip()]


# ---------- synthesis ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="piper", choices=["piper", "kokoro"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--voice", default="af_heart")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--nth", type=int, default=1)
    ap.add_argument("--max", type=int, default=0,
                    help="character cap; 0 or less means no limit")
    ap.add_argument("--text", default=None)
    ap.add_argument("--index", default=None,
                    help="write 'byte-offset<TAB>text' lines here for synced display")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    md = a.text if a.text else nth_reply(project_transcript(Path.cwd()), a.nth)
    segs, spoken, total = cap(segments(md), a.max)

    if a.dry_run:
        for kind, val in segs:
            print(f"[pause {val}s]" if kind == "pause" else val)
        print(f"--- {spoken}/{total} chars", file=sys.stderr)
        return

    out = sys.stdout.buffer
    written = 0
    index = open(a.index, "w", buffering=1) if a.index else None

    def mark(text):
        if index:
            index.write(f"{written}\t{text}\n")

    if a.engine == "piper":
        from piper import PiperVoice, SynthesisConfig
        voice = PiperVoice.load(a.model)
        rate = voice.config.sample_rate
        cfg = SynthesisConfig(length_scale=1.0 / a.speed)

        def render(t):
            return b"".join(c.audio_int16_bytes for c in voice.synthesize(t, cfg))
    else:
        import numpy as np
        from kokoro_onnx import Kokoro
        k = Kokoro(a.model, str(Path(a.model).parent / "voices-v1.0.bin"))
        rate = 24000

        def render(t):
            samples, _ = k.create(t, voice=a.voice, speed=a.speed, lang="en-us")
            return (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()

    print(f"rate={rate} chars={spoken} total={total}", file=sys.stderr)

    for kind, val in segs:
        if kind == "pause":
            mark("...")
            pcm = b"\0" * (int(rate * val) * 2)
            out.write(pcm)
            out.flush()
            written += len(pcm)
            continue
        for sentence in sentences(val):
            mark(sentence)
            pcm = render(sentence)
            out.write(pcm)
            out.flush()
            written += len(pcm)

    if index:
        index.write(f"{written}\t\n")
        index.close()


if __name__ == "__main__":
    main()
