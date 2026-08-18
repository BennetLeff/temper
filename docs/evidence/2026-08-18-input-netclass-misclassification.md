# `input` is affirmatively-declared HV, classed `Default` on both enforced surfaces

**Status: investigation. Nothing changed.** The evidence supports a
reclassification, but it **reduces enforced creepage on 10 net pairs**, so it
is a proposal awaiting owner sign-off. Board sha256
`26981fea2dbc425f...` verified identical before and after.

## 1. What `input` physically is

**UCC21550 pin 10 = OUTB, secondary (HV) side.** Established from `elec/src`,
then confirmed independently against the board's pad→net map rather than
inferred from the manifest's own summary.

Wiring, `elec/src/modules.ato`:

- `:423` `gate_hs.driver.OUTB ~ gate_ls.input`
- `:424` `dc_bus.hv_minus ~ gate_hs.driver.VSSB`
- `:425` `gate_hs.driver.VSSB ~ gate_ls.input_ref`
- `:435-437` `power_15v_ls.vcc ~ gate_hs.driver.VDDB`, `power_15v_ls.gnd ~ dc_bus.hv_minus`, `voltage = 15V`

`elec/src/components.ato:71-74` places pins 9 (VSSB), 10 (OUTB), 11 (VDDB)
under the component's own `# Secondary side` comment.

U6 (`lib:SOIC16W_Isolated`) pad→net map, read from `pcb/temper.kicad_pcb`:

| pad | net | side |
|---|---|---|
| 1, 2 | `ina`, `inb` | primary |
| 3, 8 | `+3V3` | primary |
| 4 | `gnd` | primary |
| 5 | `SHUTDOWN` | primary |
| 6 | `hb.gate_hs.driver-p1` (DT) | primary |
| **9** | **`hb-gnd`** (VSSB) | **secondary** |
| **10** | **`input`** (OUTB) | **secondary** |
| **11** | **`+15V_LS`** (VDDB) | **secondary** |
| 14, 15, 16 | `hb.gate_hs.driver-p2`, `GATE_HS`, `hb.gate_hs.driver-p1-1` | secondary |

`input` is physically sandwiched between two already-declared HV-domain nets
on adjacent pins of one package. Reference is `VSSB` = `hb-gnd` =
`dc_bus.hv_minus`.

- **Relative to `hb-gnd`: 0–15 V** — the gate swing, bounded by `VDDB` =
  `+15V_LS`, asserted `<= v_cc_sec_max` 25 V at `modules.ato:438`.
- **Relative to `PWR_RTN`: ≈ −170 V to −155 V.**
- Relative to `SW_NODE`: functional, not safety — both secondary side of U6's
  single barrier.

**Categorically not SELV.** Only two pads carry it: `R22.1`
(`hb.gate_ls.rg_on`) and `U6.10`.

## 2. It is affirmatively declared HV — not an absence case

`elec/domain_manifest.yaml:251`, under `domains.HV.nets`, with a 28-line
netlist trace naming U6.10/OUTB and R22.1 explicitly. Committed in
`96db2ccde` (PR #1134, 2026-08-15) — predates this investigation, not
self-authored.

Three distinguishable states exist in this manifest, and this is the
strongest: affirmative-HV (`input`), affirmative-SELV (`DISCHARGE_CTRL` at
`:457`), deliberately-undeclared (the four OVP mid-chain nodes).

## 3. Current classification: absent from both enforced surfaces

- `core/design_rules.py:475` `TEMPER_NET_ASSIGNMENTS` — **no `"input"` key**,
  and it matches no pattern in the fallback cascade. Measured live:
  `create_temper_design_rules().get_rules_for_net("input")` →
  `class=Default, clearance=0.15, safety_category=None`.
- `pcb/temper.kicad_pro` `net_settings.netclass_assignments` (100 entries) —
  **no `input` key** → KiCad `Default`, 0.2 mm.

The surfaces that read the manifest already disagree:
`router_v6.clearance_check._classify_net_class("input")` → **`"HV"`**, and
**`scripts/check_hv_netclass_coverage.py` already fails closed on this
today**, unprompted, under PROPERTY 1 and BLOCKING PROPERTY 3 — one of 7 such
nets; the other 6 are the `discharge.*` group.

## 4. All ten current violations are same-domain false positives

Measured with `pcb/temper.kicad_dru` regenerated (gitignored — without it
creepage reads 0) and `fp-lib-table` copied beside each scratch board
(confirmed `lib_footprint_issues`=16 / `lib_footprint_mismatch`=25, not the
168/0 signature).

| rule | req | actual | pair |
|---|---|---|---|
| `HV to LV` clearance | 2.0 | 0.6700 | U6.10 ↔ U6.9 `hb-gnd` |
| `HV to LV` creepage | 12.6 | 0.6700 | U6.10 ↔ U6.9 `hb-gnd` |
| `HighVoltageSignal to LV` clearance | 2.0 | 0.6700 | U6.10 ↔ U6.11 `+15V_LS` |
| `HighVoltageSignal to LV` creepage | 12.6 | 0.6700 | U6.10 ↔ U6.11 `+15V_LS` |
| `HighVoltageIsolated to LV` creepage | 12.6 | 4.4800 | U6.10 ↔ U6.14 `VSSA` |
| `HighVoltageIsolated to LV` creepage | 12.6 | 7.0200 | U6.10 ↔ U6.16 `VDDA` |
| `HV to LV` creepage | 12.6 | 6.3762 | U1.1 `+170V_BUS` ↔ R22.1 |
| `HV to LV` creepage | 12.6 | 6.1149 | U2.2 `DC_BUS_RTN` ↔ R22.1 |
| `HV to LV` creepage | 12.6 | 6.4091 | C1.1 `w1_1` ↔ R22.1 |
| `HV to LV` creepage | 12.6 | 10.7889 | U1.2 `power_in.ntc-no` ↔ R22.1 |

**Zero true positives.** Every counterparty is an HV-domain net.

The two 0.670 mm figures are **the SOIC-16W pad geometry itself** (1.27 mm
pitch − 0.6 mm pad width) — **unsatisfiable at any placement.**

Note the R22.1 counterparties are `+170V_BUS`/`DC_BUS_RTN`/`w1_1`/
`power_in.ntc-no` — **not `SW_NODE`**; no `input`↔`SW_NODE` pair is reported
at any distance. kicad-cli emits one row per *net pair*, which is why the
`hb-gnd` pair is reported at U6.10 rather than R22.1.

## 5. `GateDriveHV` measured and rejected

It clears all 10 false positives and surfaces **nothing**. `GateDriveHV` is
excluded from the B-side of every reinforced rule in the `.kicad_dru` and
declares no creepage constraint as an A-side, so `input` would owe **zero
creepage to any net on the board** — including `+3V3`, `gnd`, `SHUTDOWN`, and
the fan connector.

**On a −170 V-referenced conductor that is making a check pass by weakening
it.** It is also inconsistent with pads 9 and 11 either side of it, which
both carry the full reinforced set today.

`HighVoltage` also rejected: correct domain, but drags in the 5.0 mm
current-carrying trace width sized for the 15–22.5 A bus/tank tier, and an
extra `HV internal same footprint` clearance row.

## 6. Proposal: `HighVoltageSignal`

Same voltage domain, same `safety_category: HV`, same clearance 2.0 /
creepage 6.0 as **`+15V_LS`** — `input`'s own supply rail on the adjacent
pin. `trace_width` 0.5 mm matches the mA gate-drive tier.

Precedent, not new judgement: `+15V_LS`, `zcd`, `a`, and
`hb.power_loop.q_high-g` were re-scoped `HighVoltage` → `HighVoltageSignal`
on 2026-08-13. **`hb.power_loop.q_high-g` — the high side's structural mirror
of `input` — is already `HighVoltageSignal` on both surfaces.**

## 7. Measured DRC delta

kicad-cli is **nondeterministic run-to-run** (base measured 778 then 777
total; creepage 106 then 105), so each variant was run **3× and intersected**.
Every `input`-touching row below was identical in all runs; residual jitter is
confined to `shorting_items` item-order and one unrelated `K3` row.

Totals **778 → 778**. Clearance 179 → 178, creepage 106 → 107.

**CLEARED — 10 rows, all safe.** Exactly the table in §4.

- vs `hb-gnd` (pad 9) and `+15V_LS` (pad 11): `input`'s **own return and own
  supply**, working voltage 0–15 V. A 12.6 mm reinforced barrier between a
  driver output and its own VSSB/VDDB is physically meaningless, and both sit
  at the package-fixed 0.670 mm.
- vs `VSSA`/`VDDA` (pads 14/16): same secondary side of U6's single barrier.
  The 12.6 mm creepage requirement is replaced by the surviving
  `HighVoltageIsolated same side` 2.0 mm clearance rule, met at 4.48/7.02 mm.
  **Pads 9 and 11 already receive precisely this treatment today** — base
  contains no creepage row between pad 9 or 11 and pads 14/16.
- vs the four HV nets at R22.1: same single non-isolated HV domain per the
  manifest. The 2.0 mm `HighVoltageSignal` netclass clearance survives and is
  met at 6.11–10.79 mm.

**This is the reduction requiring sign-off**: ten pairs lose a 12.6 mm
creepage requirement. In every case it drops to a 2.0 mm clearance
requirement that is either met or still reported. **No pair becomes
invisible.**

**NEW — 10 rows, 9 genuine reinforced-barrier exposures against LV/SELV:**

| req | actual | pair |
|---|---|---|
| clearance 2.0 | 0.6700 | U6.10 ↔ U6.9 `hb-gnd` (HV↔HV pair, correctly rescored) |
| creepage 12.6 | 8.1000 | U6.10 ↔ U6.7 `nc_7` |
| creepage 12.6 | 8.1558 | U6.10 ↔ U6.8 `+3V3` |
| creepage 12.6 | 8.1558 | U6.10 ↔ U6.6 DT (primary) |
| creepage 12.6 | 8.3935 | U6.10 ↔ U6.5 `SHUTDOWN` |
| creepage 12.6 | 8.8039 | U6.10 ↔ U6.4 `gnd` |
| creepage 12.6 | 10.0519 | U6.10 ↔ U6.2 `inb` |
| creepage 12.6 | 10.8419 | U6.1 `ina` ↔ U6.10 |
| creepage 12.6 | 11.4706 | J2.1 `thermal.j_fan-p1` ↔ U6.10 |
| creepage 12.6 | 12.4691 | U6.10 ↔ R62.2 `safety.coil_thermal.comp-inp` |

**These are not novel.** Base already contains the byte-identical shape for
pads 9, 11, 14 and 16 against the same primary-side pins in the same 8–11 mm
band (`+15V_LS`↔`+3V3` 8.3935, `hb-gnd`↔`gnd` 9.3648, `hb-gnd`↔`J2.1`
10.2328, `hb-gnd`↔`R62.2` 11.3855). **`input` is currently the only
secondary-side U6 pin not producing them — because it is the only one classed
`Default`.** The reclassification makes it consistent with its four
neighbours.

`U6.10↔U6.11` confirmed a genuine false positive and **clears**: both rows
disappear entirely, replaced by the `Same footprint pads` / `Fine pitch IC
pads` 0.1 mm intra-package rule. Still evaluated, at the requirement that
actually applies to two pins of one package.

## 8. Placement consequence

**The CP-SAT placer is not the binding constraint and does not move.**
Measured through the live API: R22 resolves `GateDriveHV` (via its `GATE_LS`
pin), U6 resolves `HighVoltageIsolated`; no `class_pairs` entry; fallback
6.0 mm — **identical before and after under all three candidate classes.**

**The DRU creepage floor is what pins R22 away.** R22.1 owes 12.6 mm creepage
to U6 pads 9 and 11, which straddle pad 10 at 1.27 mm pitch, so it cannot
approach closer than ≈**11.3–11.9 mm** — held away from the very pin it wires
to. Under `HighVoltageSignal` the binding requirement becomes the 2.0 mm
netclass clearance to pad 9 (pad 11 becomes same-class), giving a floor of
≈**0.7–2.0 mm**. A ~6× reduction.

(The 81.03 mm R22.1↔U6.10 distance on the committed board reflects placement
predating `fix/gate-loop-placement-apply`; the floor above is
placement-independent.)

## 9. Follow-on

- Fixing this requires **two** entries, not one: `TEMPER_NET_ASSIGNMENTS`
  (PROPERTY 1) **and** `pcb/temper.kicad_pro` `netclass_assignments`
  (PROPERTY 3). The Python table alone changes nothing kicad-cli enforces —
  the `hb-gnd` precedent deliberately left PROPERTY 3 red.
- No oracle re-pin is needed:
  `test_design_rules_rust_differential.py::test_module_constants_identical` is
  **already red on `origin/main`** from `hb-gnd`.
- **The 6 `discharge.*` nets flagged alongside `input` by PROPERTY 1/3 are the
  same defect shape** and are unexamined here.
- The 9 new genuine violations need routing/placement remediation before this
  ships green.
