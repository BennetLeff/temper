#!/usr/bin/env python3
"""CI identity-gate enforcement (plan 2026-07-15-001, unit U7).

Two checks, both dry-runnable locally:

1. The quarantined fixture must always be rejected as a production input,
   regardless of ref overlap (role_violation). This is always checkable --
   the fixture and a netlist both already exist in every checkout.
2. If the real production board exists (pcb/temper.kicad_pcb, from the
   PCB-skeleton-generation plan), it must pass the gate. Skipped, not
   faked, until that board lands -- this script must not claim a false
   pass for an artifact that doesn't exist yet.

Exits 0 if all applicable checks pass, 1 with a clear diagnostic otherwise.
Never downgrades a failure to a warning.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PCB = REPO_ROOT / "pcb" / "benchmarks" / "temper_fixture_33.kicad_pcb"
PRODUCTION_PCB = REPO_ROOT / "pcb" / "temper.kicad_pcb"
NETLIST = REPO_ROOT / "elec" / "build" / "default.net"


def check_fixture_rejected() -> bool:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "temper-placer" / "src"))
    from temper_placer.io.design_bundle_preflight import BoardIdentityError, preflight_identity

    if not FIXTURE_PCB.exists():
        print(f"[FAIL] quarantined fixture not found at {FIXTURE_PCB}")
        return False
    if not NETLIST.exists():
        print(f"[FAIL] netlist not found at {NETLIST} (run `make netlist` first)")
        return False

    try:
        preflight_identity(FIXTURE_PCB, NETLIST)
    except BoardIdentityError as e:
        if "fixture" not in str(e).lower():
            print(f"[FAIL] fixture rejected, but not for the expected reason: {e}")
            return False
        print(f"[PASS] quarantined fixture correctly rejected: {e}")
        return True

    print("[FAIL] quarantined fixture was NOT rejected -- identity gate is not enforcing role")
    return False


def check_production_board_if_present() -> bool:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "temper-placer" / "src"))
    from temper_placer.io.design_bundle_preflight import preflight_identity

    if not PRODUCTION_PCB.exists():
        print(f"[SKIP] production board not present yet at {PRODUCTION_PCB}")
        return True
    if not NETLIST.exists():
        print(f"[FAIL] netlist not found at {NETLIST} (run `make netlist` first)")
        return False

    try:
        preflight_identity(PRODUCTION_PCB, NETLIST)
    except Exception as e:  # noqa: BLE001 -- any failure here is a real CI failure
        print(f"[FAIL] production board failed the identity gate: {e}")
        return False

    print(f"[PASS] production board {PRODUCTION_PCB} passes the identity gate")
    return True


def main() -> int:
    results = [check_fixture_rejected(), check_production_board_if_present()]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
