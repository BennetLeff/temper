<!-- provenance: commit=c9ade7db014bd07b754651264f77b939fdf8188f dirty=UNKNOWN (stamp added retroactively 2026-08-24: this document landed in #1466 with no provenance line, which is why the "Evidence provenance gate (docs/evidence/)" step has been failing. c9ade7db0 is the commit that introduced the file, not necessarily the tree its figures were measured against -- hence dirty=UNKNOWN rather than a claim this document cannot support. The author of #1466 should replace this with the real measurement commit if it differs.) -->

# 2026-08-23 — HV_to_ISO creepage figure decision package (SSOT-drift gate red)

## The finding

`scripts/check_creepage_clearance_drift.py` fails closed on one NOT-accepted
declaration:

```
elec/src/constraints.ato:104 (HV_to_ISO.min_creepage): metric=creepage
value=8.0mm (unspecified tier)
```

against the enforced PD3 barrier figure of **12.6 mm** (creepage/reinforced
family). The gate's own message: "a reappearing PD2 declaration fails this
gate closed."

## What HV_to_ISO physically is

`constraints.ato:102-106`:

```
module HV_to_ISO:
    min_clearance = 6.0mm
    min_creepage = 8.0mm
    requires_slot = True
```

declared "HighVoltage to HighVoltageIsolated: Across isolation barrier".

Per `elec/domain_manifest.yaml` and the DRU's own analysis
(`scripts/generate_kicad_dru.py`, RULE 4a/4b block), `HighVoltageIsolated`
nets (+5V_ISO, VBOOT_H/L, hb.gate_hs.driver-p1-1/-p2) are the UCC21550 gate
driver's secondary-side floating supply — they **float with SW_NODE** and are
members of the same declared HV domain as ac_l/+170V_BUS/SW_NODE. The pair
HV ↔ HighVoltageIsolated is therefore *same-domain functional*, not a
reinforced cross-barrier boundary:

- DRU RULE 4a gives it **2.0 mm functional clearance and NO creepage**
  constraint.
- RULE 4b puts the real 12.6 mm reinforced barrier on
  HighVoltageIsolated ↔ LV/SELV instead.

## Why the 8.0 mm is stale

8.0 mm is the PD2 reinforced figure from the pre-2026-08-15 era. When the
2026-08-15 data-driven decision (`docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md`,
PR #1229) set PD3/12.6 mm as the as-built bar, the same changeset aligned
`HV_to_LV.min_creepage` to 12.6 mm — but missed `HV_to_ISO.min_creepage`.
The SSOT-drift gate has correctly refused to accept it since.

## Options

**(A) Align to the enforced model**: change `HV_to_ISO.min_creepage`
8.0 → none (delete the field; the DRU carries no creepage for this pair) or
to 12.6 mm if the author intended extra conservatism for the driver's own
internal barrier. Note the DRU's RULE 4a already gives the pair only 2.0 mm
functional clearance, so an 8.0 mm *creepage* declaration constrains nothing
the DRU doesn't already treat as functional — it is dead weight that breaks
the SSOT gate.

**(B) Keep 8.0 mm with an ACCEPTED-drift entry** citing the UCC21550's
internal galvanic barrier as a component-level requirement distinct from the
board-level model. This needs a datasheet citation for the 8.0 mm figure —
none exists in the repo today (the value predates the evidence-doc era).

## Recommendation

Option (A), specifically **aligning to the DRU: remove the creepage line and
keep `min_clearance = 2.0mm` matching RULE 4a**, unless the owner wants the
conservatism of (B) with a sourced figure. The current 8.0 mm is a PD2-era
holdover that contradicts both the enforced model (functional) and the PD3
decision (12.6 mm) — it is neither.

## Sign-off

Owner decision recorded here: ____________ (A / B / other)
