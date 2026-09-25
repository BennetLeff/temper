"""Tests for the fault-loop wrapper.

The check logic lives in Rust (`zapote-erc::fault_loop`) and is tested there —
`cargo test -p zapote-erc --lib fault_loop`. These tests cover only the Python
wrapper: that it forwards arguments and propagates the exit code, and that it
fails legibly when the Rust binary is absent.
"""
import os
import pathlib
import stat
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import check_fault_loop as wrapper  # noqa: E402

WRAPPER = pathlib.Path(__file__).parent / "check_fault_loop.py"


def make_stub(directory: pathlib.Path, body: str) -> pathlib.Path:
    stub = directory / "zapote-fault-loop"
    stub.write_text("#!/bin/sh\n" + body)
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return stub


def test_forwards_arguments_and_propagates_exit_zero(tmp_path: pathlib.Path) -> None:
    stub = make_stub(tmp_path, 'echo "ARGS:$@"\nexit 0\n')
    env = {**os.environ, "ZAPOTE_FAULT_LOOP_BIN": str(stub)}
    result = subprocess.run(
        [sys.executable, str(WRAPPER), "--netlist", "n.json", "--loop-nets", "A,B"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "ARGS:--netlist n.json --loop-nets A,B" in result.stdout


def test_propagates_a_nonzero_exit(tmp_path: pathlib.Path) -> None:
    stub = make_stub(tmp_path, 'echo "FAULT LOOP INCONSISTENT"\nexit 1\n')
    env = {**os.environ, "ZAPOTE_FAULT_LOOP_BIN": str(stub)}
    result = subprocess.run(
        [sys.executable, str(WRAPPER), "--netlist", "n.json"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 1
    assert "INCONSISTENT" in result.stdout


def test_missing_binary_is_reported_as_a_usage_error(tmp_path: pathlib.Path) -> None:
    # an explicit but absent override, and no PATH entry
    env = {**os.environ, "ZAPOTE_FAULT_LOOP_BIN": str(tmp_path / "does-not-exist"), "PATH": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, str(WRAPPER), "--netlist", "n.json"],
        capture_output=True, text=True, env=env,
    )
    # the override is returned as-is and exec fails; the wrapper must not silently succeed
    assert result.returncode != 0


def test_wrapper_claim_is_narrowed_in_its_own_text() -> None:
    text = WRAPPER.read_text()
    assert "necessary connectivity check" in text
    assert "does not prove a conductive path" in text
