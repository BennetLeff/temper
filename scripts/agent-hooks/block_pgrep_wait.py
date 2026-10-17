#!/usr/bin/env python3
"""Claude Code PreToolUse hook: refuse Bash commands that wait in a `pgrep -f` poll loop; point to wait_for.sh.

    "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
        "command": "python3 /Users/bennet/Desktop/temper/scripts/agent-hooks/block_pgrep_wait.py"}]}]}

`until ! pgrep -f P` / `while pgrep -f P` runs as one `sh -c` whose argv holds P: on Linux the loop finds its own
shell, on macOS two such loops on one job find each other, and either way the wait never ends (scripts/wait_for.sh
has the reproduction and the fix). A bracketed pattern (`pgrep -f '[c]hain.sh'`) cannot match its own text and is
let through, as is a single pgrep outside a loop (a check, not a wait). Exit 2 blocks the call; the message on
stderr goes back to the agent.
"""
import json
import re
import sys

LOOP = re.compile(r"\b(until|while)\b")
PGREP_F = re.compile(r"\bpgrep\s+(?:-\w+\s+)*-\w*f\w*\s+(?:-\w+\s+)*(?:--\s+)?(['\"]?)([^'\"\s;|&)]+)")


def blocked(command):
    if not LOOP.search(command):
        return None
    for m in PGREP_F.finditer(command):
        if "[" not in m.group(2):
            return m.group(2)
    return None


def main():
    try:
        call = json.load(sys.stdin)
    except ValueError:
        return 0
    if call.get("tool_name") != "Bash":
        return 0
    pat = blocked(call.get("tool_input", {}).get("command", ""))
    if pat is None:
        return 0
    print(f"Blocked: a `pgrep -f {pat}` poll loop can wait forever (it matches its own shell on Linux, and another "
          f"waiter's on macOS). Use `sh scripts/wait_for.sh --timeout S pattern '{pat}'` (or `pid PID`), or run the "
          "job itself with run_in_background and wait for its completion notice.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
