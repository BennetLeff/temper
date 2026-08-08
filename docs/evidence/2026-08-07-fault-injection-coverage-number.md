# Provenance: measured against the commit below; the tracked tree carried
# this investigation's own edits (this document's own change set) at
# measurement time.
provenance: commit=ea0379ba83cc1f41f3a5cc173b69784ebe2cdec2 dirty=true

<!-- provenance: commit=ea0379ba83cc1f41f3a5cc173b69784ebe2cdec2 dirty=true -->

# The fault-injection coverage number (STRATEGY.md build order steps 4-5)

**Date:** 2026-08-07
**Scope:** `pcb/temper.kicad_pcb`, `power_pcb_dataset/drc_ceiling.json`, and `elec/` are
read-only throughout this entire body of work. Every mutation runs against a run-time copy or a
synthetic, committed fixture; nothing in this document's scripts writes to any of those three
paths.

## What this closes

`docs/STRATEGY.md`'s build order:

- **Step 4**: fault-injection harness, ~10 defect classes, with injector self-verification.
- **Step 5**: corpus specificity run -- false-positive oracle.

The target-pipeline diagram names a **validator pipeline** producing "the coverage number that
replaces 'DRC = 0'" -- per-family sensitivity, specificity, and an honest accounting of what is
NOT yet covered. This document is that number, as of this commit.

## The eleven classes, three constraint families

| Family | Owning gate | Classes injected | Caught | False-positive rate |
|---|---|---|---|---|
| PCB geometry | `kicad-drc` (`clearance`/`courtyards_overlap`/`hole_to_hole`/`shorting_items`/`missing_courtyard`) + `check_board_containment.py` | 7 | **6** | 0% confirmed on the corpus's own clean board (N=120, zero variance -- `docs/evidence/2026-08-07-clearance-courtyard-corpus-coverage.md`); cross-board specificity run below is inconclusive on 4/5 boards, not a clean 0% |
| Component value/MPN | `mpn_fabrication_gate.py` | 2 | **2** | 0% (clean fixture: 0/2 violations) |
| Process/provenance | `DrcRatchet.find_ceiling_raises`/`validate_raise_evidence` | 2 | **2** | 0% (2/2 dedicated controls -- `no-op-control`, `fully-evidenced-raise-control` -- report zero problems) |
| **Total** | | **11** | **10 (90.9%)** | see per-family notes above |

**One class, `missing-courtyard`, is a deliberate, reported gap, not a silent drop.** Its injector
is independently self-verified (re-parsed directly, decoupled from the DRC gate: 1 courtyard item
on the clean board, 0 on the mutated board), but no owning gate fires, for two separately
diagnosed, independently verified reasons -- see
`docs/evidence/2026-08-07-missing-courtyard-and-hole-to-hole-classes.md` Sec. 3. Per
METHODOLOGY.md Sec. 5 ("if a gate turns out not to catch its own defect class, that is a finding
-- report it, do not weaken the class"), it stays in the manifest and the corpus's own exit code
is honestly non-zero as a result.

### Per-class detail

| Class | Family | Real incident it is drawn from | Result |
|---|---|---|---|
| off-board | PCB geometry | R38 corpus, tank-cap-off-outline defect | PASS |
| pad-short | PCB geometry | R38 corpus, C1 pad2<->R7 pad2 short | PASS |
| creepage | PCB geometry | R38 corpus, DC_BUS<->LV_CONTROL creepage crossings | PASS |
| clearance | PCB geometry | R9/R10 vacuity closure, 2026-08-07 | PASS |
| courtyard | PCB geometry | R9/R10 vacuity closure, 2026-08-07 (replaces the 2026-08-04 dropped `courtyards_overlap` off-board proxy) | PASS |
| hole-to-hole | PCB geometry | `generate_kicad_dru.py`'s own manufacturing rule set, previously uncovered | PASS (found and fixed a real `DrcWarning`-bucket blind spot along the way -- see below) |
| missing-courtyard | PCB geometry | STRATEGY.md's "DRC -- committed board" table (`missing_courtyard` category) | **UNCOVERED, reported** (Sec. above) |
| fabricated-mpn | Component value | `r_low_top` / `ERA-3AEB6132V`, 2026-07-27 audit | PASS |
| mpn-value-mismatch | Component value | UVL-02's `r_div_bot` / `RC0603FR-0710KL` 10x mismatch, 2026-07-27 | PASS |
| no-march-entry | Process/provenance | AGENTS.md's R27 "an unattributed rise is a hard stop" | PASS |
| dangling-commit | Process/provenance | AGENTS.md's `measured_at_commit` orphaned-by-squash incident, 2026-08-07 | PASS (via a different check than the one the incident's name suggests -- see finding below) |

## Findings surfaced along the way (the point of this exercise)

1. **`hole_to_hole` was silently discarded by the corpus's own measurement wrapper before this
   pass.** `_drc_api.py`'s `_parse_drc_json` buckets every violation by its own reported severity
   into `DrcResult.errors` (non-warning) and `DrcResult.warnings` (warning); `hole_to_hole`'s
   severity is `"warning"` under kicad-cli's own compiled-in default (verified: present in raw
   JSON with that label even with zero project file), and `check_board_defect_corpus.py`'s
   `measure_drc()` returned only `.errors`. Fixed locally in that one wrapper function
   (`.errors + .warnings`), not in `_drc_api.run_drc()` itself -- the DRC ceiling ratchet and
   every other consumer of `run_drc()` are untouched. Full diagnosis:
   `docs/evidence/2026-08-07-missing-courtyard-and-hole-to-hole-classes.md` Sec. 2.

2. **`missing_courtyard` cannot be seen by this repo's DRC measurement pipeline at all, for two
   independent reasons, verified separately.** kicad-cli's compiled-in default severity for that
   rule is `ignore` without an accompanying `.kicad_pro` (which no mutated-board workdir ever has);
   AND `run_drc()` never passes `--severity-warning`/`--severity-all`, so even with a project file
   present the rule's output is still dropped. Neither was fixed here -- `run_drc()` is the
   canonical path for `drc_ceiling.json`'s own ratchet, and changing its severity flags would
   surface many new categories across the whole DRC-ceiling contract, a real, separate,
   much-larger re-baselining task outside this task's scope (and `drc_ceiling.json` is explicitly
   not to be touched by this work). Full diagnosis: same evidence doc, Sec. 3.

3. **`DrcRatchet.validate_raise_evidence` does not itself verify commit resolvability** -- a
   dangling `measured_at_commit` (well-formed 40-hex, but absent from the git object store, the
   exact 2026-08-07 incident AGENTS.md documents) is only caught by this method via a SECONDARY
   effect (the input-hash-freshness check), not by checking the commit against `git cat-file`
   directly. That verification lives in a separate gate, `check_measurement_provenance.py`'s
   `verify_commits_exist` -- consistent with AGENTS.md's own account of why that gate had to be
   added on top of the ratchet. Recorded as a finding, not fixed here (out of this corpus's scope
   -- it would mean extending `validate_raise_evidence` itself, a change to shared ratchet logic).

## Step 5: the specificity run

`power_pcb_dataset/corpus/` -- five independently-designed real KiCad boards (`temper`, `minimal`,
the real open-source `rp2040_designguide`, `bitaxe_ultra`, `piantor_right`; manifest at
`power_pcb_dataset/corpus/manifest.yaml`) -- is the "corpus already exists" false-positive oracle
STRATEGY.md's step-5 rationale refers to. None were designed by or for this fault-injection corpus.

`check_board_containment.py` (the `off-board` class's owning gate, and the one gate in this whole
harness that is genuinely board-agnostic -- pure Edge.Cuts-vs-pad-copper geometry, no reference to
any specific footprint ref) was run against all five:

| Board | Result |
|---|---|
| `rp2040_designguide` | **clean** -- 0 findings |
| `temper` (corpus copy) | **UNCHECKED** -- open Edge.Cuts outline, reported as a gate error, not silently folded into "clean" |
| `minimal` | **UNCHECKED** -- same reason |
| `bitaxe_ultra` | **finding** -- one `<no Reference>` pad per board corner (4 total), each ~1-1.2mm^2 of copper outside the outline |
| `piantor_right` | **finding** -- same shape, smaller (5 `copper_edge_clearance` context hits, 1 containment finding) |

**Not resolved to certainty**: the two findings are, by position (all four board corners, `<no
Reference>` -- i.e. a pad-less-or-ref-less footprint the gate checks by origin/pad polygon rather
than by name) and magnitude (~1mm^2, small relative to a mounting-hole pad's own area),
consistent with ordinary corner mounting-hole pads whose copper annular ring slightly overhangs
the panel edge on those two third-party boards -- plausibly a real (if minor) property of those
reference designs, not a demonstrated bug in the gate. This was not chased further to a definitive
answer; reported exactly as measured rather than rounded to a clean "0% false positive" the
evidence does not support. `clearance`/`courtyard`/`hole-to-hole`'s own failure signal is
per-specific-ref identity, which cannot be meaningfully evaluated against a foreign board's
different ref set -- their raw DRC category counts are reported as context only, never asserted;
`mpn_fabrication_gate.py` and `DrcRatchet.validate_raise_evidence` are not applicable to this
corpus at all (no atopile source, no ceiling-raise semantics) -- their specificity is covered by
the dedicated controls inside their own corpus scripts instead (Sec. above).

**An early version of this script had a real anti-vacuity bug, caught before commit**: it treated
`check_board_containment.py`'s `GateError` (the two open-outline boards) as "zero findings" --
exactly the class of silent pass METHODOLOGY.md Sec. 4 warns against. Fixed to report `UNCHECKED`
distinctly from `clean`, and PASS requires zero of both; regression-tested in
`scripts/tests/test_corpus_specificity.py`.

## How to reproduce

```
uv run --no-sync python scripts/check_board_defect_corpus.py         # PCB geometry family (needs kicad-cli, a compiled netlist)
uv run --no-sync python scripts/check_component_defect_corpus.py     # component-value family
uv run --no-sync python scripts/check_ceiling_raise_evidence_corpus.py  # process/provenance family
uv run --no-sync python scripts/check_corpus_specificity.py          # step 5, cross-board specificity
```

`kicad-cli` was not preinstalled in this sandbox; a working 10.0.5 binary (matching CI's pin) was
extracted from the `ppa:kicad/kicad-10.0-releases` `.deb` by a prior session and reused here (no
root available). This does not affect reproducibility elsewhere -- any `kicad-cli` on `PATH`
satisfies these scripts' own `shutil.which` check.
