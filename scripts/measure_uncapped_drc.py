#!/usr/bin/env python3
"""Uncapped DRC violation counting for kicad-cli-saturated categories.

Core idea: kicad-cli's DRC JSON caps every category at ERROR_LIMIT (199) or
EXTENDED_ERROR_LIMIT (499) -- a GUI list-widget constant baked into
drc_engine.cpp, not a property of the board. To get a TRUE count for a
category that sits at/near its cap, partition the space of item-pairs (or
items, for unary checks) into buckets that are PROVABLY exhaustive (every
violation falls in exactly one bucket) and non-overlapping (no violation is
double-counted), measure each bucket with a scoped kicad-cli run that keeps
it comfortably under the cap, and sum.

Two families of partition are implemented, chosen by what governs the
category:

  * DRU-rule-governed categories (clearance, creepage, track_width): the
    .kicad_dru file's own rules already partition item-pairs by which rule
    is the LAST MATCHING one (KiCad: last-matching-rule-wins). Given a
    *shadow-free* DRU (RuleShadowingError guard passed -- see
    scripts/generate_kicad_dru.py on fix/dru-rule-precedence), the winner
    for a pair is simply the matching rule ranked highest by `min` value,
    ties broken by original authored order -- exactly the tie-break the
    fixed generator's own topological sort uses. We isolate rule R's own
    band with a synthetic 2-rule DRU: rule 1 = "everything NOT matching R
    (after R is AND-NOT'd against every strictly-higher-ranked rule)" with
    `(severity ignore)` (evaluated, but never reported and -- verified
    empirically below -- never consumes the category's report budget
    either); rule 2 = R's own condition, AND-NOT every strictly-higher rule,
    at R's real value. This is provably exhaustive (every pair matches rule
    1 or rule 2, never neither) and non-overlapping (rule 2's condition is
    disjoint from every other rule's isolated condition by construction).
    A band still at/near the cap is recursively bisected by the REAL net
    names in its own anchoring net class (not a class abstraction -- the
    literal net names present on pcb/temper.kicad_pcb today), which is
    itself exhaustive+disjoint since every copper item has exactly one net.

  * Non-DRU categories (shorting_items: different-net items in electrical
    contact; silk_overlap: silkscreen-vs-silkscreen graphic overlap): these
    carry no `rule` attribution in kicad-cli's own JSON (verified: their
    "description" field never contains "rule '...'"), so there is no DRU
    condition to isolate them with. Instead we physically partition the
    BOARD CONTENT via exact byte-preserving S-expression block deletion
    (NOT a parse/reserialize round trip -- kiutils was tried and rejected:
    round-tripping pcb/temper.kicad_pcb through kiutils with ZERO edits
    still changes shorting_items 199->58 and hole_clearance 105->116, i.e.
    it silently perturbs geometry on save). shorting_items is partitioned
    by net-name bucket pairs (every copper item has exactly one net);
    silk_overlap is partitioned by footprint-reference bucket pairs
    (silkscreen graphics belong to a footprint, not a net).

Never modifies pcb/temper.kicad_pcb. All scratch boards live under a
caller-supplied directory outside the repo.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(
    os.environ.get("UNCAPPED_DRC_REPO_ROOT", str(Path(__file__).resolve().parent.parent))
)
PCB_DIR = REPO_ROOT / "pcb"

# --all-track-errors is documented (and observed here) to overshoot its
# nominal limit by a variable amount (0 up to ~14 measured in this session,
# 0-6 in the precedence doc) because the limit is checked between whole
# per-track batches, not per violation. Treat anything within this margin
# of a known limit as "still saturated, must split further".
SAFE_MARGIN = 20  # cap-detection threshold. Determinism (see
# `_verified_count`) is the primary signal; this margin is just a first filter.


def cap_for(ctype: str) -> int:
    """Delegate reporting-cap authority to ``temper-drc-rs``."""
    import temper_drc_rs  # type: ignore[import-untyped]

    cap = temper_drc_rs.drc_cap_for(ctype)
    if cap is None:
        raise ValueError(f"{ctype!r} is not a capped KiCad category")
    return int(cap)


def default_safe_ceiling(ctype: str) -> int:
    return cap_for(ctype) - SAFE_MARGIN


# ---------------------------------------------------------------------------
# Scratch board setup / kicad-cli invocation
# ---------------------------------------------------------------------------


def make_scratch_board(dst: Path, pcb_text: str | None = None) -> Path:
    """Populate `dst` with a scratch copy of the real board + project
    context. `pcb_text`, if given, replaces temper.kicad_pcb's content
    (used by the physical-partition path); otherwise the committed file is
    copied byte-for-byte. Never touches pcb/temper.kicad_pcb itself."""
    dst.mkdir(parents=True, exist_ok=True)
    if pcb_text is None:
        shutil.copy(PCB_DIR / "temper.kicad_pcb", dst / "temper.kicad_pcb")
    else:
        (dst / "temper.kicad_pcb").write_text(pcb_text)
    shutil.copy(PCB_DIR / "temper.kicad_pro", dst / "temper.kicad_pro")
    shutil.copy(PCB_DIR / "temper.kicad_dru", dst / "temper.kicad_dru")
    shutil.copy(PCB_DIR / "fp-lib-table", dst / "fp-lib-table")
    libs_dst = dst / "libs"
    if not libs_dst.exists():
        shutil.copytree(PCB_DIR / "libs", libs_dst)
    return dst


def run_kicad_drc(board_dir: Path, dru_text: str | None) -> dict:
    """Run the canonical strict raw-report seam in a staged scratch project."""
    dru_path = board_dir / "temper.kicad_dru"
    if dru_text is not None:
        dru_path.write_text(dru_text)
    from temper_placer.validation._drc_api import run_drc_measurement

    return run_drc_measurement(board_dir / "temper.kicad_pcb", strict=True).raw_report


# Every violation-shaped top-level array kicad-cli emits, in the repo's
# canonical order. This MUST stay equal to
# ``temper_placer.validation._drc_api._VIOLATION_ARRAY_KEYS`` -- pinned by
# ``scripts/tests/test_drc_report_array_keys.py``, because a divergence
# here is exactly the defect that hid 339 unconnected_items from every DRC
# number this project ever recorded.
#
# This module previously counted ``violations`` only, while its own
# ``_EXTENDED_CATEGORIES`` table above names ``unconnected_items`` as a
# 499-capped category -- so asking this tool for the true uncapped count of
# ``unconnected_items`` returned 0, contradicting its own cap table. A tool
# that reports 0 for a category it knows exists is worse than one that
# refuses: 0 reads as "solved".
_VIOLATION_ARRAY_KEYS = ("violations", "unconnected_items", "schematic_parity")


def _all_violations(drc_json: dict) -> list:
    """Every violation kicad-cli reported, across all of its top-level
    violation arrays -- not just ``violations``."""
    out: list = []
    for key in _VIOLATION_ARRAY_KEYS:
        out.extend(drc_json.get(key, []))
    return out


def category_counts(drc_json: dict) -> dict:
    from collections import Counter

    return dict(Counter(v["type"] for v in _all_violations(drc_json)))


def category_count(board_dir: Path, dru_text: str | None, category: str) -> int:
    data = run_kicad_drc(board_dir, dru_text)
    return sum(1 for v in _all_violations(data) if v["type"] == category)


# ---------------------------------------------------------------------------
# DRU rule parsing (independent of scripts/generate_kicad_dru.py so this
# tool works whether or not that generator's fix has landed -- caller
# supplies the .kicad_dru text to analyse).
# ---------------------------------------------------------------------------


@dataclass
class DruRuleInfo:
    name: str
    condition: str
    constraints: dict  # constraint type -> min value (mm)


_RULE_RE = re.compile(r'\(rule\s+"((?:[^"\\]|\\.)*)"', re.MULTILINE)


def _find_balanced(text: str, open_idx: int) -> int:
    """Given the index of an '(' , return the index just past its matching ')'."""
    depth = 0
    i = open_idx
    in_str = False
    while i < len(text):
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return i + 1
        i += 1
    raise ValueError("unbalanced parens")


def parse_dru_rules(dru_text: str) -> list[DruRuleInfo]:
    """Parse every `(rule "name" ...)` block into name/condition/constraints.
    Strips `#`-comments first (outside quoted strings)."""
    lines = []
    for line in dru_text.splitlines():
        stripped = line
        if "#" in line and '"' not in line.split("#", 1)[0]:
            stripped = line.split("#", 1)[0]
        lines.append(stripped)
    text = "\n".join(lines)

    rules = []
    for m in _RULE_RE.finditer(text):
        rule_start = m.start()
        block_end = _find_balanced(text, rule_start)
        block = text[rule_start:block_end]
        name = m.group(1)
        cond_m = re.search(r'\(condition\s+"((?:[^"\\]|\\.)*)"\)', block)
        condition = cond_m.group(1) if cond_m else None
        constraints = {}
        for cm in re.finditer(r"\(constraint\s+(\w+)\s+\(min\s+([0-9.]+)mm\)\)", block):
            constraints[cm.group(1)] = float(cm.group(2))
        if condition is not None and constraints:
            rules.append(DruRuleInfo(name=name, condition=condition, constraints=constraints))
    return rules


NETCLASS_RE = re.compile(r"A\.NetClass\s*==\s*'([^']+)'")


def anchor_class(condition: str) -> str | None:
    """The single `A.NetClass == 'X'` class this condition's A-side
    anchors on, if there is exactly one occurrence -- used to pick a
    splitting axis when a band still saturates."""
    classes = set(NETCLASS_RE.findall(condition))
    if len(classes) == 1:
        return next(iter(classes))
    return None


def isolation_dru(band_condition: str, value: float, ctype: str, label: str) -> str:
    """A 2-rule DRU: rule 1 ignores everything NOT matching
    band_condition (so it never contributes to ctype's reported count);
    rule 2 enforces `value` on exactly band_condition, at ctype. Rule 2 is
    emitted LAST, so KiCad's last-matching-rule-wins gives band_condition
    pairs the real `value` and gives everyone else `ignore` (never
    reported)."""
    safe_label = label.replace('"', "'")
    return f"""(version 1)

(rule "{safe_label} -- everyone else, ignored"
   (constraint {ctype} (min 0.001mm))
   (severity ignore)
   (condition "!({band_condition})")
)

(rule "{safe_label}"
   (constraint {ctype} (min {value}mm))
   (condition "{band_condition}")
)
"""


# ---------------------------------------------------------------------------
# Real net-name -> net-class map, from the committed board's OWN ground
# truth (pcb/temper.kicad_pro's netclass_assignments + netclass_patterns),
# not the Python SSOT layer -- this is what kicad-cli itself will use, so
# it cannot drift from the measurement.
# ---------------------------------------------------------------------------


def real_net_names() -> list[str]:
    text = (PCB_DIR / "temper.kicad_pcb").read_text()
    return sorted(set(re.findall(r'\(net \d+ "([^"]*)"\)', text)) - {""})


def net_class_map() -> dict[str, str]:
    pro = json.loads((PCB_DIR / "temper.kicad_pro").read_text())
    ns = pro["net_settings"]
    assignments: dict[str, str] = ns.get("netclass_assignments", {})
    patterns = ns.get("netclass_patterns", [])
    out = {}
    for name in real_net_names():
        if name in assignments:
            out[name] = assignments[name]
            continue
        cls = "Default"
        for p in patterns:
            if fnmatch.fnmatchcase(name, p["pattern"]):
                cls = p["netclass"]
                break
        out[name] = cls
    return out


def names_in_class(cls: str, netmap: dict[str, str]) -> list[str]:
    return sorted(n for n, c in netmap.items() if c == cls)


def netname_disjunction(side: str, names: list[str]) -> str:
    return "(" + " || ".join(f"{side}.NetName == '{n}'" for n in names) + ")"


def _verified_count(
    board_dir: Path, dru_text: str, ctype: str, safe_ceiling: int
) -> tuple[int, bool]:
    """Run the isolation DRU; if the result is anywhere near a plausible
    saturation zone, rerun once more. Returns (count, nondeterministic).
    A count that repeats exactly is treated as exact even if the safe
    margin alone would have flagged it -- determinism, not proximity to a
    round number, is what distinguishes a true count from a capped one
    (docs/evidence/2026-08-12-dru-rule-precedence.md sec 5.1: capped
    categories vary run-to-run at a fixed board; true ones don't)."""
    n1 = category_count(board_dir, dru_text, ctype)
    if n1 < safe_ceiling - 40:
        return n1, False
    n2 = category_count(board_dir, dru_text, ctype)
    return max(n1, n2), n1 != n2


# ---------------------------------------------------------------------------
# Recursive, provably-exhaustive measurement of one rule's band
# ---------------------------------------------------------------------------


@dataclass
class BandResult:
    label: str
    condition: str
    value: float
    count: int
    leaves: list = field(default_factory=list)  # sub-BandResults if split
    note: str = ""


def _measure_pool(
    board_dir: Path,
    ctype: str,
    label: str,
    rule_condition: str,
    negation_suffix: str,
    value: float,
    anchor_class_name: str,
    pool: list[str],
    safe_ceiling: int,
    _depth: int = 0,
) -> BandResult:
    """Measure the slice of `rule_condition`'s band restricted to A-side
    net names in `pool` (a subset of the real nets in anchor_class_name).
    Bisects `pool` and recurses if still saturated. `pool` partitions are
    disjoint subsets of the SAME real net-name list, so every recursion
    step is exhaustive+non-overlapping by construction, not merely
    plausible."""
    restricted = rule_condition.replace(
        f"A.NetClass == '{anchor_class_name}'", netname_disjunction("A", pool)
    )
    full_condition = restricted + negation_suffix
    dru = isolation_dru(full_condition, value, ctype, label)
    n, nondeterministic = _verified_count(board_dir, dru, ctype, safe_ceiling)

    if (n < safe_ceiling and not nondeterministic) or len(pool) == 1:
        note = ""
        if n >= safe_ceiling or nondeterministic:
            det = (
                "non-deterministic across reruns"
                if nondeterministic
                else f"n={n} >= safe ceiling {safe_ceiling}"
            )
            note = (
                f"SATURATION SUSPECTED ({det}) but net {pool[0]!r} is a single "
                "real net -- cannot split further. Reporting as a LOWER BOUND, "
                "not a true count."
            )
        return BandResult(label=label, condition=full_condition, value=value, count=n, note=note)

    mid = len(pool) // 2
    halves = [pool[:mid], pool[mid:]]
    leaves = []
    total = 0
    for half in halves:
        sub = _measure_pool(
            board_dir,
            ctype,
            f"{label} [{anchor_class_name} {len(half)}/{len(pool)}]",
            rule_condition,
            negation_suffix,
            value,
            anchor_class_name,
            half,
            safe_ceiling,
            _depth + 1,
        )
        leaves.append(sub)
        total += sub.count
    return BandResult(
        label=label,
        condition=full_condition,
        value=value,
        count=total,
        leaves=leaves,
        note=f"split on real net names of class {anchor_class_name!r} ({len(pool)} nets); n_before_split={n}",
    )


def measure_rule_band(
    board_dir: Path,
    ctype: str,
    rule: DruRuleInfo,
    value: float,
    negation_suffix: str,
    netmap: dict[str, str],
    safe_ceiling: int | None = None,
) -> BandResult:
    """Measure one ranked rule's true, exhaustive, non-overlapping
    contribution: pairs matching `rule.condition` AND NOT any
    strictly-higher-ranked rule (already folded into `negation_suffix`).
    Splits by real net name on the rule's own A-anchor class if the
    isolated count is at/near the cap."""
    if safe_ceiling is None:
        safe_ceiling = default_safe_ceiling(ctype)
    full_condition = rule.condition + negation_suffix
    dru = isolation_dru(full_condition, value, ctype, rule.name)
    n, nondeterministic = _verified_count(board_dir, dru, ctype, safe_ceiling)
    if n < safe_ceiling and not nondeterministic:
        return BandResult(label=rule.name, condition=full_condition, value=value, count=n)

    cls = anchor_class(rule.condition)
    if cls is None:
        return BandResult(
            label=rule.name,
            condition=full_condition,
            value=value,
            count=n,
            note=(
                f"SATURATION SUSPECTED (n={n} >= safe ceiling {safe_ceiling}) but "
                "this rule's own condition has no single A.NetClass anchor to "
                "split on automatically -- reporting the capped/near-capped "
                "read as a LOWER BOUND, not a true count."
            ),
        )
    pool = names_in_class(cls, netmap)
    if len(pool) < 2:
        return BandResult(
            label=rule.name,
            condition=full_condition,
            value=value,
            count=n,
            note=(
                f"SATURATION SUSPECTED (n={n}) but anchor class {cls!r} has only "
                f"{len(pool)} real net(s) on the board -- cannot split further. "
                "Reporting as a LOWER BOUND."
            ),
        )
    return _measure_pool(
        board_dir, ctype, rule.name, rule.condition, negation_suffix, value, cls, pool, safe_ceiling
    )


def measure_category_exhaustive(
    board_dir: Path, dru_text: str, ctype: str, netmap: dict[str, str]
) -> dict:
    """Full exhaustive/non-overlapping true count for a DRU-rule-governed
    category: every rule's own band (post AND-NOT of every rule ranked
    ahead of it) plus, for `clearance` only, the netclass-implicit
    fallback band (pairs no explicit rule matches -- kicad falls through
    to the project's own per-netclass clearance). Returns a dict with
    'total' and 'bands' (each a BandResult tree) for provenance.

    Rules are ranked strictly by descending `min` value; ties are broken
    by original parse (authored) order -- the SAME tie-break the fixed
    generator's own Kahn topological sort uses (order_rules_by_strictness
    in scripts/generate_kicad_dru.py on fix/dru-rule-precedence) -- so this
    reproduces KiCad's actual last-matching-rule-wins winner for every pair
    exactly. No two rules are ever merged into one combined band, which is
    what makes automatic net-name splitting possible per-rule."""
    rules = parse_dru_rules(dru_text)
    typed = [r for r in rules if ctype in r.constraints]
    ranked = sorted(typed, key=lambda r: -r.constraints[ctype])  # stable: ties keep parse order

    bands = []
    total = 0
    higher_conditions: list[str] = []
    for r in ranked:
        value = r.constraints[ctype]
        negation_suffix = (
            ""
            if not higher_conditions
            else " && " + " && ".join(f"!({c})" for c in higher_conditions)
        )
        result = measure_rule_band(board_dir, ctype, r, value, negation_suffix, netmap)
        bands.append(result)
        total += result.count
        higher_conditions.append(r.condition)

    fallback = None
    if ctype == "clearance":
        all_cond = " || ".join(f"({r.condition})" for r in typed)
        fb_dru = f"""(version 1)

(rule "explicit-rule-governed, ignored for fallback measurement"
   (constraint clearance (min 0.001mm))
   (severity ignore)
   (condition "{all_cond}")
)
"""
        fb_count = category_count(board_dir, fb_dru, ctype)
        note = ""
        if fb_count >= default_safe_ceiling("clearance"):
            note = (
                f"SATURATION SUSPECTED (n={fb_count}) -- fallback bucket spans "
                "many netclass pairs at once and has no single rule condition "
                "to split automatically. Reporting as a LOWER BOUND."
            )
        fallback = BandResult(
            label="netclass-implicit fallback (no explicit DRU rule matches)",
            condition=f"!({all_cond})",
            value=float("nan"),
            count=fb_count,
            note=note,
        )
        total += fallback.count
        bands.append(fallback)

    return {"ctype": ctype, "total": total, "bands": bands}


def band_tree_to_dict(b: BandResult) -> dict:
    return {
        "label": b.label,
        "value": b.value,
        "count": b.count,
        "note": b.note,
        "leaves": [band_tree_to_dict(leaf) for leaf in b.leaves],
    }


# ---------------------------------------------------------------------------
# Physical board partitioning for non-DRU-governed categories
# (shorting_items, silk_overlap): exact byte-preserving S-expression block
# deletion on the RAW committed text -- not a parse/reserialize round trip.
# ---------------------------------------------------------------------------


def _toplevel_block_spans(text: str, keyword: str) -> list[tuple[int, int]]:
    """Spans of every direct child of `(kicad_pcb ...)` starting with
    `(keyword `, at the file's own 2-space top-level indent."""
    spans = []
    for m in re.finditer(rf"(?m)^  \({keyword} ", text):
        start = m.start() + 2  # the '('
        end = _find_balanced(text, start)
        spans.append((start, end))
    return spans


def _net_of_block(text: str, start: int, end: int) -> int | None:
    m = re.search(r"\(net (\d+)", text[start:end])
    return int(m.group(1)) if m else None


def _pad_spans_in(text: str, fp_start: int, fp_end: int) -> list[tuple[int, int]]:
    spans = []
    for m in re.finditer(r"(?m)^    \(pad ", text[fp_start:fp_end]):
        s = fp_start + m.start() + 4
        e = _find_balanced(text, s)
        spans.append((s, e))
    return spans


def board_text_filtered_by_nets(pcb_text: str, keep_net_names: set[str]) -> str:
    """Return board text with every copper item (pad, segment, arc, via,
    zone) whose net is NOT in `keep_net_names` deleted -- footprints and
    every non-copper attribute untouched byte-for-byte for kept items.
    Net numbers are resolved via the file's own `(net N "name")` header
    declarations (left in place; unused net numbers referenced by nothing
    are harmless)."""
    net_num_to_name = dict(re.findall(r'\(net (\d+) "([^"]*)"\)', pcb_text))
    keep_nums = {n for n, name in net_num_to_name.items() if name in keep_net_names}

    deletions: list[tuple[int, int]] = []

    for kind in ("segment", "arc", "via", "zone"):
        for s, e in _toplevel_block_spans(pcb_text, kind):
            net = _net_of_block(pcb_text, s, e)
            # net 0 ("no net") items are never deleted, matching the pad
            # handling below -- consistency matters here: an earlier version
            # of this function deleted net-0 segments/vias/zones in every
            # bucket run (while never deleting net-0 PADS), an asymmetry
            # that silently and permanently excluded any such item from
            # every partition run. Left uncorrected this systematically
            # undercounts whatever real violations involve them.
            if net is not None and net != 0 and str(net) not in keep_nums:
                deletions.append((s, e))

    for fp_s, fp_e in _toplevel_block_spans(pcb_text, "footprint"):
        for pad_s, pad_e in _pad_spans_in(pcb_text, fp_s, fp_e):
            net = _net_of_block(pcb_text, pad_s, pad_e)
            if net is not None and str(net) not in keep_nums and net != 0:
                deletions.append((pad_s, pad_e))

    deletions.sort()
    out = []
    cursor = 0
    for s, e in deletions:
        if s < cursor:
            continue  # overlapping/nested, skip (shouldn't happen by construction)
        out.append(pcb_text[cursor:s])
        cursor = e
    out.append(pcb_text[cursor:])
    return "".join(out)


def board_text_filtered_by_refs(pcb_text: str, keep_refs: set[str]) -> str:
    """Return board text with every footprint whose reference designator
    is NOT in `keep_refs` deleted entirely, and every track/via/zone
    dropped outright (irrelevant to silk_overlap, and removing them
    shrinks/speeds every scratch run). Kept footprints are byte-identical
    to the original, including their silkscreen graphics."""
    deletions: list[tuple[int, int]] = []
    for kind in ("segment", "arc", "via", "zone"):
        deletions.extend(_toplevel_block_spans(pcb_text, kind))

    for fp_s, fp_e in _toplevel_block_spans(pcb_text, "footprint"):
        block = pcb_text[fp_s:fp_e]
        m = re.search(r'\(property "Reference" "([^"]*)"', block)
        ref = m.group(1) if m else None
        if ref not in keep_refs:
            deletions.append((fp_s, fp_e))

    deletions.sort()
    out = []
    cursor = 0
    for s, e in deletions:
        if s < cursor:
            continue
        out.append(pcb_text[cursor:s])
        cursor = e
    out.append(pcb_text[cursor:])
    return "".join(out)


def all_footprint_refs(pcb_text: str) -> list[str]:
    refs = []
    for fp_s, fp_e in _toplevel_block_spans(pcb_text, "footprint"):
        block = pcb_text[fp_s:fp_e]
        m = re.search(r'\(property "Reference" "([^"]*)"', block)
        if m:
            refs.append(m.group(1))
    return sorted(set(refs))


# ---------------------------------------------------------------------------
# Item-level bisection WITHIN a single footprint pair, for when even
# footprint-reference granularity (board_text_filtered_by_refs) is not fine
# enough: two footprints alone can already saturate kicad-cli's cap (see
# docs/evidence/2026-08-13-track-width-silk-overlap-uncapped-measurement.md
# -- C2xC3 and C5xC7 on this board, both instances of the CP_Radial_D35.0mm
# library footprint whose silkscreen is drawn as 556 individual `fp_line` +
# 3 `fp_circle` primitives instead of a circle). A footprint reference is
# already the finest unit board_text_filtered_by_refs can delete; this
# section goes one level finer, bisecting ONE footprint's own graphic-item
# list the same way _measure_pool bisects a DRU band's real net names --
# same principle (partition a population that is still too coarse), applied
# one layer deeper.
# ---------------------------------------------------------------------------


def _footprint_span(pcb_text: str, ref: str) -> tuple[int, int]:
    """The (start, end) span of the footprint block whose Reference property
    equals `ref`. Raises if not found or not unique."""
    matches = []
    for fp_s, fp_e in _toplevel_block_spans(pcb_text, "footprint"):
        block = pcb_text[fp_s:fp_e]
        m = re.search(r'\(property "Reference" "([^"]*)"', block)
        if m and m.group(1) == ref:
            matches.append((fp_s, fp_e))
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one footprint with Reference {ref!r}, found {len(matches)}"
        )
    return matches[0]


def _silk_item_spans_in(pcb_text: str, fp_start: int, fp_end: int) -> list[tuple[int, int]]:
    """Spans of every direct-child (fp_line|fp_circle|fp_arc|fp_poly) graphic
    item within one footprint block, in document order -- the rendered primitives
    kicad-cli's silk_overlap check treats as individual items (verified:
    deleting a subset of them via this same span-and-delete mechanism
    board_text_filtered_by_refs already uses for whole footprints changes
    the reported count by exactly the deleted items' own contribution, never
    more or less -- see the exhaustiveness argument in
    measure_saturating_footprint_pair's docstring). Not layer-filtered: a
    bucket may contain non-silkscreen items (e.g. F.Fab courtyard lines) --
    harmless, since those never contribute to silk_overlap either way and
    the partition only needs to be exhaustive+disjoint over the FULL item
    list, not silk-only, for the sum to be correct."""
    spans = []
    for kind in (
        "fp_text",
        "fp_text_box",
        "fp_line",
        "fp_rect",
        "fp_circle",
        "fp_arc",
        "fp_poly",
    ):
        for m in re.finditer(rf"(?m)^    \({kind} ", pcb_text[fp_start:fp_end]):
            s = fp_start + m.start() + 4
            e = _find_balanced(pcb_text, s)
            spans.append((s, e))
    spans.sort()
    return spans


def board_text_filtered_by_refs_and_items(
    pcb_text: str,
    keep_refs: set[str],
    item_subset: dict[str, set[int]] | None = None,
) -> str:
    """Like board_text_filtered_by_refs (every footprint not in `keep_refs`
    deleted entirely, every track/via/zone dropped), but for any ref that is
        also a key in `item_subset`: additionally deletes every rendered direct-child
    graphic item (fp_line/fp_circle/fp_arc/fp_poly, 0-based document order
    per _silk_item_spans_in) whose index is not in that ref's kept set.
    Every other part of a bisected footprint (pads, properties, non-graphic
    children) is left untouched -- only used to shrink an oversized
    hatch-pattern silkscreen body, never to touch anything electrical."""
    item_subset = item_subset or {}
    deletions: list[tuple[int, int]] = []
    for kind in ("segment", "arc", "via", "zone"):
        deletions.extend(_toplevel_block_spans(pcb_text, kind))

    for fp_s, fp_e in _toplevel_block_spans(pcb_text, "footprint"):
        block = pcb_text[fp_s:fp_e]
        m = re.search(r'\(property "Reference" "([^"]*)"', block)
        ref = m.group(1) if m else None
        if ref not in keep_refs:
            deletions.append((fp_s, fp_e))
            continue
        if ref in item_subset:
            keep_idx = item_subset[ref]
            for idx, (s, e) in enumerate(_silk_item_spans_in(pcb_text, fp_s, fp_e)):
                if idx not in keep_idx:
                    deletions.append((s, e))

    deletions.sort()
    out = []
    cursor = 0
    for s, e in deletions:
        if s < cursor:
            continue  # overlapping/nested, skip (shouldn't happen by construction)
        out.append(pcb_text[cursor:s])
        cursor = e
    out.append(pcb_text[cursor:])
    return "".join(out)


@dataclass
class PairCellResult:
    a_items: int
    b_items: int
    count: int
    leaves: list = field(default_factory=list)
    note: str = ""


def _measure_pair_cell(
    board_dir: Path,
    pcb_text: str,
    ref_a: str,
    ref_b: str,
    a_group: list[int],
    b_group: list[int],
    safe_ceiling: int,
    _depth: int = 0,
) -> PairCellResult:
    """One (a_group x b_group) cross-product cell, auto-recursing exactly
    like _measure_pool does for a DRU band's real net names: if the cell
    saturates (or is non-deterministic) and at least one side still has
    more than one item, bisect the LARGER side in half and recurse on the
    two resulting cells -- still exhaustive+non-overlapping, because the
    bisected side's two halves partition it exactly. Stops and reports a
    LOWER BOUND only when both sides are already down to a single item
    each and it is still saturated (the true floor of this partition
    family, matching measure_rule_band's / _measure_pool's own stopping
    condition for DRU bands)."""
    filtered = board_text_filtered_by_refs_and_items(
        pcb_text, {ref_a, ref_b}, {ref_a: set(a_group), ref_b: set(b_group)}
    )
    make_scratch_board(board_dir, pcb_text=filtered)
    n, nondet = _verified_count(board_dir, None, "silk_overlap", safe_ceiling)
    saturated = n >= safe_ceiling or nondet

    if not saturated or (len(a_group) <= 1 and len(b_group) <= 1):
        note = ""
        if saturated:
            det = (
                "non-deterministic across reruns"
                if nondet
                else f"n={n} >= safe ceiling {safe_ceiling}"
            )
            note = (
                f"SATURATION SUSPECTED ({det}) but both sides are down to a single "
                "item each -- cannot split further. Reporting as a LOWER BOUND, "
                "not a true count."
            )
        return PairCellResult(a_items=len(a_group), b_items=len(b_group), count=n, note=note)

    if len(a_group) >= len(b_group) and len(a_group) > 1:
        mid = len(a_group) // 2
        halves = [(a_group[:mid], b_group), (a_group[mid:], b_group)]
    else:
        mid = len(b_group) // 2
        halves = [(a_group, b_group[:mid]), (a_group, b_group[mid:])]

    leaves = []
    total = 0
    for ag, bg in halves:
        leaf = _measure_pair_cell(
            board_dir, pcb_text, ref_a, ref_b, ag, bg, safe_ceiling, _depth + 1
        )
        leaves.append(leaf)
        total += leaf.count
    return PairCellResult(
        a_items=len(a_group),
        b_items=len(b_group),
        count=total,
        leaves=leaves,
        note=f"split ({len(a_group)}x{len(b_group)} items, n_before_split={n})",
    )


def pair_cell_to_dict(c: PairCellResult) -> dict:
    return {
        "a_items": c.a_items,
        "b_items": c.b_items,
        "count": c.count,
        "note": c.note,
        "leaves": [pair_cell_to_dict(leaf) for leaf in c.leaves],
    }


def measure_saturating_footprint_pair(
    board_dir: Path,
    pcb_text: str,
    ref_a: str,
    ref_b: str,
    safe_ceiling: int | None = None,
    a_group: list[int] | None = None,
    b_group: list[int] | None = None,
) -> dict:
    """Exact, provably exhaustive/non-overlapping silk_overlap count between
    two SPECIFIC footprints whose combined reading saturates kicad-cli's cap
    even with every other footprint deleted -- the finest granularity
    board_text_filtered_by_refs can reach. Recursively bisects ref_a's
    and/or ref_b's own graphic-item list (via _measure_pair_cell) whenever a
    cell saturates, the same auto-refining strategy _measure_pool already
    uses for a DRU band's real net names, applied one layer deeper (within
    a single footprint pair instead of across net names).

    Exhaustive and non-overlapping by construction: every one of ref_a's
    items is in exactly one leaf of the a-side bisection at any point in
    the recursion, likewise ref_b, so every unordered (item_from_a,
    item_from_b) pair is covered by exactly one leaf cell -- a cross grid,
    NOT the triangular self-pair sweep measure_by_bucket_pairs uses for a
    single population, because ref_a's and ref_b's item lists are two
    disjoint populations to begin with (no same-footprint pair can appear
    here, matching kicad-cli's own observed behaviour that same-footprint
    silk_overlap pairs are never reported). Every other footprint is
    deleted for every run.

    `a_group`/`b_group` let a caller resume/refine a specific sub-region
    (e.g. the handful of cells a coarser prior sweep found still saturated)
    instead of re-measuring an entire board's worth of already-resolved
    cells from scratch -- pass the exact item-index lists for the region to
    refine; omit both to measure the two footprints' full item sets.
    """
    if safe_ceiling is None:
        safe_ceiling = default_safe_ceiling("silk_overlap")
    if a_group is None or b_group is None:
        a_s, a_e = _footprint_span(pcb_text, ref_a)
        b_s, b_e = _footprint_span(pcb_text, ref_b)
        a_group = list(range(len(_silk_item_spans_in(pcb_text, a_s, a_e))))
        b_group = list(range(len(_silk_item_spans_in(pcb_text, b_s, b_e))))
    root = _measure_pair_cell(board_dir, pcb_text, ref_a, ref_b, a_group, b_group, safe_ceiling)
    return {
        "ref_a": ref_a,
        "ref_b": ref_b,
        "total": root.count,
        "tree": pair_cell_to_dict(root),
    }


# ---------------------------------------------------------------------------
# Net-41 admission instrument: exact mutation-cone silk evidence.
# ---------------------------------------------------------------------------


def _rust_silk_scope_receipt(payload: dict) -> dict:
    """Thin transport shim to the Rust-owned mutation census and pair ledger."""
    import temper_drc_rs  # type: ignore[import-untyped]

    return json.loads(
        temper_drc_rs.drc_silk_scope_receipt_json(json.dumps(payload, separators=(",", ":")))
    )


def _rust_silk_cell_check(*, pairs: list[list[str]], safe_ceiling: int, cell: dict) -> dict:
    """Ask Rust whether three raw cell samples are semantically repeatable."""
    import temper_drc_rs  # type: ignore[import-untyped]

    return json.loads(
        temper_drc_rs.drc_silk_cell_check_json(
            json.dumps(
                {"pairs": pairs, "safe_ceiling": safe_ceiling, "cell": cell},
                separators=(",", ":"),
            )
        )
    )


def _sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_tree(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(child.relative_to(path).as_posix().encode())
        digest.update(b"\0")
        digest.update(child.read_bytes())
        digest.update(b"\xff")
    return digest.hexdigest()


def silk_instrument_context(board: Path) -> dict:
    """Content identity for the exact strict KiCad instrument around *board*."""
    from temper_placer.validation._drc_api import get_kicad_cli_version

    version = get_kicad_cli_version()
    if not version:
        raise RuntimeError("kicad-cli version is unavailable")
    project = board.with_suffix(".kicad_pro")
    dru = board.with_suffix(".kicad_dru")
    table = board.parent / "fp-lib-table"
    libraries = board.parent / "libs"
    return {
        "schema": "temper.kicad-drc-instrument/v1",
        "kicad_cli_version": version,
        "runner": "temper_placer.validation._drc_api.run_drc_measurement/v1",
        "runner_flags": ["drc", "--format", "json", "--all-track-errors", "single-thread"],
        "project_sha256": _sha256_file(project),
        "dru_sha256": _sha256_file(dru),
        "fp_lib_table_sha256": _sha256_file(table),
        "libraries_sha256": _sha256_tree(libraries),
    }


def _stage_strict_project(source_board: Path, destination: Path, pcb_text: str) -> Path:
    """Stage one complete project around a byte-filtered scratch subject."""
    destination.mkdir(parents=True, exist_ok=True)
    board = destination / source_board.name
    board.write_text(pcb_text, encoding="utf-8")
    for suffix in (".kicad_pro", ".kicad_dru"):
        shutil.copy(source_board.with_suffix(suffix), board.with_suffix(suffix))
    shutil.copy(source_board.parent / "fp-lib-table", destination / "fp-lib-table")
    shutil.copytree(source_board.parent / "libs", destination / "libs", dirs_exist_ok=True)
    return board


def _silk_findings(raw_report: dict | list[dict]) -> list[dict]:
    findings = raw_report if isinstance(raw_report, list) else _all_violations(raw_report)
    return [
        finding for finding in findings if finding.get("type") == "silk_overlap"
    ]


def _seeded_pair_groups(*, bootstrap: dict, partition_seed: dict | None) -> list[list[list[str]]]:
    """Return a prior receipt's exhaustive pair partition, or no seed."""
    if not partition_seed or not partition_seed.get("complete"):
        return []
    binding_keys = (
        "schema",
        "source_sha256",
        "declared_refs",
        "measurement_scope_refs",
        "instrument_context_sha256",
    )
    if any(partition_seed.get(key) != bootstrap.get(key) for key in binding_keys):
        return []
    groups = [leaf.get("pairs", []) for leaf in partition_seed.get("leaves", [])]
    covered = [tuple(pair) for group in groups for pair in group]
    all_refs = sorted(set(bootstrap["measurement_scope_refs"]))
    # Rust remains the final ledger authority; this check only avoids seeding
    # from an obviously empty or duplicated transport shape.
    if not groups or len(covered) != len(set(covered)) or not all_refs:
        return []
    return groups


def measure_silk_mutation_cone(
    *,
    source_board: Path,
    subject_board: Path,
    declared_refs: list[str],
    scratch_dir: Path,
    use_declared_scope: bool = False,
    partition_seed: dict | None = None,
    instrument_context: dict | None = None,
    measurement_fn=None,
) -> dict:
    """Measure every candidate-changeable ``silk_overlap`` pair exactly once.

    Each root cell keeps one affected footprint plus a deterministic peer
    bucket. A saturated or disagreeing cell bisects only its peer axis, so
    its assigned unordered pairs remain exhaustive and disjoint. The raw
    cell count — including irrelevant peer-to-peer findings — decides whether
    the report is safely below KiCad's cap; only findings whose Rust-parsed
    pair belongs to the cell are retained as candidate evidence.
    """
    from temper_placer.validation._drc_api import run_drc_measurement

    source_board = Path(source_board)
    subject_board = Path(subject_board)
    source_text = source_board.read_text(encoding="utf-8")
    subject_text = subject_board.read_text(encoding="utf-8")
    context = instrument_context or silk_instrument_context(source_board)
    bootstrap_payload = {
        "source_board": source_text,
        "subject_board": subject_text,
        "declared_refs": list(declared_refs),
        "use_declared_scope": use_declared_scope,
        "raw_global_capped": True,
        "instrument_context": context,
        "leaves": [],
    }
    bootstrap = _rust_silk_scope_receipt(bootstrap_payload)
    cache_path = scratch_dir / "completed-receipt.json"
    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cached = {}
        binding_keys = (
            "schema",
            "source_sha256",
            "silk_projection_sha256",
            "instrument_context_sha256",
            "declared_refs",
            "actual_mutated_refs",
            "rigid_only_mutated_refs",
            "measurement_scope_refs",
        )
        if cached.get("complete") and all(
            cached.get(key) == bootstrap.get(key) for key in binding_keys
        ):
            rebound_payload = dict(bootstrap_payload)
            rebound_payload["leaves"] = [
                {
                    "pairs": leaf["pairs"],
                    "cells": leaf["cells"],
                }
                for leaf in cached["leaves"]
            ]
            rebound_payload["execution"] = {
                "kicad_invocation_count": 0,
                "reused_projection_receipt_sha256": sha256_text(
                    json.dumps(cached, sort_keys=True, separators=(",", ":"))
                ),
            }
            rebound = _rust_silk_scope_receipt(rebound_payload)
            if rebound["complete"]:
                return rebound
    scope = list(bootstrap["measurement_scope_refs"])
    all_refs = all_footprint_refs(subject_text)
    static_refs = sorted(set(all_refs) - set(scope))
    safe_ceiling = int(bootstrap["safe_ceiling"])
    measure = measurement_fn or (lambda board: run_drc_measurement(board, strict=True).raw_findings)
    measurement_board = _stage_strict_project(
        subject_board,
        scratch_dir / "measurement-project",
        subject_text,
    )
    leaves: list[dict] = []
    cell_counter = 0
    used_partition_seed = False

    def measure_cell(
        pairs: list[list[str]],
        keep_refs: set[str],
        *,
        item_region: dict | None = None,
        first_indices: list[int] | None = None,
        second_indices: list[int] | None = None,
    ) -> tuple[dict, str]:
        nonlocal cell_counter
        cell_counter += 1
        if item_region is None:
            filtered = board_text_filtered_by_refs(subject_text, keep_refs)
        else:
            pair = item_region["pair"]
            filtered = board_text_filtered_by_refs_and_items(
                subject_text,
                set(pair),
                {pair[0]: set(first_indices or []), pair[1]: set(second_indices or [])},
            )
        measurement_board.write_text(filtered, encoding="utf-8")
        reports = [measure(measurement_board) for _ in range(3)]
        samples = [_silk_findings(report) for report in reports]
        cell = {
            "sample_counts": [len(sample) for sample in samples],
            "sample_findings": samples,
            "item_region": item_region,
        }
        return cell, filtered

    def cell_resolved(pairs: list[list[str]], cell: dict) -> bool:
        return bool(
            _rust_silk_cell_check(pairs=pairs, safe_ceiling=safe_ceiling, cell=cell)["resolved"]
        )

    def item_cells(
        pair: list[str],
        first_indices: list[int],
        second_indices: list[int],
        first_count: int,
        second_count: int,
        prior_cell: dict | None = None,
    ) -> list[dict]:
        region = {
            "pair": pair,
            "first_item_count": first_count,
            "second_item_count": second_count,
            "first_indices": first_indices,
            "second_indices": second_indices,
        }
        cell, _filtered = (
            (dict(prior_cell, item_region=region), "")
            if prior_cell is not None
            else measure_cell(
                [pair],
                set(pair),
                item_region=region,
                first_indices=first_indices,
                second_indices=second_indices,
            )
        )
        if cell_resolved([pair], cell):
            return [cell]
        if len(first_indices) <= 1 and len(second_indices) <= 1:
            return [cell]
        if len(first_indices) >= len(second_indices) and len(first_indices) > 1:
            midpoint = len(first_indices) // 2
            halves = [
                (first_indices[:midpoint], second_indices),
                (first_indices[midpoint:], second_indices),
            ]
        else:
            midpoint = len(second_indices) // 2
            halves = [
                (first_indices, second_indices[:midpoint]),
                (first_indices, second_indices[midpoint:]),
            ]
        return [
            child
            for first_half, second_half in halves
            for child in item_cells(
                pair,
                first_half,
                second_half,
                first_count,
                second_count,
            )
        ]

    def record_leaf(pairs: list[list[str]], cells: list[dict], filtered: str) -> None:
        leaves.append(
            {
                "pairs": pairs,
                "cells": cells,
                "resolved": all(cell_resolved(pairs, child) for child in cells),
                "scratch_subject_sha256": sha256_text(filtered),
            }
        )

    def run_pair_group(pairs: list[list[str]]) -> None:
        keep_refs = {reference for pair in pairs for reference in pair}
        cell, filtered = measure_cell(pairs, keep_refs)
        resolved = cell_resolved(pairs, cell)
        if not resolved and len(pairs) > 1:
            midpoint = len(pairs) // 2
            run_pair_group(pairs[:midpoint])
            run_pair_group(pairs[midpoint:])
            return
        cells = [cell]
        if not resolved:
            pair = pairs[0]
            first_span = _footprint_span(subject_text, pair[0])
            second_span = _footprint_span(subject_text, pair[1])
            first_count = len(_silk_item_spans_in(subject_text, *first_span))
            second_count = len(_silk_item_spans_in(subject_text, *second_span))
            cells = item_cells(
                pair,
                list(range(first_count)),
                list(range(second_count)),
                first_count,
                second_count,
                prior_cell=cell,
            )
        record_leaf(pairs, cells, filtered)

    def run_cross_product(anchors: list[str], peers: list[str]) -> None:
        pairs = [sorted((anchor, peer)) for anchor in anchors for peer in peers]
        cell, filtered = measure_cell(pairs, set(anchors) | set(peers))
        if cell_resolved(pairs, cell):
            record_leaf(pairs, [cell], filtered)
            return
        if len(anchors) > 1 or len(peers) > 1:
            if len(peers) >= len(anchors) and len(peers) > 1:
                midpoint = len(peers) // 2
                run_cross_product(anchors, peers[:midpoint])
                run_cross_product(anchors, peers[midpoint:])
            else:
                midpoint = len(anchors) // 2
                run_cross_product(anchors[:midpoint], peers)
                run_cross_product(anchors[midpoint:], peers)
            return
        run_pair_group(pairs)

    seeded_groups = _seeded_pair_groups(bootstrap=bootstrap, partition_seed=partition_seed)
    if seeded_groups:
        used_partition_seed = True
        for pairs in seeded_groups:
            run_pair_group(pairs)
    else:
        ordered_scope = sorted(scope)
        if static_refs:
            run_cross_product(ordered_scope, static_refs)
        affected_pairs = [
            [anchor, peer]
            for index, anchor in enumerate(ordered_scope)
            for peer in ordered_scope[index + 1 :]
        ]
        if affected_pairs:
            run_pair_group(affected_pairs)

    final_payload = dict(bootstrap_payload)
    final_payload["leaves"] = [
        {
            "pairs": leaf["pairs"],
            "cells": leaf["cells"],
        }
        for leaf in leaves
    ]
    final_payload["execution"] = {"kicad_invocation_count": cell_counter * 3}
    if used_partition_seed and partition_seed is not None:
        final_payload["execution"]["partition_seed_receipt_sha256"] = sha256_text(
            json.dumps(partition_seed, sort_keys=True, separators=(",", ":"))
        )
    receipt = _rust_silk_scope_receipt(final_payload)
    if receipt["complete"]:
        scratch_dir.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(cache_path)
    return receipt


def sha256_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def bucket(items: list, k: int) -> list[list]:
    """Split `items` into k contiguous buckets, as evenly as possible."""
    n = len(items)
    base, extra = divmod(n, k)
    buckets = []
    i = 0
    for j in range(k):
        size = base + (1 if j < extra else 0)
        buckets.append(items[i : i + size])
        i += size
    return [b for b in buckets if b]


def measure_by_bucket_pairs(
    board_dir: Path,
    ctype: str,
    pcb_text: str,
    buckets: list[list[str]],
    filter_fn,
    safe_ceiling: int | None = None,
) -> dict:
    """Sum `ctype` over every unordered bucket pair (i, j), i<=j, of a
    physical board partition. Exhaustive because every relevant item
    belongs to exactly one bucket (by construction of `buckets`);
    non-overlapping because each unordered item-pair is tested under
    exactly one (i, j) run. Any single (i, j) run landing at/near the cap
    is reported as a bucketing-granularity failure (told to the caller,
    not silently summed) rather than refined automatically -- refining a
    2-D bucket grid safely needs a finer regrid of BOTH axes at once,
    which is worth a human decision, not an unattended retry loop.
    """
    if safe_ceiling is None:
        safe_ceiling = default_safe_ceiling(ctype)
    results = []
    total = 0
    any_saturated = False
    for i in range(len(buckets)):
        for j in range(i, len(buckets)):
            keep = set(buckets[i]) | set(buckets[j])
            filtered = filter_fn(pcb_text, keep)
            make_scratch_board(board_dir, pcb_text=filtered)
            n, nondet = _verified_count(board_dir, None, ctype, safe_ceiling)
            saturated = n >= safe_ceiling or nondet
            any_saturated = any_saturated or saturated
            results.append(
                {"i": i, "j": j, "count": n, "saturated": saturated, "nondeterministic": nondet}
            )
            total += n
    return {
        "ctype": ctype,
        "n_buckets": len(buckets),
        "total": total,
        "any_saturated": any_saturated,
        "pairs": results,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_band_tree(b: BandResult, indent: int = 0) -> None:
    print(" " * indent + f"{b.label} = {b.count}" + (f"  [{b.note}]" if b.note else ""))
    for leaf in b.leaves:
        _print_band_tree(leaf, indent + 2)


def _cli_dru_category(args) -> None:
    if args.dru_generator:
        import importlib.util

        spec = importlib.util.spec_from_file_location("_dru_gen", args.dru_generator)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        dru_text = mod.generate_dru()
    else:
        dru_text = Path(args.dru_file).read_text()

    board_dir = Path(args.scratch_dir)
    make_scratch_board(board_dir)
    netmap = net_class_map()
    result = measure_category_exhaustive(board_dir, dru_text, args.category, netmap)
    print(f"TRUE {args.category}: {result['total']}")
    for b in result["bands"]:
        _print_band_tree(b)
    if args.json:
        json.dump(
            {
                "category": args.category,
                "total": result["total"],
                "bands": [band_tree_to_dict(b) for b in result["bands"]],
            },
            Path(args.json).open("w"),
            indent=2,
        )


def _cli_physical_category(args) -> None:
    pcb_text = (PCB_DIR / "temper.kicad_pcb").read_text()
    board_dir = Path(args.scratch_dir)
    if args.category == "shorting_items":
        items = real_net_names()
        filter_fn = board_text_filtered_by_nets
    elif args.category == "silk_overlap":
        items = all_footprint_refs(pcb_text)
        filter_fn = board_text_filtered_by_refs
    else:
        raise SystemExit(f"no physical partition strategy for {args.category!r}")
    buckets = bucket(items, args.buckets)
    result = measure_by_bucket_pairs(board_dir, args.category, pcb_text, buckets, filter_fn)
    print(
        f"raw bucket-pair sum {args.category}: {result['total']} (any_saturated={result['any_saturated']})"
    )
    print(
        "NOTE: this raw sum double-counts intra-bucket pairs across every "
        "bucket-pair run that includes that bucket. Apply inclusion-exclusion "
        "yourself before trusting a total -- see docs/evidence/"
        "2026-08-12-uncapped-drc-measurement.md sec on shorting_items for why "
        "this matters and why this session did not ship a validated total."
    )
    if args.json:
        json.dump(result, Path(args.json).open("w"), indent=2)


def _cli_saturating_pair(args) -> None:
    pcb_text = (PCB_DIR / "temper.kicad_pcb").read_text()
    board_dir = Path(args.scratch_dir)
    result = measure_saturating_footprint_pair(board_dir, pcb_text, args.ref_a, args.ref_b)
    print(f"TRUE silk_overlap {args.ref_a}x{args.ref_b}: {result['total']}")
    if args.json:
        json.dump(result, Path(args.json).open("w"), indent=2)


def _cli_silk_mutation_cone(args) -> None:
    declared_refs = list(args.declared_ref)
    if not declared_refs:
        import temper_quality_oracle  # type: ignore[import-untyped]

        declared_refs = json.loads(temper_quality_oracle.corridor_footprint_scope_json_py())[
            "affected_refs"
        ]
    result = measure_silk_mutation_cone(
        source_board=Path(args.source_board),
        subject_board=Path(args.subject_board),
        declared_refs=declared_refs,
        use_declared_scope=args.use_declared_scope,
        scratch_dir=Path(args.scratch_dir),
    )
    print(
        f"silk mutation cone: {result['category_state']}; "
        f"pairs={result['covered_pair_count']}/{result['expected_pair_count']}; "
        f"invocations={result['execution']['kicad_invocation_count']}"
    )
    if args.json:
        Path(args.json).write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("dru-category", help="exhaustive count for clearance/creepage/track_width")
    p1.add_argument(
        "category",
        choices=["clearance", "creepage", "track_width", "hole_clearance", "hole_to_hole"],
    )
    p1.add_argument("--dru-file", help="path to a pre-generated .kicad_dru")
    p1.add_argument(
        "--dru-generator", help="path to a generate_kicad_dru.py exposing generate_dru()"
    )
    p1.add_argument("--scratch-dir", required=True)
    p1.add_argument("--json", help="write full band tree to this path")
    p1.set_defaults(func=_cli_dru_category)

    p2 = sub.add_parser("physical-category", help="bucket-pair sum for shorting_items/silk_overlap")
    p2.add_argument("category", choices=["shorting_items", "silk_overlap"])
    p2.add_argument("--buckets", type=int, default=8)
    p2.add_argument("--scratch-dir", required=True)
    p2.add_argument("--json", help="write full pair table to this path")
    p2.set_defaults(func=_cli_physical_category)

    p3 = sub.add_parser(
        "saturating-pair",
        help="exact silk_overlap count for two specific footprints whose combined "
        "reading alone saturates the cap (item-level bisection within the pair)",
    )
    p3.add_argument("ref_a")
    p3.add_argument("ref_b")
    p3.add_argument("--scratch-dir", required=True)
    p3.add_argument("--json", help="write full recursive cell tree to this path")
    p3.set_defaults(func=_cli_saturating_pair)

    p4 = sub.add_parser(
        "silk-mutation-cone",
        help="exact, repeated silk evidence for every pair incident to a mutation scope",
    )
    p4.add_argument("--source-board", default=str(PCB_DIR / "temper.kicad_pcb"))
    p4.add_argument("--subject-board", default=str(PCB_DIR / "temper.kicad_pcb"))
    p4.add_argument("--declared-ref", action="append", default=[])
    p4.add_argument("--use-declared-scope", action="store_true")
    p4.add_argument("--scratch-dir", required=True)
    p4.add_argument("--json", help="write the content-bound completed receipt")
    p4.set_defaults(func=_cli_silk_mutation_cone)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
