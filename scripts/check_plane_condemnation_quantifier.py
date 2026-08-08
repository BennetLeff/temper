#!/usr/bin/env python3
"""Plane-condemnation quantifier gate: catch a minority of zones silently
condemning an entire copper layer from the router's routing space.

Motivation
----------
``docs/solutions/logic-errors/single-zone-condemns-whole-copper-layer-plane-2026-07-29.md``
documents a bug in ``_extract_stackup()``
(``packages/temper-placer/src/temper_placer/io/_parse_board.py``): a physical
copper layer is classified ``layer_type="plane"`` the moment **any** zone on
that layer sits on a plane-required net (``_is_plane_required_net`` --
``ACMains``/``HighVoltage`` nets, plus a keyword fallback). Router
V6's ``routing_space.py:85`` then excludes every non-``signal``/``mixed``
layer from ``compute_routing_space()`` wholesale -- not just the area the
plane-required pour occupies, the *entire physical layer*. On the production
board this condemns both outer copper layers (F.Cu, B.Cu) because a small
minority of their zones (measured 2026-08-07: 6 of 48, 12.5% -- the doc's own
"4 of 48" figure has already drifted since 2026-07-29, a live illustration of
``docs/solutions/best-practices/stale-absolute-baseline-vs-mutable-board-2026-07-29.md``)
are plane-required.

The fix that landed (``use_declared_layer_roles``, opt-in, default ``False``)
is deliberately NOT flipped on in production: ``obstacle_map.py`` still
unions every zone on a layer into an opaque router obstacle regardless of
net, so opening the outer layers before pours become derived output would
reproduce a recorded 12x routing-completion regression (see that same doc's
"Solution" section and
``docs/solutions/best-practices/correct-diagnosis-unsafe-change-2026-07-28.md``).
The underlying quantifier bug (any() over zones, not a measured fraction) is
therefore still LIVE in production by design, tracked and accepted for the
two layers already measured -- but nothing was watching for a THIRD layer
(or a growing fraction on F.Cu/B.Cu) joining the condemned set, which is
exactly how this class of defect gets worse silently.

What this checks
-----------------
Independently (via kiutils, not by re-deriving the router's own zone-scan
logic -- reuses ``_is_plane_required_net`` as the single source of truth,
per ``docs/solutions/best-practices/gate-subset-blindness-2026-07-27.md``
guidance #4) counts, per copper layer:

  - ``total_zones``: net-bearing zones present on that layer
  - ``plane_required_zones``: the subset ``_is_plane_required_net`` accepts

and cross-references against the REAL classification
(``temper_placer.io.kicad_parser.parse_kicad_pcb_v6``, default args --
production's own settings) for every layer it marks ``layer_type="plane"``.

A layer is a QUANTIFIER-CONDEMNATION if it is classified ``"plane"`` while
``plane_required_zones / total_zones < MINORITY_THRESHOLD`` (default 0.5) --
i.e. the *majority* of its content is ordinary signal/power pours, not
plane-required copper, yet the whole layer is excluded from routing space
on the strength of a minority. Every such layer must appear in the dated
allowlist (``plane-condemnation-allowlist.yaml``) with a recorded
measurement and the tracking doc; an UNLISTED quantifier-condemned layer
fails the gate. This is not a check that the underlying router bug is fixed
(it isn't, and is not safe to fix alone -- see above) -- it is a check that
its blast radius is known, bounded, and would be noticed the moment it grows.

Fail-closed contract (this repo's METHODOLOGY.md Sec 4/5, matching
``check_isolation_keepout.py``): never exits 0 unless it positively confirms
a real, non-empty check ran. Exits non-zero (gate error) for:
  - the board file is missing, empty, or fails to parse
  - the board declares zero copper layers
  - the board has zero net-bearing zones anywhere (nothing to measure a
    quantifier fraction against)
  - the real parser and this gate's independent zone scan disagree about
    whether a "plane"-classified layer has any zones at all (a structural
    data-integrity mismatch, not "0 violations")

Exit codes:
  0 - PASSED: every quantifier-condemned layer (if any) is on the dated
      allowlist.
  3 - VIOLATION: a quantifier-condemned layer is NOT on the allowlist (a new
      or unexpectedly worse instance of the documented bug).
  5 - GATE ERROR: the gate could not run a trustworthy check at all.

Usage:
  uv run --no-sync python scripts/check_plane_condemnation_quantifier.py
  uv run --no-sync python scripts/check_plane_condemnation_quantifier.py --board PATH --allowlist PATH
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packages" / "temper-placer" / "src"))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root()
DEFAULT_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
DEFAULT_ALLOWLIST = REPO_ROOT / "plane-condemnation-allowlist.yaml"

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

# A layer classified "plane" whose plane-required-zone fraction falls below
# this is condemned on a MINORITY of its content -- the exact quantifier-bug
# signature the source doc describes (4/48 = 8.3% at the time it was
# written; measured 6/48 = 12.5% today). 0.5 is a wide, deliberately
# conservative margin: there is no legitimate design where a layer that is
# majority NON-plane-required content should be treated as fully
# unroutable, so nothing near this boundary is expected to false-positive.
MINORITY_THRESHOLD = 0.5

_COPPER_LAYER_TYPE = "signal"


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Allowlist (dated, documented -- see plane-condemnation-allowlist.yaml)
# ---------------------------------------------------------------------------


@dataclass
class AllowlistEntry:
    layer: str
    date: str
    reason: str
    doc: str
    measured_fraction: float | None = None


def load_allowlist(path: Path) -> dict[str, AllowlistEntry]:
    if not path.is_file():
        return {}
    raw_text = path.read_text(encoding="utf-8")
    if not raw_text.strip():
        return {}

    import yaml

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise GateError(f"allowlist is not valid YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict) or "allowlist" not in data:
        raise GateError(f"allowlist must be a mapping with an 'allowlist' key: {path}")
    entries = data["allowlist"] or []
    out: dict[str, AllowlistEntry] = {}
    for i, e in enumerate(entries):
        if not isinstance(e, dict) or "layer" not in e or "date" not in e or "reason" not in e or "doc" not in e:
            raise GateError(
                f"allowlist entry #{i} is missing required keys (layer/date/reason/doc): {e!r}"
            )
        out[e["layer"]] = AllowlistEntry(
            layer=e["layer"],
            date=str(e["date"]),
            reason=str(e["reason"]),
            doc=str(e["doc"]),
            measured_fraction=float(e["measured_fraction"]) if "measured_fraction" in e else None,
        )
    return out


# ---------------------------------------------------------------------------
# Independent zone-fraction measurement (kiutils; reuses the SSOT predicate)
# ---------------------------------------------------------------------------


def _expand_copper_layers(raw_layers: list[str], copper_layers_ordered: list[str]) -> frozenset[str]:
    out: set[str] = set()
    copper_set = set(copper_layers_ordered)
    for name in raw_layers:
        if name in ("*.Cu", "*Cu"):
            out |= copper_set
        elif name in copper_set:
            out.add(name)
    return frozenset(out)


@dataclass
class LayerZoneStats:
    total_zones: int = 0
    plane_required_zones: int = 0

    @property
    def fraction(self) -> float:
        return self.plane_required_zones / self.total_zones if self.total_zones else 0.0


def measure_zone_fractions(board_path: Path) -> tuple[list[str], dict[str, LayerZoneStats]]:
    """Returns (copper_layers_ordered, {layer_name: LayerZoneStats})."""
    if not board_path.is_file():
        raise GateError(f"board not found: {board_path}")
    try:
        from kiutils.board import Board
    except ImportError as exc:
        raise GateError(f"kiutils is not installed: {exc}") from exc
    try:
        board = Board.from_file(str(board_path))
    except Exception as exc:  # kiutils raises plain Exception/ValueError on malformed input
        raise GateError(f"failed to parse board {board_path}: {exc}") from exc

    signal_layers = [ly for ly in board.layers if getattr(ly, "type", None) == _COPPER_LAYER_TYPE]
    if not signal_layers:
        raise GateError(f"board declares zero copper (type=signal) layers: {board_path}")
    copper_layers_ordered = [ly.name for ly in sorted(signal_layers, key=lambda ly: ly.ordinal)]

    # Reuse the router's own SSOT predicate rather than re-deriving a second,
    # independently-drifting copy of "is this net plane-worthy" -- see
    # docs/solutions/best-practices/gate-subset-blindness-2026-07-27.md
    # guidance #4 and
    # docs/solutions/best-practices/substring-net-classification-drifts-from-ssot-2026-07-27.md.
    from temper_placer.io._parse_board import _is_plane_required_net

    stats: dict[str, LayerZoneStats] = {name: LayerZoneStats() for name in copper_layers_ordered}
    total_zones_examined = 0
    for zone in board.zones:
        if zone.keepoutSettings is not None:
            continue  # a keepout region, not copper -- not a "zone" for this bug's purposes
        net_name = zone.netName or ""
        if not net_name:
            continue
        layers = _expand_copper_layers(zone.layers or [], copper_layers_ordered)
        if not layers:
            continue
        total_zones_examined += 1
        is_pr = _is_plane_required_net(net_name)
        for ly in layers:
            stats[ly].total_zones += 1
            if is_pr:
                stats[ly].plane_required_zones += 1

    if total_zones_examined == 0:
        raise GateError(
            f"board has zero net-bearing copper zones: {board_path} -- nothing for this "
            "gate to measure a plane-condemnation fraction against (anti-vacuous-truth: "
            "report as a gate error, not '0 violations')"
        )

    return copper_layers_ordered, stats


def get_real_classification(board_path: Path) -> dict[str, str]:
    """Returns {layer_name: layer_type} from the REAL router parser, default
    args (production's own settings: use_declared_layer_roles=False)."""
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

    try:
        parsed = parse_kicad_pcb_v6(board_path)
    except Exception as exc:
        raise GateError(f"temper_placer's own parser failed on {board_path}: {exc}") from exc
    if not parsed.stackup.layers:
        raise GateError(f"temper_placer's own parser reported zero stackup layers for {board_path}")
    return {ly.name: ly.layer_type for ly in parsed.stackup.layers}


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


@dataclass
class LayerFinding:
    layer: str
    layer_type: str
    total_zones: int
    plane_required_zones: int
    fraction: float
    allowlisted: bool
    allowlist_entry: AllowlistEntry | None = None


@dataclass
class Report:
    copper_layers: list[str] = field(default_factory=list)
    plane_layers_total: int = 0  # every layer classified layer_type="plane", condemned or not
    findings: list[LayerFinding] = field(default_factory=list)  # minority-condemned "plane" layers
    unlisted_condemned: list[LayerFinding] = field(default_factory=list)  # violations
    stale_allowlist_entries: list[str] = field(default_factory=list)  # info only


def run(
    board_path: Path,
    allowlist_path: Path,
    minority_threshold: float = MINORITY_THRESHOLD,
) -> tuple[str, Report]:
    """Returns (state, report), state in 'clean' | 'violation'.

    Raises GateError for anything that must fail closed (exit 5).
    """
    report = Report()
    allowlist = load_allowlist(allowlist_path)

    copper_layers_ordered, stats = measure_zone_fractions(board_path)
    real_types = get_real_classification(board_path)

    report.copper_layers = copper_layers_ordered

    condemned_layers = [name for name in copper_layers_ordered if real_types.get(name) == "plane"]
    report.plane_layers_total = len(condemned_layers)

    for layer in condemned_layers:
        st = stats.get(layer)
        if st is None or st.total_zones == 0:
            raise GateError(
                f"layer {layer!r} is classified 'plane' by temper_placer's own parser, "
                "but this gate's independent zone scan found ZERO net-bearing zones on "
                "it -- the two measurements disagree about the board's own content, "
                "which is a data-integrity problem, not '0 violations'."
            )
        finding = LayerFinding(
            layer=layer,
            layer_type=real_types[layer],
            total_zones=st.total_zones,
            plane_required_zones=st.plane_required_zones,
            fraction=st.fraction,
            allowlisted=layer in allowlist,
            allowlist_entry=allowlist.get(layer),
        )
        if st.fraction < minority_threshold:
            report.findings.append(finding)
            if not finding.allowlisted:
                report.unlisted_condemned.append(finding)

    for layer, entry in allowlist.items():
        if real_types.get(layer) != "plane":
            report.stale_allowlist_entries.append(
                f"{layer}: allowlisted ({entry.date}) but no longer classified 'plane' -- "
                "entry may be removable."
            )
        else:
            st = stats.get(layer)
            if st is not None and st.fraction >= minority_threshold:
                report.stale_allowlist_entries.append(
                    f"{layer}: allowlisted as minority-condemned but measured fraction "
                    f"{st.fraction:.3f} is no longer below the {minority_threshold} "
                    "threshold -- entry may be removable."
                )

    if report.unlisted_condemned:
        return "violation", report
    return "clean", report


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_report(state: str, report: Report, board_path: Path, allowlist_path: Path) -> None:
    print(f"Board: {board_path}")
    print(f"Allowlist: {allowlist_path}")
    print(
        f"Copper layers: {len(report.copper_layers)} ({', '.join(report.copper_layers)}). "
        f"Layers classified 'plane': {report.plane_layers_total}. "
        f"Minority-condemned (quantifier-bug signature, fraction < threshold): {len(report.findings)}."
    )

    gh = get_github_summary_path()

    for f in report.findings:
        tag = "ALLOWLISTED" if f.allowlisted else "**UNLISTED**"
        print(
            f"  [{tag}] {f.layer}: {f.plane_required_zones}/{f.total_zones} zones "
            f"plane-required ({f.fraction:.3f}) -- classified layer_type={f.layer_type!r}, "
            f"excluded from routing space wholesale."
        )
        if f.allowlist_entry:
            print(f"      allowlist doc: {f.allowlist_entry.doc}")

    for note in report.stale_allowlist_entries:
        print(f"  [info] stale allowlist entry: {note}")

    if state == "clean":
        msg = (
            f"PASSED -- {len(report.findings)} quantifier-condemned layer(s) found, all on the "
            "dated allowlist. No new/unexpected layer is being excluded from routing space by "
            "a minority of its zones."
        )
        print(f"\n{msg}")
        if gh:
            with open(gh, "a") as fh:
                fh.write(f"### Plane Condemnation Quantifier Gate -- PASSED\n{msg}\n")
        return

    print(f"\n=== VIOLATIONS: {len(report.unlisted_condemned)} unlisted condemned layer(s) ===")
    for f in report.unlisted_condemned:
        print(
            f"  {f.layer}: {f.plane_required_zones}/{f.total_zones} zones plane-required "
            f"({f.fraction:.3f}) -- NOT on {allowlist_path.name}. Either this is a newly-"
            "introduced instance of the quantifier bug (see "
            "docs/solutions/logic-errors/single-zone-condemns-whole-copper-layer-plane-2026-07-29.md) "
            "and should be fixed at the source, or it is understood and accepted and must be "
            "added to the allowlist with a dated, documented reason."
        )
    print(f"\nFAILED -- {len(report.unlisted_condemned)} unlisted quantifier-condemned layer(s)")
    if gh:
        with open(gh, "a") as fh:
            fh.write(
                f"### Plane Condemnation Quantifier Gate -- FAILED\n"
                f"{len(report.unlisted_condemned)} unlisted quantifier-condemned layer(s)\n\n"
            )
            for f in report.unlisted_condemned:
                fh.write(f"- `{f.layer}`: {f.plane_required_zones}/{f.total_zones} ({f.fraction:.3f})\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument("--minority-threshold", type=float, default=MINORITY_THRESHOLD)
    args = parser.parse_args()

    try:
        state, report = run(args.board, args.allowlist, args.minority_threshold)
    except GateError as exc:
        print("=== PLANE CONDEMNATION QUANTIFIER GATE ERROR ===", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        print(
            "GATE RESULT: ERROR -- not PASSED, not a violation. The gate "
            "could not run a trustworthy check.",
            file=sys.stderr,
        )
        gh = get_github_summary_path()
        if gh:
            with open(gh, "a") as fh:
                fh.write(f"### Plane Condemnation Quantifier Gate -- GATE ERROR\n{exc}\n")
        sys.exit(EXIT_GATE_ERROR)

    _print_report(state, report, args.board, args.allowlist)

    if state == "violation":
        sys.exit(EXIT_VIOLATION)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
