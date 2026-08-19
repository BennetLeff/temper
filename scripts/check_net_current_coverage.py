#!/usr/bin/env python3
"""Net-current coverage gate: every HV-domain net has a declared design
current, and every declared key names a real board net.

Motivating defect (confirmed on ``origin/main``, measured before the fix
this gate is designed against):

  ``temper_drc_rs::ipc::net_currents()`` -- the single machine-readable
  net -> ampacity table in this repo, and the input that sizes copper --
  was keyed on a "ghost" vocabulary inherited from a superseded schematic
  revision: ``DC_BUS+``, ``AC_L``, ``AC_N``, ``+5V``. None of those four
  is a net on ``pcb/temper.kicad_pcb``. The board spells them
  ``+170V_BUS``/``DC_BUS_RTN``, ``ac_l``/``ac_n``, and has no ``+5V`` at
  all. ``pcb/temper.kicad_pro`` carries 39 assignments in that same dead
  vocabulary, where they are inert; here they were LOAD-BEARING.

  The lookup returned ``DEFAULT_SIGNAL_CURRENT`` (0.1 A) for anything it
  failed to match, so 20 of the 27 nets ``elec/domain_manifest.yaml``
  declares under its ``HV`` domain silently resolved to a signal-level
  current -- among them the DC bus (``+170V_BUS``), its return
  (``DC_BUS_RTN``), the doubler midpoint (``PWR_RTN``), both CMC line
  windings (``w1_1``/``w1_2``) and the resonant tank (``tank-out``,
  ``tank.c_tank1-p2``). Measured consequence on the physics width path:
  ``DC_BUS_RTN``, ``PWR_RTN``, ``tank-out``, ``tank.c_tank1-p2``,
  ``hb-gnd``, ``w1_1`` and ``w1_2`` were each sized at the 0.127mm
  fabrication floor -- signal width, on conductors carrying 15-22.5 A.

  This is the SAME failure shape already fixed twice in this table by
  hand and once by another gate: the 2026-08-17 ``GATE_H`` -> ``GATE_HS``
  rename (docs/evidence/2026-08-17-gate-drive-ampacity-key-rename-fix.md)
  and the 2026-08-14 ``power_in.ntc-no`` addition. Both were found because
  somebody happened to look. Nothing made the table's coverage checkable,
  so the next stale key was always going to cost the same silent
  fall-through. That is what this gate exists to make impossible.

Convention: this gate deliberately mirrors
``scripts/check_hv_netclass_coverage.py`` -- same
``elec/domain_manifest.yaml`` HV-domain SSOT, same structural
``parse_board_net_names`` board reader (imported from it rather than
reimplemented), same ``run() -> (state, Report)`` shape, same
EXIT_OK/EXIT_VIOLATION/EXIT_GATE_ERROR codes, same blocking/informational
property split. It is the ampacity sibling of that gate's netclass
coverage.

PROPERTY 1 -- HV-domain net current coverage (BLOCKING)
--------------------------------------------------------
Every net ``elec/domain_manifest.yaml`` declares under its ``HV`` domain
(the hand-reviewed, human-curated SSOT for which nets are mains/HV-domain)
must resolve to a declared design current via
``temper_drc_rs.try_net_design_current_a``, or carry an explicit waiver in
``scripts/net_current_waivers.yaml`` with a stated reason.

The HV domain is the scope boundary on purpose, and it is the same one
``check_hv_netclass_coverage.py`` PROPERTY 1 draws. These are the
conductors on which an under-width trace is a fire risk. Requiring an
entry for all 162 board nets would mean hand-declaring ~130 GPIO/SPI/I2C
signal nets, which buys no safety and creates a large surface of
hand-maintained figures -- the very thing that rots. Nets outside the HV
domain that have no entry are reported by PROPERTY 3, not gated.

PROPERTY 2 -- no ghost keys (BLOCKING)
---------------------------------------
Every key in ``net_currents()`` must name a real net on
``pcb/temper.kicad_pcb``. A key that matches no board net is dead weight
at best; at worst it is the ``DC_BUS+`` case, where a plausible-looking
entry with a plausible-looking 16.0 A value made the table LOOK like it
covered the DC bus while the actual bus nets fell through to 0.1 A. A
reader auditing that table by eye saw a covered DC bus. There wasn't one.

Comparison is case-insensitive, matching the resolver's own semantics
(``try_net_design_current_a`` retries case-insensitively), so a key
written ``AC_L`` for a board net spelled ``ac_l`` is NOT reported -- it
genuinely resolves.

PROPERTY 3 -- undeclared board nets (INFORMATIONAL, never gates)
----------------------------------------------------------------
Every real board net with no declared current, listed so the signal tier
is visible and auditable rather than implicit. This never gates: a
genuine signal net legitimately has no ampacity figure. It exists so that
a NEW power net added to the board shows up in a diff here even if
somebody forgets to add it to the manifest.

Usage:
  uv run python scripts/check_net_current_coverage.py
  uv run python scripts/check_net_current_coverage.py --kicad-pcb PATH
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.repo import find_repo_root  # noqa: E402
from check_hv_netclass_coverage import GateError  # noqa: E402
from check_hv_netclass_coverage import load_hv_nets, parse_board_net_names  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

REPO_ROOT = find_repo_root()
DEFAULT_MANIFEST = REPO_ROOT / "elec" / "domain_manifest.yaml"
DEFAULT_KICAD_PCB = REPO_ROOT / "pcb" / "temper.kicad_pcb"
DEFAULT_WAIVERS = REPO_ROOT / "scripts" / "net_current_waivers.yaml"


@dataclass
class Report:
    hv_nets_checked: int = 0
    board_nets_checked: int = 0
    table_keys_checked: int = 0
    # PROPERTY 1 (BLOCKING)
    hv_nets_without_current: list[str] = field(default_factory=list)
    hv_nets_waived: list[str] = field(default_factory=list)
    # PROPERTY 2 (BLOCKING)
    ghost_table_keys: list[str] = field(default_factory=list)
    # PROPERTY 3 (INFORMATIONAL)
    undeclared_board_nets: list[str] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)


def load_waivers(path: Path) -> dict[str, str]:
    """Return ``{net: reason}`` from the waiver file, or ``{}`` if absent.

    Fail-closed on a malformed file or an empty/missing reason: a waiver
    with no stated reason is not a waiver, it is an unexplained hole, and
    silently honouring it would rebuild the exact silence this gate exists
    to remove.
    """
    if not path.is_file():
        return {}
    try:
        import yaml  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover
        raise GateError(f"PyYAML unavailable, cannot read {path}: {e}") from e
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise GateError(f"{path}: malformed YAML: {e}") from e
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise GateError(f"{path}: expected a mapping of net -> reason, got {type(raw).__name__}")
    waivers = raw.get("waivers", raw)
    if not isinstance(waivers, dict):
        raise GateError(f"{path}: 'waivers' must be a mapping of net -> reason")
    out: dict[str, str] = {}
    for net, reason in waivers.items():
        if not isinstance(reason, str) or not reason.strip():
            raise GateError(
                f"{path}: waiver for {net!r} has no reason. A waiver without a "
                "stated reason is an unexplained hole, not a waiver."
            )
        out[str(net)] = reason.strip()
    return out


def load_net_currents() -> dict[str, float]:
    """The live ``net_currents()`` table from the compiled Rust extension.

    Raises GateError (fail-closed) if the extension is not importable --
    mirrors ``check_hv_netclass_coverage._default_live_inputs``' treatment
    of an unimportable extension as a gate error, never a silent skip.
    """
    try:
        from temper_drc_rs import NET_CURRENTS  # noqa: PLC0415
    except ImportError as e:
        raise GateError(
            "could not import temper_drc_rs -- is the environment synced "
            f"(`make venv-isolate && make extensions`)? ({e})"
        ) from e
    if not NET_CURRENTS:
        raise GateError(
            "temper_drc_rs.NET_CURRENTS is empty -- the extension is stale or "
            "broken, not evidence that no net has a declared current"
        )
    return dict(NET_CURRENTS)


def resolve_current(net_name: str, table: dict[str, float]) -> float | None:
    """Mirror ``try_net_design_current_a``: exact, then case-insensitive."""
    if net_name in table:
        return table[net_name]
    lowered = net_name.lower()
    for key, value in table.items():
        if key.lower() == lowered:
            return value
    return None


def check_hv_current_coverage(
    hv_nets: list[str], table: dict[str, float], waivers: dict[str, str]
) -> tuple[list[str], list[str]]:
    """PROPERTY 1. Returns (missing, waived)."""
    missing: list[str] = []
    waived: list[str] = []
    for net in hv_nets:
        if resolve_current(net, table) is not None:
            continue
        if net in waivers:
            waived.append(net)
        else:
            missing.append(net)
    return sorted(missing), sorted(waived)


def check_ghost_keys(table: dict[str, float], board_nets: set[str]) -> list[str]:
    """PROPERTY 2. Table keys naming no real board net."""
    lowered = {n.lower() for n in board_nets}
    return sorted(k for k in table if k.lower() not in lowered)


def check_undeclared_board_nets(board_nets: set[str], table: dict[str, float]) -> list[str]:
    """PROPERTY 3 (informational)."""
    return sorted(n for n in board_nets if resolve_current(n, table) is None)


def run(
    manifest_path: Path = DEFAULT_MANIFEST,
    kicad_pcb_path: Path = DEFAULT_KICAD_PCB,
    waivers_path: Path = DEFAULT_WAIVERS,
    table: dict[str, float] | None = None,
    board_nets: set[str] | None = None,
) -> tuple[str, Report]:
    """Returns (state, report); state in 'clean' | 'violation' | 'tool_error'."""
    report = Report()
    try:
        if table is None:
            table = load_net_currents()
        if board_nets is None:
            board_nets = parse_board_net_names(kicad_pcb_path)
        hv_nets = load_hv_nets(manifest_path)
        waivers = load_waivers(waivers_path)
    except GateError as e:
        report.tool_errors.append(str(e))
        return "tool_error", report
    except Exception as e:  # noqa: BLE001 - any load failure must fail closed
        report.tool_errors.append(f"{type(e).__name__}: {e}")
        return "tool_error", report

    report.hv_nets_checked = len(hv_nets)
    report.board_nets_checked = len(board_nets)
    report.table_keys_checked = len(table)

    missing, waived = check_hv_current_coverage(hv_nets, table, waivers)
    report.hv_nets_without_current = missing
    report.hv_nets_waived = waived
    report.ghost_table_keys = check_ghost_keys(table, board_nets)
    report.undeclared_board_nets = check_undeclared_board_nets(board_nets, table)

    if report.hv_nets_without_current or report.ghost_table_keys:
        return "violation", report
    return "clean", report


def _print_report(state: str, report: Report) -> None:
    print("=" * 72)
    print("NET CURRENT COVERAGE GATE")
    print("=" * 72)
    if report.tool_errors:
        print("\nTOOL ERROR (fail-closed):")
        for e in report.tool_errors:
            print(f"  - {e}")
        return

    print(
        f"\nChecked {report.hv_nets_checked} HV-domain nets, "
        f"{report.board_nets_checked} board nets, "
        f"{report.table_keys_checked} net_currents() keys."
    )

    print("\nPROPERTY 1 -- HV-domain net current coverage (BLOCKING)")
    if report.hv_nets_without_current:
        print(f"  FAIL: {len(report.hv_nets_without_current)} HV net(s) with no declared current:")
        for n in report.hv_nets_without_current:
            print(f"    - {n}")
        print(
            "\n  These conductors are mains/HV-domain per elec/domain_manifest.yaml\n"
            "  and would be sized without a current figure. Add a cited entry to\n"
            "  temper_drc_rs::ipc::net_currents(), or waive it in\n"
            "  scripts/net_current_waivers.yaml with a reason."
        )
    else:
        print("  PASS: every HV-domain net has a declared design current.")
    if report.hv_nets_waived:
        print(f"  ({len(report.hv_nets_waived)} explicitly waived: {', '.join(report.hv_nets_waived)})")

    print("\nPROPERTY 2 -- no ghost keys (BLOCKING)")
    if report.ghost_table_keys:
        print(f"  FAIL: {len(report.ghost_table_keys)} table key(s) naming no board net:")
        for k in report.ghost_table_keys:
            print(f"    - {k}")
        print(
            "\n  A key that matches no board net makes the table LOOK like it covers\n"
            "  a conductor it does not. This is the 'DC_BUS+' shape exactly."
        )
    else:
        print("  PASS: every net_currents() key names a real board net.")

    print("\nPROPERTY 3 -- undeclared board nets (INFORMATIONAL, never gates)")
    print(f"  {len(report.undeclared_board_nets)} board net(s) have no declared current.")
    print("  (Expected for genuine signal nets; listed so new power nets are visible.)")

    print("\n" + "=" * 72)
    print(f"RESULT: {state.upper()}")
    print("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--kicad-pcb", type=Path, default=DEFAULT_KICAD_PCB)
    parser.add_argument("--waivers", type=Path, default=DEFAULT_WAIVERS)
    parser.add_argument(
        "--list-undeclared",
        action="store_true",
        help="print every board net with no declared current (PROPERTY 3 detail)",
    )
    args = parser.parse_args()

    state, report = run(
        manifest_path=args.manifest,
        kicad_pcb_path=args.kicad_pcb,
        waivers_path=args.waivers,
    )
    _print_report(state, report)
    if args.list_undeclared:
        print("\nUndeclared board nets:")
        for n in report.undeclared_board_nets:
            print(f"  {n}")

    if state == "tool_error":
        sys.exit(EXIT_GATE_ERROR)
    if state == "violation":
        sys.exit(EXIT_VIOLATION)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
