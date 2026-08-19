#!/usr/bin/env python3
"""BOM <-> source reconciliation gate (R14).

Goal-set requirement R14: "The BOM reconciles against source in both
directions, with no costed line lacking a circuit and no wired component
uncosted." Before this gate existed, nothing in CI checked this at all --
``docs/hardware/BOM.md`` appeared only in ``python-tests.yml``'s path-filter
list, and the two existing reconciliation gates check different pairs of
artifacts: ``mpn_fabrication_gate.py`` checks MPN/value *internal
consistency* within ``elec/src/*.ato`` (a fabricated MPN can still pass this
gate), and ``check_netlist_board_reconciliation.py`` checks
``pcb/temper.kicad_pcb`` against ``elec/build/default.net`` (board vs
netlist, not the priced BOM document). Manual audits on 2026-07-25 and
2026-07-26 (``docs/evidence/2026-07-25-bom-source-audit.md``,
``docs/evidence/2026-07-26-bom-blocker-resolution.md``) found and fixed BOM
drift by hand; nothing has re-run that audit since, and the BOM has drifted
again.

WHAT THIS GATE DOES
====================

For every component-table row in ``docs/hardware/BOM.md`` (detected by a
markdown table header row containing ``Ref``, ``Part Number`` and ``Qty``
cells -- every real component table in this document uses that header, see
``parse_bom()``), and for every physical-component instantiation in
``elec/src/*.ato`` (every ``<var> = new <Type>`` where ``Type`` is itself
defined with the ``component`` keyword somewhere in ``elec/src/*.ato`` --
NOT the ``module``/``interface`` keywords, which mark composite
sub-assemblies and abstract electrical interfaces respectively, never a
single orderable part -- see ``parse_component_defaults()`` /
``physical_component_types()``), this gate matches BOM designator to source
variable name by normalized string identity (lowercased, non-alphanumeric
characters stripped: ``"C_TANK1"`` and ``"c_tank1"`` both normalize to
``"ctank1"``) and reports three classes of finding:

  1. COSTED-NO-CIRCUIT   -- a BOM designator with no normalized match among
                             any ``elec/src/*.ato`` instantiation.
  2. WIRED-UNCOSTED       -- an ``elec/src/*.ato`` instantiation whose
                             variable name has no normalized match among any
                             BOM designator.
  3. MPN-MISMATCH         -- a designator that DOES match on both sides, but
                             the MPN set on the BOM side and the MPN set on
                             the source side are completely disjoint (e.g.
                             BOM ``K_DIS1`` = ``G5LE-1 DC12``, source
                             ``k_dis1.mpn`` = ``RT314012``).

Exit codes (matching ``check_netlist_board_reconciliation.py`` /
``mpn_fabrication_gate.py`` convention):
  0 - PASSED: 0 non-allowlisted findings, across a real, non-empty check.
  3 - VIOLATION: at least one non-allowlisted finding in any of the 3 classes.
  5 - GATE ERROR: the gate could not run a trustworthy check at all (BOM.md
      missing/unparseable, zero .ato files, zero component instantiations
      parsed, or an allowlist present but unparseable). Never a silent pass.

WHY THIS IS A HEURISTIC, DOCUMENTED LIMITATION (read before trusting a
"clean" result or being surprised by a "dirty" one)
====================================================

Per ``docs/STRATEGY.md``'s "``default.net`` aliases part identity by
footprint -- use ``default.csv``" entry (2026-07-26) and this repo's
``Makefile``, the fully-authoritative way to answer "what part identity does
source assign to which board position" is atopile's build output,
specifically ``elec/build/default.csv`` (NOT ``default.net``, whose
``libsource`` field collapses every component sharing a footprint onto one
canonical libpart -- confirmed in that STRATEGY.md entry: 85 distinct BOM
parts collapsed to 40 ``libpart`` entries).

This gate does NOT build or parse that artifact as its primary path. Not
because the tooling is unavailable here -- it is: ``uv tool run --from
'atopile>=0.2,<0.3' ato --non-interactive build ...`` (the ``Makefile``'s
``netlist`` target) was run directly while authoring this gate and
succeeded, producing a real ``elec/build/default.csv``/``default.net`` pair
-- but because that artifact does NOT solve the core problem this gate has,
confirmed by actually reading the output it produced:

  ``elec/build/default.csv`` keys identity by the REAL, KiCad-annotated
  reference designator. Spot-checked directly against the build this gate's
  introduction produced: the discharge relays ``k_dis1``/``k_dis2`` land as
  ``K2``/``K3``; the tank capacitors ``c_tank1``/``c_tank2``/``c_tank3`` land
  as ``C25``/``C26``/``C27``; the OVP-01 sense-divider top resistors
  ``r_div_top1-3`` land as ``R51``/``R52``/``R53``; the OVP-01 ADC-tap
  resistors ``r_adc_top1-3`` land as ``R56``/``R57``/``R58``.
  ``docs/hardware/BOM.md``'s ``Ref`` column is NOT any of that. It is a
  human-authored, semantic/logical label chosen by whoever wrote each BOM
  row for readability (``R_OVP1-3``, ``K_DIS1``, ``R_OVP_REF_T``) -- it is
  neither the real annotated refdes NOR always the literal
  ``elec/src/*.ato`` variable name (compare: BOM's
  ``R_OVP_ADC_T``/``R_OVP_ADC_B`` vs. source's actual
  ``r_adc_top1``/``r_adc_top2``/``r_adc_top3``/``r_adc_bot`` -- there is no
  string transform connecting those two labels). Reading ``default.net``
  authoritatively answers "which real refdes is
  ``safety.ovp.r_adc_top1``" -- it also, separately, resolves this gate's own
  reused-variable-name ambiguity precisely via each instance's
  ``sheetpath``: spot-checked, ``r_ref_top``/``r_ref_bot``/``r_hyst`` (each
  declared 4x, once per comparator class) resolve to distinct
  ``safety.ocp``/``safety.thermal``/``safety.coil_thermal``/``safety.uvlo_logic``
  sheetpaths, confirming this gate's hand-verified
  ``bom-reconciliation-allowlist.yaml`` pairings (below) rather than
  contradicting them, and confirming ``SecondaryOCPComparator`` (OCP-02)
  truly has zero components in the compiled netlist (it is defined but
  never instantiated from ``Top`` -- not merely "excluded by policy"). But
  none of that gives an automatic answer for BOM.md's ``Ref`` column, which
  was never written in terms of real refdes in the first place: matching
  ``K2`` to ``K_DIS1`` still requires the same kind of human/semantic
  judgment this gate's allowlist already encodes by reading the source
  directly. Reading ``default.net`` narrows a different, real gap (this
  document vs. the physical board) that
  ``check_netlist_board_reconciliation.py`` already owns for the board side;
  it would upgrade this gate's reused-name disambiguation from
  hand-verified to mechanically-verified, but that is a larger follow-up
  (a new parser for atopile's netlist s-expression format, executed in CI
  where the artifact is built) than this change's scope, given the actual
  BOM-vs-label problem persists regardless.

CONCRETE CONSEQUENCES of the normalized-string-identity heuristic, so a
result here is read correctly:

  * FALSE POSITIVES (real match, reported as a mismatch): whenever a BOM
    author chose a label that doesn't literally transform to the source
    variable name. Confirmed cases at gate-introduction time: the OVP
    ADC-tap divider above; the OVP-01 sense/reference dividers (BOM's
    ``R_OVP_REF_T``/``R_OVP_REF_B`` vs. source, where that divider was
    deleted entirely in a 2026-07-27 redesign -- see
    ``docs/evidence/2026-07-26-ovp-crossing-resolution.md`` -- and BOM never
    absorbed the change, so this one is actually a TRUE positive, not a
    tooling artifact); any comparator reference divider built from a
    template class whose local variable name (e.g. ``r_ref_top``) is reused
    verbatim across several distinct comparator instances (OCP-01, THM-01,
    THM-02 each declare their OWN ``r_ref_top`` -- see
    ``mpn_fabrication_gate.py``'s module docstring, which documents the same
    reused-name convention for a different gate) while BOM.md assigns each
    instance a distinct, instance-specific label (``R_OCP_REF_T``,
    ``R_THM_REF_T``, ``R_THM2_REF_T``). These get allowlisted individually
    with a reason once triaged, exactly like ``mpn-fabrication-allowlist.yaml``
    handles its own false positives -- see ``bom-reconciliation-allowlist.yaml``.
  * FALSE NEGATIVES (real mismatch, not reported): this gate does not
    attempt fuzzy/prefix matching, so it cannot tell you two DIFFERENT
    normalized labels refer to the same physical part; it also cannot see
    quantity mismatches within a designator group, and it does not check
    Package/footprint agreement at all. It is a designator-identity and
    MPN-identity checker only.

Given both are real and documented, this gate's HONEST claim is narrower
than "the BOM reconciles" -- it is "every BOM/source component pair whose
designator label happens to be the same string, once case/underscores are
stripped, has an MPN that agrees" plus "every source/BOM label with no
string counterpart on the other side is flagged for human triage." That is
still strictly more coverage than the 0% this repo had before (nothing
parsed BOM.md at all), and every specific contradiction in the gap this gate
was built to close (K_DIS1/K_DIS2, C_TANK1-3, the OVP dividers) is caught by
exactly this heuristic -- see the anti-vacuity tests in
``scripts/tests/test_check_bom_source_reconciliation.py`` for seeded-defect
proof of each finding class.

Allowlist (``bom-reconciliation-allowlist.yaml``, hand-curated only, same
convention as ``mpn-fabrication-allowlist.yaml``): each entry suppresses one
``(kind, designator[, file])`` finding and requires a non-empty ``reason``.
There is no ``--init``/auto-regenerate mode, for the same reason
``mpn_fabrication_gate.py`` has none (see that module's docstring): an
allowlist a script can bulk-write to is not a safety net.

BACKLOG ENTRIES (``backlog: true``) vs. JUSTIFIED EXCEPTIONS
==============================================================

Two structurally distinct kinds of allowlist entry share this file:

  * JUSTIFIED EXCEPTIONS (the default shape, no ``backlog`` key): a
    hand-verified, permanent statement that a finding is NOT a content
    defect -- the BOM and source genuinely refer to the same part under
    different labels, or the part is deliberately out of ``elec/src``
    scope. ``reason`` explains *why the finding is wrong*, citing the
    source line(s), and is expected to stay in this file indefinitely.

  * BACKLOG ENTRIES (``backlog: true`` + ``seeded: "YYYY-MM-DD"``): a
    dated admission that a finding IS real, pre-existing drift, not yet
    triaged or fixed -- seeded in bulk on the date this gate first became
    a hard, non-``continue-on-error`` CI gate (2026-08-07), purely so the
    gate could go live without being reverted for blocking every PR on a
    pre-existing procurement backlog. A backlog entry's ``reason`` holds
    the finding's own verbatim detail (what the gate would otherwise have
    printed), NOT a justification -- there is no claim here that the
    finding is wrong.

    ``load_allowlist()`` fails closed (returns ``None``, same as any
    other malformed entry) if ``backlog: true`` appears without a valid
    ``seeded: "YYYY-MM-DD"`` date, or if ``seeded`` appears without
    ``backlog: true`` -- the two fields are required to travel together,
    so a backlog entry can never be hand-edited into looking like a plain
    justified one (or vice versa) by dropping just one field.

    ``run()`` always reports backlog-suppressed findings under their own
    banner and section, counted separately from both new findings and
    justified exceptions, on every single run (pass or fail) -- see the
    "N backlog finding(s) suppressed" line -- specifically so a growing
    backlog cannot fade into silent, permanent background noise the way a
    merged-in justified entry can. Run with ``--backlog-report`` to list
    every outstanding backlog entry (and whether it still matches a live
    finding) so the backlog can be worked down and the count watched
    falling.

Usage:
  uv run python scripts/check_bom_source_reconciliation.py
  uv run python scripts/check_bom_source_reconciliation.py --bom PATH --ato-glob 'elec/src/*.ato'
  uv run python scripts/check_bom_source_reconciliation.py --backlog-report
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root()
DEFAULT_BOM = REPO_ROOT / "docs" / "hardware" / "BOM.md"
DEFAULT_ATO_GLOB = "elec/src/*.ato"
DEFAULT_ALLOWLIST = REPO_ROOT / "bom-reconciliation-allowlist.yaml"

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

KIND_COSTED_NO_CIRCUIT = "costed_no_circuit"
KIND_WIRED_UNCOSTED = "wired_uncosted"
KIND_MPN_MISMATCH = "mpn_mismatch"
ALL_KINDS = (KIND_COSTED_NO_CIRCUIT, KIND_WIRED_UNCOSTED, KIND_MPN_MISMATCH)


# ---------------------------------------------------------------------------
# BOM.md parsing
# ---------------------------------------------------------------------------


@dataclass
class BomLine:
    designator: str  # single designator, after comma/range splitting
    ref_field: str  # original, un-split "Ref" cell text (for reporting)
    mpn: str
    qty_field: str  # original "Qty" cell text
    section: str
    line: int


_RANGE_RE = re.compile(r"^([A-Za-z_]+)(\d+)-(\d+)$")


def split_designators(ref_field: str) -> list[str]:
    """Split a BOM ``Ref`` cell into individual designators.

    Handles the two shapes this BOM uses: comma-separated lists
    (``"C_BUS1, C_BUS1B, C_BUS2, C_BUS2B"``) and one hyphenated range
    (``"R_OVP1-3"`` -> ``R_OVP1``, ``R_OVP2``, ``R_OVP3``). Every other
    ``Ref`` cell in the current document is a single bare token."""
    out: list[str] = []
    for token in ref_field.split(","):
        token = token.strip()
        if not token:
            continue
        m = _RANGE_RE.match(token)
        if m:
            prefix, lo, hi = m.group(1), int(m.group(2)), int(m.group(3))
            out.extend(f"{prefix}{i}" for i in range(lo, hi + 1))
        else:
            out.append(token)
    return out


def _split_table_row(line: str) -> list[str]:
    # Markdown table row: leading/trailing '|' optional, cells '|'-separated.
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def parse_bom(path: Path) -> list[BomLine]:
    """Parse every component table in BOM.md into individual BomLine rows.

    A "component table" is any markdown table whose header row contains
    cells ``Ref``, ``Part Number`` and ``Qty`` (every real per-component
    table in this document uses exactly that header, with or without a
    ``Package`` column -- confirmed: every ``^| Ref `` header line in the
    current document matches this shape). Summary/reference tables
    (Critical Long-Lead Items, Revision History, the DESAT risk table, the
    BOM-by-category summary) do not have this header and are skipped."""
    if not path.is_file():
        return []

    lines = path.read_text().splitlines()
    section = ""
    out: list[BomLine] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.startswith("#"):
            section = line.lstrip("#").strip()
            i += 1
            continue
        if line.startswith("|"):
            header = _split_table_row(line)
            if (
                "Ref" in header
                and "Part Number" in header
                and "Qty" in header
                and i + 1 < n
                and re.match(r"^\|?[\s:-]+\|", lines[i + 1])
            ):
                ref_i = header.index("Ref")
                mpn_i = header.index("Part Number")
                qty_i = header.index("Qty")
                i += 2  # header + separator
                while i < n and lines[i].startswith("|"):
                    row = _split_table_row(lines[i])
                    if len(row) > max(ref_i, mpn_i, qty_i):
                        ref_field = row[ref_i]
                        mpn = row[mpn_i]
                        qty_field = row[qty_i]
                        if ref_field and mpn:
                            for desig in split_designators(ref_field):
                                out.append(
                                    BomLine(
                                        designator=desig,
                                        ref_field=ref_field,
                                        mpn=mpn,
                                        qty_field=qty_field,
                                        section=section,
                                        line=i + 1,
                                    )
                                )
                    i += 1
                continue
        i += 1
    return out


# ---------------------------------------------------------------------------
# elec/src/*.ato parsing
# ---------------------------------------------------------------------------


@dataclass
class SourcePart:
    var: str
    type_: str
    mpn: str | None
    file: str
    line: int


COMPONENT_DEF_RE = re.compile(r"^component\s+([A-Za-z_][A-Za-z0-9_]*)\s*:")
CLASS_MPN_RE = re.compile(r'^\s+mpn\s*=\s*"([^"]+)"')
NEW_RE = re.compile(r"^\s*([a-z_][a-zA-Z0-9_]*)\s*=\s*new\s+([A-Za-z_][A-Za-z0-9_]*)")
MPN_RE = re.compile(r'^\s*([a-z_][a-zA-Z0-9_]*)\.mpn\s*=\s*"([^"]+)"')


def _in_block(line: str) -> bool:
    return line.strip() == "" or line[:1] in (" ", "\t")


def parse_component_defaults(ato_files: list[Path]) -> tuple[set[str], dict[str, str]]:
    """Return (physical_component_type_names, class_level_default_mpn).

    Every ``component <Name>:`` block (as opposed to ``module``/``interface``,
    which mark composite sub-assemblies / abstract electrical interfaces,
    never a single orderable part -- confirmed: ``grep -n '^component \\|^module
    \\|^interface ' elec/src/*.ato`` at gate-introduction time showed exactly
    34 ``component`` blocks, all in ``components.ato``, distinct from the
    ``module``-keyword footprint/sub-assembly helpers in ``footprints.ato``/
    ``modules.ato`` and the ``interface``-keyword electrical types in
    ``interfaces.ato``) contributes its name to the physical-type set. If the
    block also has a class-level ``mpn = "..."`` line (some components, e.g.
    ``Button``/``PinHeader_1x02``/``TestPoint``, declare a single fixed MPN
    for every instance rather than setting it per-instantiation), that MPN is
    recorded as the type's default."""
    types: set[str] = set()
    defaults: dict[str, str] = {}
    for path in ato_files:
        lines = path.read_text().splitlines()
        i = 0
        n = len(lines)
        while i < n:
            m = COMPONENT_DEF_RE.match(lines[i])
            if not m:
                i += 1
                continue
            name = m.group(1)
            types.add(name)
            i += 1
            mpn: str | None = None
            while i < n and _in_block(lines[i]):
                if mpn is None:
                    mm = CLASS_MPN_RE.match(lines[i])
                    if mm:
                        mpn = mm.group(1)
                i += 1
            if mpn is not None:
                defaults[name] = mpn
    return types, defaults


def parse_instances(
    ato_files: list[Path],
    physical_types: set[str],
    defaults: dict[str, str],
    repo_root: Path = REPO_ROOT,
) -> list[SourcePart]:
    """Return every physical-component instantiation, with its resolved MPN
    (per-instance ``.mpn =`` override if present, else the type's class-level
    default, else ``None``).

    Pairing an instance to its own (not some other reused-name instance's)
    ``.mpn =`` override uses the same "most recently declared var name wins"
    convention as ``mpn_fabrication_gate.py``'s ``parse_ato_file()`` -- see
    that function's docstring for why this is correct as long as a var's own
    ``new`` line always precedes its own ``.mpn =`` line in file order, which
    is this codebase's established convention.

    ``repo_root`` is only used to compute each part's reported ``file`` path
    (relative to it) -- takes an explicit parameter, like
    ``mpn_fabrication_gate.py``'s ``parse_ato_file()``, so tests can point it
    at a synthetic ``tmp_path`` tree instead of the real repo root."""
    parts: list[SourcePart] = []
    for path in ato_files:
        rel = str(path.relative_to(repo_root))
        lines = path.read_text().splitlines()
        open_idx: dict[str, int] = {}
        for lineno, line in enumerate(lines, start=1):
            m = NEW_RE.match(line)
            if m:
                var, typ = m.group(1), m.group(2)
                if typ in physical_types:
                    parts.append(
                        SourcePart(var=var, type_=typ, mpn=defaults.get(typ), file=rel, line=lineno)
                    )
                    open_idx[var] = len(parts) - 1
                else:
                    open_idx.pop(var, None)
                continue
            m2 = MPN_RE.match(line)
            if m2:
                var, mpn = m2.group(1), m2.group(2)
                idx = open_idx.get(var)
                if idx is not None:
                    parts[idx].mpn = mpn
    return parts


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


# ---------------------------------------------------------------------------
# Allowlist -- hand-curated only, same convention as mpn-fabrication-allowlist.yaml
# ---------------------------------------------------------------------------


@dataclass
class AllowlistEntry:
    kind: str
    designator: str
    file: str | None
    reason: str
    backlog: bool = False
    seeded: str | None = None


_SEEDED_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_allowlist(path: Path) -> list[AllowlistEntry] | None:
    """Load the hand-curated allowlist. Returns None on any parse failure
    (caller must treat that as a tool error, not an empty-but-valid list).

    Two entry shapes are accepted (see module docstring's "BACKLOG ENTRIES
    vs. JUSTIFIED EXCEPTIONS"): a plain justified exception (no ``backlog``/
    ``seeded`` keys), or a dated backlog entry (``backlog: true`` AND a
    ``seeded: "YYYY-MM-DD"`` string -- both required together, never just
    one). Either shape fails closed the same as a missing kind/designator/
    reason -- a backlog entry with a malformed date is not silently treated
    as either an empty allowlist or a justified one."""
    if not path.is_file():
        return []
    import yaml

    try:
        data = yaml.safe_load(path.read_text())
    except Exception:
        return None
    if data is None:
        return []
    if not isinstance(data, dict) or "allowlist" not in data:
        return None
    entries_raw = data["allowlist"]
    if not isinstance(entries_raw, list):
        return None
    entries: list[AllowlistEntry] = []
    for e in entries_raw:
        if not isinstance(e, dict):
            return None
        # Literal written at the call site on purpose: the cardinality of
        # the required-key set is baked into the source, so this all() can
        # never be a vacuous aggregation over a collection that turned out
        # empty at runtime (check_vacuous_gates.py's `_is_literal_source`
        # carve-out). Binding it to a name first hid that from the reader
        # and from the gate alike.
        if not all(k in e for k in ("kind", "designator", "reason")):
            return None
        if e["kind"] not in ALL_KINDS:
            return None
        if not isinstance(e["designator"], str) or not e["designator"].strip():
            return None
        if not isinstance(e["reason"], str) or not e["reason"].strip():
            return None
        file_val = e.get("file")
        if file_val is not None and not isinstance(file_val, str):
            return None
        backlog_val = e.get("backlog", False)
        if not isinstance(backlog_val, bool):
            return None
        seeded_val = e.get("seeded")
        if seeded_val is not None and not isinstance(seeded_val, str):
            return None
        if backlog_val:
            if not seeded_val or not seeded_val.strip() or not _SEEDED_DATE_RE.match(seeded_val.strip()):
                return None
            seeded_val = seeded_val.strip()
        else:
            # A plain justified entry must NOT carry a seeded date -- the
            # two fields travel together or not at all, so one can never be
            # dropped to blur a backlog entry into a justified-looking one.
            if seeded_val is not None:
                return None
        entries.append(
            AllowlistEntry(
                kind=e["kind"],
                designator=e["designator"],
                file=file_val,
                reason=e["reason"],
                backlog=backlog_val,
                seeded=seeded_val,
            )
        )
    return entries


def allowlist_covers(
    entries: list[AllowlistEntry], kind: str, designator: str, file: str | None = None
) -> AllowlistEntry | None:
    norm = normalize(designator)
    for e in entries:
        if e.kind != kind or normalize(e.designator) != norm:
            continue
        if e.file is not None and e.file != file:
            continue
        return e
    return None


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    kind: str
    designator: str
    detail: str
    allowlisted: bool
    allow_reason: str = ""
    file: str | None = None
    backlog: bool = False
    seeded: str | None = None


@dataclass
class Report:
    bom_lines: list[BomLine]
    source_parts: list[SourcePart]
    findings: list[Finding] = field(default_factory=list)

    @property
    def new_findings(self) -> list[Finding]:
        return [f for f in self.findings if not f.allowlisted]

    @property
    def allowlisted_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.allowlisted]

    @property
    def backlog_findings(self) -> list[Finding]:
        """Allowlisted findings suppressed by a dated BACKLOG entry --
        real, un-triaged drift, not a justified exception. Kept separate
        from ``justified_findings`` so a backlog can never be reported as
        (or silently mistaken for) hand-verified-clean."""
        return [f for f in self.findings if f.allowlisted and f.backlog]

    @property
    def justified_findings(self) -> list[Finding]:
        """Allowlisted findings suppressed by a plain, permanent justified
        exception (no ``backlog`` flag)."""
        return [f for f in self.findings if f.allowlisted and not f.backlog]


def reconcile(
    bom_lines: list[BomLine], source_parts: list[SourcePart], allowlist: list[AllowlistEntry]
) -> Report:
    bom_by_norm: dict[str, list[BomLine]] = {}
    for bl in bom_lines:
        bom_by_norm.setdefault(normalize(bl.designator), []).append(bl)

    src_by_norm: dict[str, list[SourcePart]] = {}
    for sp in source_parts:
        src_by_norm.setdefault(normalize(sp.var), []).append(sp)

    findings: list[Finding] = []

    # Direction 1: costed with no circuit.
    for norm, group in sorted(bom_by_norm.items()):
        if norm in src_by_norm:
            continue
        for bl in group:
            entry = allowlist_covers(allowlist, KIND_COSTED_NO_CIRCUIT, bl.designator)
            findings.append(
                Finding(
                    kind=KIND_COSTED_NO_CIRCUIT,
                    designator=bl.designator,
                    detail=(
                        f"BOM.md ({bl.section!r}, line {bl.line}) costs {bl.designator!r} as "
                        f"{bl.mpn!r}, but no elec/src/*.ato instantiation's variable name "
                        f"normalizes to match it"
                    ),
                    allowlisted=entry is not None,
                    allow_reason=entry.reason if entry else "",
                    backlog=entry.backlog if entry else False,
                    seeded=entry.seeded if entry else None,
                )
            )

    # Direction 2: wired but uncosted.
    for norm, group in sorted(src_by_norm.items()):
        if norm in bom_by_norm:
            continue
        for sp in group:
            entry = allowlist_covers(allowlist, KIND_WIRED_UNCOSTED, sp.var, sp.file)
            mpn_desc = repr(sp.mpn) if sp.mpn else "no MPN declared in source"
            findings.append(
                Finding(
                    kind=KIND_WIRED_UNCOSTED,
                    designator=sp.var,
                    detail=(
                        f"{sp.file}:{sp.line} instantiates {sp.var} = new {sp.type_} "
                        f"({mpn_desc}), but no BOM.md designator normalizes to match it"
                    ),
                    allowlisted=entry is not None,
                    allow_reason=entry.reason if entry else "",
                    file=sp.file,
                    backlog=entry.backlog if entry else False,
                    seeded=entry.seeded if entry else None,
                )
            )

    # Direction 3: same designator, disjoint MPN sets.
    for norm in sorted(set(bom_by_norm) & set(src_by_norm)):
        bom_group = bom_by_norm[norm]
        src_group = src_by_norm[norm]
        bom_mpns = {bl.mpn for bl in bom_group}
        src_mpns = {sp.mpn for sp in src_group if sp.mpn is not None}
        if not bom_mpns or not src_mpns:
            continue
        if not bom_mpns.isdisjoint(src_mpns):
            continue
        desig = bom_group[0].designator
        entry = allowlist_covers(allowlist, KIND_MPN_MISMATCH, desig)
        src_desc = ", ".join(f"{sp.file}:{sp.line} mpn={sp.mpn!r}" for sp in src_group)
        findings.append(
            Finding(
                kind=KIND_MPN_MISMATCH,
                designator=desig,
                detail=(
                    f"designator {desig!r} matches on both sides but MPN sets disagree: "
                    f"BOM={sorted(bom_mpns)!r} vs. source [{src_desc}]"
                ),
                allowlisted=entry is not None,
                allow_reason=entry.reason if entry else "",
                backlog=entry.backlog if entry else False,
                seeded=entry.seeded if entry else None,
            )
        )

    return Report(bom_lines=bom_lines, source_parts=source_parts, findings=findings)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def run(
    bom_path: Path,
    ato_glob: str,
    allowlist_path: Path,
    src_root: Path = REPO_ROOT,
    backlog_report: bool = False,
) -> int:
    """``src_root`` is the base ``ato_glob`` is resolved against (and the
    base ``parse_instances()`` reports each part's ``file`` relative to) --
    an explicit parameter, like ``check_netlist_board_reconciliation.py``'s
    ``--src-dir``, so tests can point it at a synthetic ``tmp_path`` tree
    instead of the real repo root.

    ``backlog_report``, if set, prints an additional section listing every
    dated BACKLOG allowlist entry and whether it still matches a live
    finding (vs. STALE -- the underlying drift got fixed and the entry can
    be deleted). Purely additive: it never changes the pass/fail exit
    code, which is always governed solely by ``report.new_findings``."""
    if not bom_path.is_file():
        print(f"[BOM-RECONCILIATION-GATE-ERROR] BOM not found: {bom_path}", file=sys.stderr)
        return EXIT_GATE_ERROR

    bom_lines = parse_bom(bom_path)
    if not bom_lines:
        print(
            f"[BOM-RECONCILIATION-GATE-ERROR] 0 component rows parsed from {bom_path}. "
            "Either the BOM has no component tables (implausible) or parse_bom()'s header "
            "detection has drifted from the document's table format -- either way this is a "
            "tool error, never a pass.",
            file=sys.stderr,
        )
        return EXIT_GATE_ERROR

    ato_files = sorted(src_root.glob(ato_glob))
    if not ato_files:
        print(
            f"[BOM-RECONCILIATION-GATE-ERROR] No .ato files matched glob {ato_glob!r} under "
            f"{src_root}.",
            file=sys.stderr,
        )
        return EXIT_GATE_ERROR

    physical_types, defaults = parse_component_defaults(ato_files)
    if not physical_types:
        print(
            "[BOM-RECONCILIATION-GATE-ERROR] 0 `component <Name>:` blocks found across "
            f"{len(ato_files)} .ato file(s) -- the physical-component-type detector has "
            "drifted from the source syntax.",
            file=sys.stderr,
        )
        return EXIT_GATE_ERROR

    source_parts = parse_instances(ato_files, physical_types, defaults, src_root)
    if not source_parts:
        print(
            "[BOM-RECONCILIATION-GATE-ERROR] 0 physical-component instantiations parsed from "
            f"{len(ato_files)} .ato file(s) (0 `<var> = new <Type>` lines where Type is one of "
            f"the {len(physical_types)} known component types). This is a tool error, never a "
            "pass -- a 155-component design instantiating zero components is implausible.",
            file=sys.stderr,
        )
        return EXIT_GATE_ERROR

    allowlist = load_allowlist(allowlist_path)
    if allowlist is None:
        print(
            f"[BOM-RECONCILIATION-GATE-ERROR] Allowlist at {allowlist_path} exists but could "
            "not be parsed (bad YAML or missing required fields: kind/designator/reason on "
            "some entry). Failing closed rather than silently treating it as empty.",
            file=sys.stderr,
        )
        return EXIT_GATE_ERROR

    report = reconcile(bom_lines, source_parts, allowlist)

    print(f"BOM: {bom_path}")
    print(f"Source: {len(ato_files)} .ato file(s) matching {ato_glob!r}")
    print(
        f"Parsed {len(bom_lines)} BOM designator row(s) and {len(source_parts)} source "
        f"component instantiation(s) ({len(physical_types)} known physical component types)."
    )
    print(f"Allowlist entries loaded: {len(allowlist)}")

    new_findings = report.new_findings
    justified = report.justified_findings
    backlog = report.backlog_findings

    by_kind: dict[str, list[Finding]] = {}
    for f in new_findings:
        by_kind.setdefault(f.kind, []).append(f)

    if justified:
        print(f"\n=== ALLOWLISTED -- justified exceptions (suppressed, {len(justified)}) ===")
        for f in justified:
            print(f"  [{f.kind}] {f.designator}: {f.allow_reason}")

    seeded_dates = sorted({f.seeded for f in backlog if f.seeded})
    seeded_desc = ", ".join(seeded_dates) if seeded_dates else "n/a"

    if backlog:
        print(
            f"\n=== ALLOWLISTED -- BACKLOG (suppressed, {len(backlog)}; seeded {seeded_desc}; "
            "NOT justified exceptions -- real, un-triaged drift, see "
            f"{allowlist_path.name}'s docstring) ==="
        )
        for f in backlog:
            print(f"  [{f.kind}] {f.designator}: {f.allow_reason}")

    # Printed on EVERY run, pass or fail, so a growing backlog can never
    # fade into silent background noise the way a merged-in justified
    # entry can -- see module docstring's "BACKLOG ENTRIES vs. JUSTIFIED
    # EXCEPTIONS".
    backlog_banner = (
        f"{len(backlog)} backlog finding(s) suppressed (seeded {seeded_desc}); "
        f"{len(new_findings)} new finding(s)."
    )
    print(f"\n{backlog_banner}")

    if backlog_report:
        print("\n=== BACKLOG REPORT ===")
        backlog_entries = [e for e in allowlist if e.backlog]
        if not backlog_entries:
            print("  (no backlog entries in allowlist)")
        else:
            live_counts: dict[tuple[str, str, str | None], int] = {}
            for f in backlog:
                live_counts[(f.kind, normalize(f.designator), f.file)] = (
                    live_counts.get((f.kind, normalize(f.designator), f.file), 0) + 1
                )
            for e in sorted(backlog_entries, key=lambda e: (e.kind, e.designator)):
                key = (e.kind, normalize(e.designator), e.file)
                n = live_counts.get(key, 0)
                status = f"{n} live finding(s)" if n else "STALE -- 0 live findings, safe to remove"
                scope = f" ({e.file})" if e.file else ""
                print(f"  [{e.kind}] {e.designator}{scope} -- seeded {e.seeded}: {status}")
            print(
                f"\n  {len(backlog_entries)} backlog entry/entries in {allowlist_path.name}, "
                f"{len(backlog)} live backlogged finding(s) suppressed this run."
            )

    gh = get_github_summary_path()

    if not new_findings:
        print(
            f"\nPASSED -- 0 new finding(s) across {len(bom_lines)} BOM row(s) / "
            f"{len(source_parts)} source instantiation(s)."
        )
        if gh:
            with open(gh, "a") as fh:
                fh.write("### BOM<->Source Reconciliation Gate -- PASSED\n")
                fh.write(f"0 new finding(s). {len(justified)} justified exception(s) allowlisted. ")
                fh.write(f"{backlog_banner}\n")
        return EXIT_OK

    print(f"\n=== FINDINGS: {len(new_findings)} ===")
    gh_lines: list[str] = []
    for kind in ALL_KINDS:
        kind_findings = by_kind.get(kind, [])
        if not kind_findings:
            continue
        print(f"\n  [{kind}] {len(kind_findings)} finding(s):")
        for f in kind_findings:
            print(f"    {f.detail}")
            gh_lines.append(f"- `[{kind}]` {f.detail}")

    if gh:
        with open(gh, "a") as fh:
            fh.write("### BOM<->Source Reconciliation Gate -- FAILED\n")
            fh.write(
                f"{len(new_findings)} finding(s) ({len(justified)} justified exception(s) "
                f"allowlisted). {backlog_banner}\n\n"
            )
            for line in gh_lines[:200]:
                fh.write(line + "\n")

    print(f"\nFAILED -- {len(new_findings)} finding(s)")
    print(backlog_banner)
    print(
        "Remediation: either fix the drift (BOM.md or elec/src, maintainer's call -- this gate "
        "only detects), or if the finding is a genuine, deliberate exception (e.g. a chassis "
        "part intentionally out of elec/src scope, or a reused generic template variable name "
        f"that a real netlist would disambiguate), add a justified entry to "
        f"{allowlist_path.name} (hand-edited only -- see module docstring). Pre-existing, "
        "not-yet-triaged drift belongs in a dated BACKLOG entry (backlog: true, seeded: "
        "\"YYYY-MM-DD\"), never a justified one."
    )
    return EXIT_VIOLATION


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--bom", type=Path, default=DEFAULT_BOM)
    parser.add_argument("--ato-glob", default=DEFAULT_ATO_GLOB)
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument(
        "--backlog-report",
        action="store_true",
        help="List every dated BACKLOG allowlist entry and whether it still matches a live "
        "finding (vs. STALE, safe to remove), so the backlog can be worked down and its count "
        "watched falling. Purely additive -- never changes the exit code.",
    )
    args = parser.parse_args()
    sys.exit(run(args.bom, args.ato_glob, args.allowlist, backlog_report=args.backlog_report))


if __name__ == "__main__":
    main()
