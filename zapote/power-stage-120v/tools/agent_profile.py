#!/usr/bin/env python3
"""Where a Claude Code agent's wall time goes, from its transcript; optionally, where a chain run's time goes.

    python3 -I tools/agent_profile.py TRANSCRIPT.jsonl [--top 15]
    python3 -I tools/agent_profile.py --build BUILDDIR

TRANSCRIPT is the agent's .jsonl (a subagent's lives under ~/.claude/projects/<project>/subagents/agent-<id>.jsonl;
the task .output file the harness reports is a symlink to it). Every record carries a timestamp. Each gap between
consecutive records is charged to:
  - tool time while any tool call is open (issued, result not back yet); each call is also timed on its own
    (call -> result), so long waits and builds show up by command;
  - model time otherwise (thinking and writing the next turn).
The listing is the slowest tool calls, then tool time per tool name.

--build lists a build directory's files by modification time, with the gap to the previous file. chain.sh writes no
per-step timestamps, so this is the step timeline it leaves behind: a gap before a file is (roughly) the step that
wrote it. Gate blocks run in parallel, so gaps are not additive past the core gates.
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def when(rec):
    t = rec.get("timestamp")
    return datetime.fromisoformat(t.replace("Z", "+00:00")) if t else None


def label(name, inp):
    s = inp.get("command") or inp.get("description") or inp.get("file_path") or json.dumps(inp)
    return f"{name}: " + " ".join(str(s).split())


def transcript(path, top):
    recs = [r for r in (json.loads(line) for line in Path(path).open() if line.strip()) if when(r)]
    recs.sort(key=when)
    calls, done = {}, []
    tool_s = model_s = 0.0
    prev = when(recs[0])
    for r in recs:
        t, msg = when(r), r.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        gap = (t - prev).total_seconds()
        prev = t
        if calls:
            tool_s += gap
        else:
            model_s += gap
        if not isinstance(content, list):
            continue
        if r.get("type") == "assistant":
            for b in content:
                if b.get("type") == "tool_use":
                    calls[b["id"]] = (t, b["name"], label(b["name"], b.get("input") or {}))
        elif r.get("type") == "user":
            for b in (b for b in content if b.get("type") == "tool_result"):
                if b["tool_use_id"] in calls:
                    t0, name, text = calls.pop(b["tool_use_id"])
                    done.append(((t - t0).total_seconds(), t0, name, text))
    wall = (when(recs[-1]) - when(recs[0])).total_seconds()
    print(f"wall {wall / 60:.1f} min  ({when(recs[0]):%H:%M} -> {when(recs[-1]):%H:%M} UTC)")
    print(f"tool {tool_s / 60:.1f} min   model {model_s / 60:.1f} min")
    print(f"{len(done)} tool calls, mean model turn {model_s / max(1, len(done)):.0f} s")
    if calls:
        print(f"{len(calls)} call(s) still open (running now):")
        for t0, _, text in calls.values():
            print(f"   since {t0:%H:%M} {text[:200]}")
    print(f"\nslowest {top} tool calls:")
    for d, t0, _, text in sorted(done, reverse=True)[:top]:
        print(f"{d / 60:6.1f} min  {t0:%H:%M}  {text[:200]}")
    per = defaultdict(lambda: [0, 0.0])
    for d, _, name, _ in done:
        per[name][0] += 1
        per[name][1] += d
    print("\nper tool:")
    for name, (n, d) in sorted(per.items(), key=lambda kv: -kv[1][1]):
        print(f"{d / 60:6.1f} min  {n:4d} calls  {name}")


def build(path):
    files = sorted((p for p in Path(path).iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime)
    prev = None
    for p in files:
        t = datetime.fromtimestamp(p.stat().st_mtime)
        gap = "" if prev is None else f"+{(t - prev).total_seconds():5.0f} s"
        print(f"{t:%H:%M:%S} {gap:>9}  {p.name}")
        prev = t
    if len(files) > 1:
        span = files[-1].stat().st_mtime - files[1].stat().st_mtime
        print(f"\n{span / 60:.1f} min from the second file to the last (the first is often a copied input)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("transcript", nargs="?")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--build")
    a = ap.parse_args()
    if not (a.transcript or a.build):
        ap.error("give a transcript, --build BUILDDIR, or both")
    if a.transcript:
        transcript(Path(a.transcript).resolve(), a.top)
    if a.build:
        if a.transcript:
            print()
        build(a.build)
    return 0


if __name__ == "__main__":
    sys.exit(main())
