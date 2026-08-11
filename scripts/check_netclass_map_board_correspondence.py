#!/usr/bin/env python3
"""Net-class map <-> board correspondence gate: every net name used as a
key in a hand-maintained ``net_classes:`` YAML mapping must be a real net
name on the board.

This is the generalisation half of the three correspondence gates in
this repo's "silent drift" defect class (see docs/evidence/
2026-08-11-correspondence-gates.md for the full write-up). Defect 3's
proximate cause was ``pcb/temper.kicad_pro``'s ``netclass_assignments``
drifting from ``TEMPER_NET_ASSIGNMENTS`` (case-mismatched ``ac_l``/``ac_n``,
missing ``SW_NODE``/``+170V_BUS``) -- PR #1023 fixed that pair, and #1025
is landing a generator with ``--check`` for exactly that pair (do not
duplicate it; this gate does not touch ``pcb/temper.kicad_pro`` at all).

Surveying the repo for OTHER hand-maintained copies of "which net belongs
to which class" (this task's explicit ask -- "survey for other
hand-maintained copies of a single source of truth") found the SAME
failure shape, independently, in four different files, none of them
``pcb/temper.kicad_pro``:

  - ``configs/temper_deterministic_config.yaml``'s ``net_classes:`` map
    uses ``AC_L``/``AC_N``/``DC_BUS+``/``DC_BUS-`` -- the real board nets
    are ``ac_l``/``ac_n``/``+170V_BUS``/``DC_BUS_RTN`` (confirmed against
    ``pcb/temper.kicad_pcb``'s own net table). This file is loaded by
    ``scripts/run_feedback_loop.py``, which calls
    ``Netlist.apply_net_class_mapping(net_class_mapping)`` -- that
    method's own docstring: "Nets not in the mapping retain their
    current net_class (typically the default 'Signal')". Exact-key
    matching with a silent, unlogged no-op on a miss is the SAME failure
    shape as ``TEMPER_NET_ASSIGNMENTS``' fallthrough that motivated
    ``check_hv_netclass_coverage.py`` -- a mains-voltage net silently
    inherits the default (lowest-clearance) class because the key that
    was supposed to classify it never matched anything.
  - ``packages/temper-placer/configs/temper_constraints.yaml``'s and
    ``configs/temper_production_config.yaml``'s ``net_classes:`` maps
    both still key on ``"+340V_BUS"`` -- a name
    ``elec/domain_manifest.yaml`` itself documents as renamed (`"+170V_BUS"
    # dc_bus_plus. Renamed from "+340V_BUS"`). The real net is
    ``+170V_BUS``; ``+340V_BUS`` matches nothing.
  - ``packages/temper-placer/configs/gate_driver_constraints.yaml``'s
    ``net_classes:`` map keys on ``GATE_H``/``GATE_L``/``CGND``/
    ``VCC_BOOT`` -- none of which is a real net name on the board (the
    real gate-drive nets are ``GATE_HS``/``GATE_LS``; there is no
    ``CGND`` or ``VCC_BOOT`` net on the current board at all).

Nothing before this gate checked that a ``net_classes:`` map's keys are
real net names anywhere. Because the standard consumer pattern
(``Netlist.apply_net_class_mapping`` and equivalents) does plain exact-key
dict lookup with a silent skip-on-miss, EVERY ONE of these files can have
an arbitrarily wrong key with zero symptom other than "the net quietly
got the default class" -- there is no error, no warning, not even a
count mismatch surfaced anywhere.

Scope, deliberately narrow and mechanical: this gate does not attempt to
guess a fix for a broken key (unlike a component reference, which
usually has an obvious real board equivalent once you know the
intended part, a stale net name is not always a 1:1 rename -- see the
module docstring's ``docs/evidence/2026-08-11-correspondence-gates.md``
discussion of which of the four files' broken keys are safe, mechanical
renames vs. which need the same kind of human/domain reconciliation
``temper_constraints.references.yaml`` required for defect 1's component
references). It only asserts the one universal, unconditionally-true
invariant: a ``net_classes:`` mapping key that is not a real net name can
never affect anything, on any consumer, ever -- so it is always a defect,
never a legitimate "not yet placed" or "future net" case (unlike a
component reference, a net name is defined by the compiled design, not
by a placement decision).

Discovery, not a hand-maintained file list (that would just be the same
kind of drift-prone duplication this gate exists to catch): every
top-level ``*.yaml`` file directly under ``configs/`` and under
``packages/temper-placer/configs/`` (non-recursive -- matches where all
four discovered instances live) is parsed, and any file whose top-level
``net_classes`` key is a mapping of ``{str: str}`` is treated as a
candidate. A file where ``net_classes`` is absent, or is some other
shape (e.g. a list, like the unrelated nested ``net_classes: ["ACMains"]``
per-rule field that appears inside some of these same files' other
sections -- a false-positive this gate must not trip on), is skipped,
not flagged.

Fail-closed contract (this repo's gate-family convention): this gate
exits non-zero for every one of:
  - the board file is missing or has no non-empty net table
  - zero candidate files with a top-level ``net_classes`` mapping are
    discovered across both config directories (a vacuous run -- this
    gate's whole premise, that such files exist, would be false)
  - a discovered candidate file is not valid YAML

Exit codes:
  0 - PASSED: every discovered net_classes mapping key is a real net name
  3 - VIOLATION: at least one mapping key does not match any real net
  5 - GATE ERROR: the gate could not run a trustworthy check at all

Usage:
  uv run python scripts/check_netclass_map_board_correspondence.py
  uv run python scripts/check_netclass_map_board_correspondence.py --board PATH
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402
from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

REPO_ROOT = find_repo_root()
DEFAULT_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
# Non-recursive: matches where every discovered instance of this pattern
# actually lives. A gate that walked the whole tree would also have to
# start excluding directories by hand -- itself a hand-maintained list.
CONFIG_DIRS = (
    REPO_ROOT / "configs",
    REPO_ROOT / "packages" / "temper-placer" / "configs",
)

_NET_ENTRY_RE = re.compile(r'\(net\s+\d+\s+"([^"]*)"\)')


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Board: real net names
# ---------------------------------------------------------------------------


def load_real_net_names(board_path: Path) -> set[str]:
    if not board_path.is_file():
        raise GateError(f"board file not found: {board_path}")
    text = board_path.read_text(encoding="utf-8")
    names = {m for m in _NET_ENTRY_RE.findall(text) if m}
    if not names:
        raise GateError(f"{board_path} has no non-empty net table entries")
    return names


# ---------------------------------------------------------------------------
# Config discovery
# ---------------------------------------------------------------------------


def discover_netclass_map_files(config_dirs: tuple[Path, ...]) -> list[Path]:
    """Returns every top-level *.yaml file under the given directories
    (non-recursive) whose parsed content has a top-level ``net_classes``
    key that is itself a mapping of {str: str}."""
    candidates: list[Path] = []
    for d in config_dirs:
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
            except yaml.YAMLError as e:
                raise GateError(f"{path} is not valid YAML: {e}") from e
            if not isinstance(data, dict):
                continue
            nc = data.get("net_classes")
            if isinstance(nc, dict) and nc and all(isinstance(v, str) for v in nc.values()):
                candidates.append(path)
    return candidates


def load_netclass_map(path: Path) -> dict[str, str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in data["net_classes"].items()}


# ---------------------------------------------------------------------------
# Correspondence check
# ---------------------------------------------------------------------------


@dataclass
class BrokenKey:
    config_path: str
    net_name: str
    declared_class: str


def check_map_against_board(
    config_path: Path, net_classes: dict[str, str], real_net_names: set[str]
) -> list[BrokenKey]:
    return [
        BrokenKey(str(config_path), net_name, cls)
        for net_name, cls in net_classes.items()
        if net_name not in real_net_names
    ]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class Report:
    files_checked: list[str] = field(default_factory=list)
    keys_checked: int = 0
    broken_keys: list[BrokenKey] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)


def run(board_path: Path, config_dirs: tuple[Path, ...] = CONFIG_DIRS) -> tuple[str, Report]:
    report = Report()
    try:
        real_net_names = load_real_net_names(board_path)
        candidate_files = discover_netclass_map_files(config_dirs)
    except GateError as e:
        report.tool_errors.append(str(e))
        return "tool_error", report

    if not candidate_files:
        report.tool_errors.append(
            "zero YAML files with a top-level 'net_classes' mapping discovered under "
            f"{', '.join(str(d) for d in config_dirs)} -- vacuous run, not a clean pass"
        )
        return "tool_error", report

    report.files_checked = [str(p) for p in candidate_files]
    for path in candidate_files:
        net_classes = load_netclass_map(path)
        report.keys_checked += len(net_classes)
        report.broken_keys.extend(check_map_against_board(path, net_classes, real_net_names))

    if report.broken_keys:
        return "violation", report
    return "clean", report


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_report(state: str, report: Report) -> None:
    print(
        "Net-class map <-> board correspondence gate -- "
        f"{len(report.files_checked)} file(s), {report.keys_checked} key(s) checked"
    )
    for f in report.files_checked:
        print(f"  scanned: {f}")

    if report.tool_errors:
        print(f"\n{len(report.tool_errors)} TOOL ERROR(S)")
        for e in report.tool_errors:
            print(f"  TOOL_ERROR {e}")
        if state == "tool_error":
            print(
                "\nGATE RESULT: ERROR -- not PASSED, not a violation. The gate "
                "could not run a trustworthy check.",
                file=sys.stderr,
            )
            return

    print(f"\n=== BROKEN net_classes KEYS: {len(report.broken_keys)} ===")
    for b in report.broken_keys:
        print(
            f"  VIOLATION {b.config_path}: net_classes[{b.net_name!r}] = {b.declared_class!r} -- "
            f"{b.net_name!r} is not a real net name on the board; this assignment is a silent no-op"
        )

    if state == "clean":
        print("\nNet-class map <-> board correspondence gate passed")
    elif state == "violation":
        print(f"\nFAILED -- {len(report.broken_keys)} broken net_classes key(s)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    args = parser.parse_args()

    state, report = run(args.board)
    _print_report(state, report)

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"\n### Net-Class Map <-> Board Correspondence Gate: {state}\n")
            f.write(
                f"- Files checked: {len(report.files_checked)}\n"
                f"- Keys checked: {report.keys_checked}\n"
                f"- Broken keys: {len(report.broken_keys)}\n"
                f"- Tool errors: {len(report.tool_errors)}\n"
            )
            if report.broken_keys:
                f.write("\nBroken keys:\n")
                for b in report.broken_keys:
                    f.write(f"- `{b.config_path}`: `{b.net_name}` -> `{b.declared_class}`\n")

    if state == "tool_error":
        sys.exit(EXIT_GATE_ERROR)
    if state == "violation":
        sys.exit(EXIT_VIOLATION)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
