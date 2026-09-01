<!-- provenance: commit=ed1b18d069531e02572484c24b70ccebf93cd049 dirty=false (clean tree; `git status --porcelain` empty at measurement time). pcb/temper.kicad_pcb sha256=62bff72d04ba3885534aa21df021b61f2a9bb3500c3be885d88ed103a6822777 -- byte-identical to the board named in power_pcb_dataset/drc_ceiling.json's own provenance, so this is a same-board cross-check and not a re-derivation on a moved target. kicad-cli 10.0.5, measured live. Tool: scripts/measure_uncapped_drc.py dru-category {creepage,clearance} --dru-generator scripts/generate_kicad_dru.py, i.e. the COMMITTED generator, which emits PD3 (HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD3_MM). pcb/ was not written; the only pcb/ file touched is the gitignored pcb/temper.kicad_dru, regenerated from the SSOT. -->

# DRC cross-check: two methods, one board, identical totals — and where the remaining violations actually sit

**Date:** 2026-08-24
**Base:** `origin/main` @ `ed1b18d06`
**Board:** `62bff72d…`

## What this is, and what it is not

**It is not a discovery that the recorded counts are stale.** I set out believing
that, because `docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md` records
creepage **377** and clearance **1663**, and I treated those as current. They are
not: `power_pcb_dataset/drc_ceiling.json` was re-measured later and already
records

```
violations_by_type = {"clearance": 185, "creepage": 114,
                      "copper_edge_clearance": 11, "hole_clearance": 33}
```

against this exact board. **I should have read the ceiling file before offering
to measure anything.** That correction is the honest headline and it is recorded
here rather than quietly dropped.

**What it is** is two things the record did not previously have:

1. **An independent cross-method confirmation.** The ceiling was measured via the
   `temper_placer.validation._drc_api.run_drc` protocol (120 samples,
   `--all-track-errors`, single-thread pin). This run used
   `measure_uncapped_drc.py`'s uncapped DRU-band partition — a structurally
   different technique that isolates each rule's own band with a synthetic
   two-rule DRU and sums provably-exhaustive buckets. Same board, **identical
   totals: creepage 114, clearance 185.** Two methods agreeing to the unit is
   stronger evidence than either alone, and the ceiling's provenance block does
   not claim it.
2. **The per-band breakdown**, which the ceiling does not record and which is
   where the decision value is.

## 1. Creepage — 114, concentrated in two buckets

```
TRUE creepage: 114
  HV to LV                            50
  HighVoltageSignal to LV             36
  HighVoltageIsolated to LV           16
  HighVoltageTank to LV                6
  AC Mains to LV                       3
  HighVoltageTank functional creepage  3
```

**`HV to LV` (50) + `HighVoltageSignal to LV` (36) = 86 of 114, i.e. 75 %.** Any
burn-down starts there. `AC Mains to LV` — the bucket nearest the mains inlet —
is down to 3.

## 2. Clearance — 185, and 91 % of it is not safety-critical

```
TRUE clearance: 185
  netclass-implicit fallback (no explicit DRU rule matches)  120
  Default routing                                             48
  GateDriveHV to ACMains                                       8
  HighVoltageIsolated same side                                5
  HV to LV                                                     2
  GateDriveHV to HighVoltageIsolated                           2
  AC Mains to LV                     0    AC Mains to HV                  0
  HighVoltageIsolated to LV          0    HV internal same footprint      0
  HighVoltageTank to LV              0    HighVoltageSignal to LV         0
  GateDriveHV near HV                0    GateDriveSELV near HV           0
  Power internal same footprint      0    Ground clearance                0
  Same footprint pads                0    Fine pitch IC pads              0
  USB differential                   0
```

**This is the finding worth having.** 168 of 185 (91 %) are
`netclass-implicit fallback` + `Default routing` — generic routing tightness with
no domain-crossing meaning. Every cross-domain HV clearance bucket that names
mains, tank, or signal against LV reads **zero**. Only 17 violations sit in
HV-specific bands, and 8 of those are one pair-class (`GateDriveHV to ACMains`).

So on **clearance**, the isolation barriers are effectively clean and what
remains is routing. The safety gap is a **creepage** gap, and §1 says where.

Both totals sum exactly over their bands — that is the partition's
exhaustiveness property, and it is what makes these TRUE counts rather than
`kicad-cli` reports capped at its 199/499 GUI list-widget limits.

## 3. A stale note inside the ceiling file

`drc_ceiling.json`'s `saturation_hazard.clearance` records
`"true_count": 179` with a note naming board `26981fea` and the #1333/#1334
re-route. The sibling `violations_by_type.clearance` records **185** against
board `62bff72d`.

Not a contradiction — they are measurements of *different boards* — but the
hazard note now sits beside a current number while describing a prior one, and a
reader checking "is clearance near its 499 cap" gets 179 from a board that is no
longer the subject. It reads as current and is not. Worth re-deriving on the
next ceiling touch; not corrected here, because `AGENTS.md` requires ceiling
edits to carry their own re-measurement discipline and this document changes no
ceiling value.

## 4. What this does not change

- **The PD3 decision.** `docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md`
  stands: the board is forced-air-vented and compartment-less, and the owner
  confirmed on 2026-08-24 that no enclosure is planned near-term.
- **Any individual finding.** `K1`↔`R56` at 5.036 mm and `RT1`↔`K1` at 7.000 mm
  are among the 114.
- **That the gates are correctly red.** 114 is not zero.

## 5. Reproducing

```bash
uv run --no-sync python scripts/measure_uncapped_drc.py dru-category creepage \
  --dru-generator scripts/generate_kicad_dru.py --scratch-dir /tmp/drc --json /tmp/creepage.json
uv run --no-sync python scripts/measure_uncapped_drc.py dru-category clearance \
  --dru-generator scripts/generate_kicad_dru.py --scratch-dir /tmp/drc2 --json /tmp/clearance.json
```

~10 minutes each. `--json` writes the full band tree including each band's scoped
DRU and raw count, so the partition is auditable rather than trusted.

## 6. Sources

- `power_pcb_dataset/drc_ceiling.json` — the committed counts this run confirms,
  and §3's stale hazard note.
- `docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md` — the PD3 decision,
  and the 377/1663 figures superseded by the later ceiling re-measure.
- `scripts/measure_uncapped_drc.py` — the uncapped partition counter.
- `docs/evidence/2026-08-24-k1-isolation-barrier-triage.md` — two of the 114.
