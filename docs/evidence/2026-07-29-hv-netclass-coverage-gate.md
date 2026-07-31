<!-- provenance: commit=cbaad2eb7f53b23320316d75f0e767faaf371955 dirty=false (base) -->

# HV netclass coverage gate: design, motivating defects, and before/after proof

> **Re-measurement note (2026-07-31):** the before-side numbers below were
> re-measured against today's `origin/main` tip (`4a387393e`) on 2026-07-31,
> because the gate's original validation (this document's first draft,
> 2026-07-29) measured a main that has since advanced by several merged
> slices (`#434`, `4c59d7550`, `#440`-adjacent fixes). The qualitative
> finding holds and the specific names have changed -- see the
> "Before: today's origin/main" section. Both runs used the gate as it
> exists on this branch (`feat/hv-netclass-coverage-gate`,
> base `cbaad2eb7`), invoked as
> `python scripts/check_hv_netclass_coverage.py` with the measured tree's
> own `elec/domain_manifest.yaml`, `pcb/temper.kicad_pro`,
> `temper_placer.core.design_rules`, and `scripts/generate_kicad_dru.py`.

`scripts/check_hv_netclass_coverage.py` is a CI gate asserting two
properties nothing in the repo previously checked, both of which failed in
production on `origin/main` in the 2026-07-28/29 defect cluster:

1. **Every HV-domain net has a netclass** -- every net
   `elec/domain_manifest.yaml` declares under its `HV` domain (the
   hand-reviewed, human-curated SSOT for which nets are mains/HV, also
   relied on by `scripts/check_domain_partition.py`) must have an entry in
   `TEMPER_NET_ASSIGNMENTS`
   (`packages/temper-placer/src/temper_placer/core/design_rules.py`). A
   manifest-HV net absent from that table silently falls through to
   `DesignRules`' low-voltage default clearance/creepage for every
   Python-side (CP-SAT placer, router_v6) decision.
2. **Every declared netclass carries real rules** -- every class declared
   as a real, intentional netclass (the union of `TEMPER_NET_CLASSES` keys
   and `pcb/temper.kicad_pro`'s `net_settings.classes` entries with a
   non-empty `description`, minus the KiCad-structural `Default` and
   `Differential` classes) must have at least one POSITIVE
   `A.NetClass == 'X'` / `B.NetClass == 'X'` rule in
   `scripts/generate_kicad_dru.py`'s generated output. A class mentioned
   only negatively (`!= 'X'`), or not at all, enforces nothing for any net
   assigned to it.

The gate is fail-closed: it exits non-zero (exit 5, GATE ERROR) for every
degenerate input (missing/empty/malformed manifest or `kicad_pro`, no `HV`
domain, zero declared netclasses, empty DRU output, unimportable live
environment) and exits 3 (VIOLATION) when either property fails. It never
exits 0 unless it positively ran a real check on real data.

## Motivating defects (all confirmed on origin/main, 2026-07-28/29)

1. **`+170V_BUS` resolved to NO netclass.** The live 170V DC bus
   (declared under `domain_manifest.yaml`'s `HV` domain) had no
   `TEMPER_NET_ASSIGNMENTS` entry at all -- the table carried the stale
   `+340V_BUS` key, which matches zero compiled nets. `DesignRules`
   therefore applied its low-voltage default to the live DC bus. Fixed on
   main by `4c59d7550` ("classify the live 170V bus") and the sweep on
   this branch's base; the fix is present in today's `origin/main`.
2. **`HighVoltageIsolated` existed with zero DRC rules.** The
   gate-drive floating bootstrap-supply netclass was declared (with a
   real, described 6.0mm-clearance entry) in `pcb/temper.kicad_pro`, but
   `scripts/generate_kicad_dru.py` emitted zero rules referencing it by
   name -- any net assigned the class inherited only KiCad's per-netclass
   baseline clearance and no creepage protection. Fixed on main by
   `81f3c69a5` (#434 slice 4 of 8); main's DRU now carries the
   "HighVoltageIsolated same side" / "HighVoltageIsolated to LV" rules.
3. **`+15V_LS` (HV) assigned the low-voltage `Power` class.** Full
   analysis in `docs/evidence/2026-07-28-netclass-defect-reconciliation.md`
   (Defect 1). Note the gate's PROPERTY 1 deliberately checks *presence in
   `TEMPER_NET_ASSIGNMENTS`*, not the *safety category of the assigned
   class* -- the wrong-class shape is caught by that sweep's evidence
   trail, not by this gate (see the scope note below). The class split that
   made `+15V_LS`'s fix durable (GateDrive -> GateDriveHV/GateDriveSELV)
   IS enforced by PROPERTY 2: a declared class with no positive rules is
   flagged.

## Before: today's origin/main (re-measured 2026-07-31, `4a387393e`)

Run: the gate script copied onto a detached worktree of `origin/main`
(`4a387393e`), executed against that tree's own manifest, `kicad_pro`,
`design_rules.py`, and `generate_kicad_dru.py`.

```
HV netclass coverage gate -- 21 HV-domain net(s) checked against
TEMPER_NET_ASSIGNMENTS, 12 declared netclass(es) checked against
scripts/generate_kicad_dru.py's generated rules

=== PROPERTY 1: UNCLASSIFIED HV NETS: 0 ===
=== PROPERTY 2: NETCLASSES WITH NO RULES: 1 ===
  VIOLATION netclass 'GateDrive' is a declared netclass (TEMPER_NET_CLASSES
  and/or pcb/temper.kicad_pro) but scripts/generate_kicad_dru.py's generated
  output contains zero rules positively matching NetClass == 'GateDrive' --
  this class enforces nothing for any net assigned to it

FAILED -- 0 unclassified HV net(s), 1 netclass(es) with no rules
```

Interpretation: main fixed the `+170V_BUS` and `HighVoltageIsolated`
defects in the slices above (hence `0` unclassified and
`HighVoltageIsolated` now covered), but `pcb/temper.kicad_pro` on main
still declares the legacy pre-split **`GateDrive`** class (with a real
description), while main's DRU generator -- updated by the same split --
emits only `GateDriveHV`/`GateDriveSELV` rules. `GateDrive` is therefore a
live declaration that matches zero rules: any net still assigned it (and
main's kicad_pro/netlist-era boards still reference it) gets no
class-specific enforcement. This is the exact PROPERTY 2 failure shape the
gate exists to catch, at a smaller scale than the original
`HighVoltageIsolated` case.

## After: this branch (`feat/hv-netclass-coverage-gate`, base `cbaad2eb7`)

The branch carries `cbaad2eb7` ("replace legacy GateDrive class with
GateDriveHV/GateDriveSELV split"), which fixes the kicad_pro declaration
side of the split. Run against this branch's own tree:

```
HV netclass coverage gate -- 21 HV-domain net(s) checked against
TEMPER_NET_ASSIGNMENTS, 11 declared netclass(es) checked against
scripts/generate_kicad_dru.py's generated rules

=== PROPERTY 1: UNCLASSIFIED HV NETS: 0 ===
=== PROPERTY 2: NETCLASSES WITH NO RULES: 0 ===

HV netclass coverage gate passed
```

11 declared classes (vs 12 on main): the legacy `GateDrive` class is gone
from `pcb/temper.kicad_pro`, leaving `GateDriveHV` and `GateDriveSELV`,
both positively referenced by the DRU generator.

## Scope boundary: what this gate deliberately does not check

PROPERTY 1 asserts *presence* of a `TEMPER_NET_ASSIGNMENTS` entry, not
that the assigned class's `safety_category` is HV/AC. The wrong-class
shape (`+15V_LS` -> `Power`; the still-open `PWR_RTN` -> `GND` case,
`docs/evidence/2026-07-28-netclass-defect-reconciliation.md` section 3c,
flagged for a human call) is deliberately outside this gate: enforcing it
would flag `PWR_RTN`, whose reclassification has an order-of-magnitude
larger blast radius (85-pin system-return net; a placement-zone concern
documented in `configs/temper_production_config.yaml`). The boundary is
tracked in issue temper#519 (PWR_RTN classification) rather than silently
enforced here. PROPERTY 2, by contrast, does make the GateDrive split
durable -- a class that exists but matches no rule is always flagged.
