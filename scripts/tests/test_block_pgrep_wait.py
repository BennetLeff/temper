"""scripts/agent-hooks/block_pgrep_wait.py: blocks pgrep -f poll loops, lets checks and bracketed patterns through."""
import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "agent-hooks" / "block_pgrep_wait.py"


def verdict(command, tool="Bash"):
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps({"tool_name": tool, "tool_input": {"command": command}}),
                       capture_output=True, text=True)
    return r.returncode, r.stderr


def test_blocks_until_loop():
    rc, msg = verdict('until ! pgrep -f "chain.sh native21s43" >/dev/null; do sleep 30; done; echo done')
    assert rc == 2 and "wait_for.sh" in msg


def test_blocks_while_loop_with_flags():
    assert verdict("while pgrep -lf incr_iter.sh; do sleep 5; done")[0] == 2


def test_allows_single_check():
    assert verdict('pgrep -fl "passes.sh|incr_iter.sh" | grep -v ps-layers; echo checked')[0] == 0


def test_allows_bracketed_pattern():
    assert verdict("until ! pgrep -f '[c]hain.sh native21s43'; do sleep 30; done")[0] == 0


def test_allows_wait_for():
    assert verdict("sh scripts/wait_for.sh --timeout 3600 pattern 'chain.sh native21s43'")[0] == 0


def test_ignores_other_tools_and_bad_input():
    assert verdict("until ! pgrep -f x; do sleep 1; done", tool="Read")[0] == 0
    r = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True)
    assert r.returncode == 0
