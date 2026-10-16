"""scripts/wait_for.sh: waits on other processes, never on itself or the shell that started it."""
import subprocess
import time
import uuid
from pathlib import Path

WAIT = Path(__file__).resolve().parents[1] / "wait_for.sh"


def mark():
    return f"WAITFOR-{uuid.uuid4().hex[:10]}"


def run(cmd, timeout):
    t = time.monotonic()
    r = subprocess.run(["sh", "-c", cmd], capture_output=True, text=True, timeout=timeout)
    return r, time.monotonic() - t


def test_two_old_idiom_waiters_outlive_the_job():
    # the failure this script exists for (on macOS; on Linux one loop already matches its own `sh -c`): two
    # `until ! pgrep -f P` loops on one job each match the other's argv and never end after the job does
    m = mark()
    loop = f"until ! pgrep -f {m} >/dev/null; do sleep 0.2; done"
    job = subprocess.Popen(["sh", "-c", f"sleep 1; : {m}"])
    a = subprocess.Popen(["sh", "-c", loop])
    b = subprocess.Popen(["sh", "-c", loop])
    try:
        job.wait()
        time.sleep(2)
        assert a.poll() is None and b.poll() is None, "the pgrep -f loops ended; wait_for.sh's premise no longer holds"
    finally:
        a.kill()
        b.kill()


def test_pattern_with_no_other_process_returns_at_once():
    m = mark()
    r, dt = run(f"sh {WAIT} --interval 1 pattern {m}  # {m}", timeout=10)
    assert r.returncode == 0, r.stderr
    assert dt < 3


def test_pattern_waits_for_the_matching_process():
    m = mark()
    job = subprocess.Popen(["sh", "-c", f"sleep 2; : {m}"])
    try:
        r, dt = run(f"sh {WAIT} --interval 0.2 --timeout 20 pattern {m}", timeout=30)
        assert r.returncode == 0, r.stderr
        assert dt >= 1.5
    finally:
        job.kill()


def test_timeout_reports_what_is_left():
    m = mark()
    job = subprocess.Popen(["sh", "-c", f"sleep 30; : {m}"])
    try:
        r, _ = run(f"sh {WAIT} --interval 0.2 --timeout 1 pattern {m}", timeout=10)
        assert r.returncode == 124
        assert str(job.pid) in r.stderr
    finally:
        job.kill()


def test_two_waiters_do_not_wait_on_each_other():
    m = mark()
    other = subprocess.Popen(["sh", str(WAIT), "--interval", "0.2", "--timeout", "20", "pattern", m])
    try:
        time.sleep(0.5)
        r, dt = run(f"sh {WAIT} --interval 0.2 --timeout 5 pattern {m}", timeout=10)
        assert r.returncode == 0, r.stderr
        assert dt < 3
    finally:
        other.kill()


def test_pid_mode():
    job = subprocess.Popen(["sleep", "1.5"])
    r, dt = run(f"sh {WAIT} --interval 0.2 --timeout 10 pid {job.pid}", timeout=20)
    job.wait()
    assert r.returncode == 0
    assert dt >= 1.0
