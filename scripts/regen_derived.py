#!/usr/bin/env python3
"""Regenerate the repo's derived artifacts — and refuse where regenerating would hide a defect.

WHY THIS EXISTS
---------------
On 2026-08-06 a derived artifact drifted behind a merge five separate times,
and each one turned `main` red for everyone:

    README/docs counts          after a 29-PR merge run
    oracle-hash registry        after #794 introduced the gate
    workspace package count     after #800 added a crate
    script manifest             after #800 added a script
    oracle-hash registry again  after #805 added five oracles

Every one was caught by a gate, correctly — and every one was caught *after*
the merge, because there was no single command an author could run first.
This is that command.

NOT EVERYTHING IS SAFE TO REGENERATE
------------------------------------
The reason this is a script and not `make regen: gen_a && gen_b && gen_c` is
that blanket regeneration is how a ratchet quietly stops ratcheting. Two of
these artifacts are *evidence*, not output:

* ``.hash-order-inventory`` — a NEW_SITE is a real determinism defect. Recording
  it converts a bug into an accepted baseline. Two such defects landed on
  2026-08-06 (``metrics/quality.py``, ``component_assignment.py``); both were
  fixed, neither inventoried. This tool REFUSES on NEW_SITE. It will record a
  STALE_ENTRY (debt paid, ledger behind), which is the shrink direction.

* ``scripts/oracle_hashes.json`` — an UNREGISTERED entry is a genuinely new
  oracle and safe to record. A DRIFTED entry means a *pinned* oracle's bytes
  changed, which is exactly what the gate exists to catch, and
  ``update_oracle_hashes.py``'s own docstring warns that running it over a
  drifted tree records the drift. This tool REFUSES on drift and prints the
  commit that last touched each drifted file, so the cause is established
  before it is recorded. Re-run with ``--accept-oracle-drift`` once you can
  name the deliberate re-pin.

Unconditionally safe, because they are pure functions of tracked source:
``gen_repo_state.py`` and ``gen_wasm_test_registry.py``.

USAGE
    uv run python scripts/regen_derived.py            # regenerate what is safe
    uv run python scripts/regen_derived.py --check    # report only, change nothing
    uv run python scripts/regen_derived.py --accept-oracle-drift

EXIT CODES
    0  everything is regenerated and consistent
    1  something needs a human: a NEW_SITE to fix, or oracle drift to explain
    2  a generator or gate failed to run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str]) -> tuple[int, str]:
    """Run *cmd* from the repo root, returning (exit code, combined output)."""
    proc = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def py(script: str, *args: str) -> list[str]:
    return [sys.executable, str(REPO_ROOT / "scripts" / script), *args]


def last_commit_touching(path: str) -> str:
    code, out = run(["git", "log", "-1", "--oneline", "--", path])
    return out.strip() if code == 0 and out.strip() else "(no commit found)"


def regen_pure(check: bool) -> int:
    """Artifacts that are pure functions of tracked source. Always safe."""
    problems = 0
    for script, check_flag in (("gen_repo_state.py", "--check"),
                               ("gen_wasm_test_registry.py", "--check")):
        if not (REPO_ROOT / "scripts" / script).exists():
            continue
        code, out = run(py(script, check_flag) if check else py(script))
        tail = out.strip().splitlines()[-1] if out.strip() else "(no output)"
        if check and code != 0:
            print(f"  DRIFT  {script}: {tail}")
            problems += 1
        else:
            print(f"  ok     {script}: {tail}")
    return problems


def handle_oracles(check: bool, accept_drift: bool) -> int:
    code, out = run(py("check_oracle_hashes.py"))
    if code == 0:
        print(f"  ok     oracle hashes: {out.strip().splitlines()[0]}")
        return 0

    drifted = [ln.split("]", 1)[1].split("--")[0].strip()
               for ln in out.splitlines() if "[DRIFTED]" in ln]
    unregistered = [ln for ln in out.splitlines() if "[UNREGISTERED]" in ln]

    if drifted and not accept_drift:
        print(f"  REFUSE oracle hashes: {len(drifted)} PINNED oracle(s) drifted; "
              f"{len(unregistered)} unregistered")
        print("         A drifted pin means a verbatim oracle's bytes changed. That is the")
        print("         case the gate exists to catch -- recording it here would launder it.")
        print("         Establish the cause, then re-run with --accept-oracle-drift:")
        for path in drifted:
            print(f"           {path}")
            print(f"             last touched by: {last_commit_touching(path)}")
        return 1

    if check:
        print(f"  DRIFT  oracle hashes: {len(unregistered)} unregistered, "
              f"{len(drifted)} drifted (run without --check to record)")
        return 1

    code, out = run(py("update_oracle_hashes.py"))
    if code != 0:
        print(f"  FAIL   update_oracle_hashes.py:\n{out}")
        return 2
    verify_code, verify_out = run(py("check_oracle_hashes.py"))
    status = "ok    " if verify_code == 0 else "FAIL  "
    print(f"  {status} oracle hashes: {verify_out.strip().splitlines()[0]}")
    return 0 if verify_code == 0 else 2


def handle_hash_order(check: bool) -> int:
    code, out = run(py("check_hash_order_determinism.py"))
    if code == 0:
        print(f"  ok     hash order: {out.strip().splitlines()[0]}")
        return 0

    new_sites = [ln for ln in out.splitlines() if ln.startswith("NEW_SITE")]
    stale = [ln for ln in out.splitlines()
             if ln.startswith(("STALE_ENTRY", "COUNT_SHRANK"))]

    if new_sites:
        print(f"  REFUSE hash order: {len(new_sites)} NEW_SITE(s) -- these are DEFECTS, not ledger entries.")
        print("         A set iterated to build an ordered artifact carries PYTHONHASHSEED's")
        print("         order into it. Fix the iteration (project through the input, or sort);")
        print("         do NOT add it to .hash-order-inventory.")
        for ln in new_sites[:5]:
            print(f"           {ln[:150]}")
        return 1

    if stale and not check:
        code, out = run(py("check_hash_order_determinism.py", "--write-inventory"))
        if code != 0:
            print(f"  FAIL   --write-inventory:\n{out}")
            return 2
        print(f"  ok     hash order: recorded {len(stale)} paid-down entr(ies) (shrink direction)")
        return 0

    print(f"  DRIFT  hash order: {len(stale)} stale ledger entr(ies) "
          f"(run without --check to record)")
    return 1


def handle_manifest() -> int:
    """`scripts/manifest.yaml` must list every script. Report only.

    Deliberately not auto-generated: an entry carries a `purpose` written for a
    human reader, and a machine-filled placeholder would defeat the point of
    the inventory. This landed on `main` red once already — #800 added
    `gen_wasm_test_registry.py` without an entry — so it is surfaced here even
    though the fix is manual.
    """
    script = REPO_ROOT / "scripts" / "check_manifest_gate.py"
    if not script.exists():
        return 0
    _, out = run(py("check_manifest_gate.py"))
    missing = [ln.strip() for ln in out.splitlines()
               if "has no manifest entry" in ln]
    if not missing:
        summary = next((ln for ln in out.splitlines() if "PASSED" in ln), "OK")
        print(f"  ok     manifest: {summary.strip()}")
        return 0
    print(f"  ACTION manifest: {len(missing)} script(s) have no entry in "
          f"scripts/manifest.yaml -- add one (purpose is written by hand):")
    for ln in missing[:5]:
        print(f"           {ln[:130]}")
    return 1



def handle_unwired() -> int:
    """Registered Rust kernels with no production caller. Report only.

    Not auto-fixable: wiring a shim is a code change with its own risk (the
    kernel may not model every field the shipped Python reads -- two such
    defects were found on 2026-08-06). Surfaced here so it is seen before a
    merge rather than in an audit weeks later.
    """
    script = REPO_ROOT / "scripts" / "check_unwired_kernels.py"
    if not script.exists():
        return 0
    code, out = run(py("check_unwired_kernels.py"))
    first = out.strip().splitlines()[0] if out.strip() else "(no output)"
    if code == 0:
        print(f"  ok     unwired kernels: {first}")
        return 0
    print(f"  ACTION unwired kernels: {first}")
    for ln in out.splitlines():
        if ln.startswith(("NEW_UNWIRED", "STALE_ENTRY")):
            print(f"           {ln[:130]}")
    return 1



def handle_wire_format() -> int:
    """Kernels whose wire format is narrower than the Python they replace.

    Report only: the fix is a wire-format change plus a corpus row, which is
    a code change with its own risk. Surfaced here so it is seen before a
    merge rather than in an audit.
    """
    if not (REPO_ROOT / "scripts" / "check_wire_format_fidelity.py").exists():
        return 0
    code, out = run(py("check_wire_format_fidelity.py"))
    first = out.strip().splitlines()[0] if out.strip() else "(no output)"
    if code == 0:
        print(f"  ok     wire formats: {first}")
        return 0
    print(f"  ACTION wire formats: {first}")
    for ln in out.splitlines():
        if ln.startswith(("DROPPED_FIELD", "STALE_ENTRY")):
            print(f"           {ln[:120]}")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="report only; change nothing (what CI would see)")
    ap.add_argument("--accept-oracle-drift", action="store_true",
                    help="record a drifted oracle pin -- only with a known, deliberate re-pin")
    args = ap.parse_args()

    print("derived artifacts:" + (" (check only)" if args.check else ""))
    problems = regen_pure(args.check)
    problems += handle_oracles(args.check, args.accept_oracle_drift)
    problems += handle_hash_order(args.check)
    problems += handle_manifest()
    problems += handle_unwired()
    problems += handle_wire_format()

    if problems == 0:
        print("all derived artifacts consistent")
        return 0
    print(f"\n{problems} item(s) need attention -- see above")
    return 1 if problems < 2 else problems


if __name__ == "__main__":
    sys.exit(main())
