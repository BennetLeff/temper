<!-- provenance: commit=2abb246db697da2685a652b93632a42d11595d51 dirty=false (branch analysis/isolation-pad-pair-binding, cut fresh from origin/main @ 2abb246db). pcb/temper.kicad_pcb sha256=26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b -- verified before and after; the board file was NEVER written by this work. pcb/temper.kicad_dru regenerated in-worktree by scripts/generate_kicad_dru.py against a freshly built .venv (make venv-isolate; scripts/check_stale_extensions.py = 10/10 fresh) -- it is gitignored and generated, and creepage reads 0 without it. Pad-pair distances computed with the repo's canonical kernel temper_placer.core.pad_geometry.pad_pair_distance (temper-geometry Rust). Cross-checked against kicad-cli 10.0.5 (/home/bennet/.local/bin/kicad-cli), 3 runs intersected (297/298/297 violations -> 261 stable keys); every distance below reproduces to 4 decimals in both. Domains read from elec/domain_manifest.yaml; netclasses from pcb/temper.kicad_pro net_settings.netclass_assignments (the surface kicad-cli enforces), cross-read against temper_placer.core.design_rules.TEMPER_NET_ASSIGNMENTS. -->

# The five "unfixable" isolation parts: which pad pair actually binds

Max intra-package pad span is not the quantity that matters, and for three of
these five parts it is not even measured across pads that carry opposite
domains. K1's 25.06 mm is **mounting-hole to mounting-hole** (two NPTH pads
with no net); T1/T2's 20.06 mm and U6's 13.19 mm are **pad-centre to
pad-centre**, which over-reports edge-to-edge creepage by half the sum of the
two pads' extents. The binding quantity is
`min over {HV pad} x {SELV pad}` of exact copper-edge distance.

## Verdict table

| part | binding pad pair | nets | domains | actual | required | requirement type | class |
|---|---|---|---|---|---|---|---|
| **C6** | 1 / 2 | `PWR_RTN` / `gnd` | HV / SELV | **8.0000 mm** | 12.6 mm | reinforced (`HV to LV`) | **(a)** |
| **K1** | *(none on copper)* | — | — | **n/a** | n/a | n/a | **(c)** |
| **T1** | 1/4 **and** 2/3 (tie) | `tank-out`/`gnd`, `PWR_RTN`/`I_SENSE` | HV / SELV | **9.1000 mm** | 12.6 mm | reinforced (`HV to LV`) | **(a)** |
| **T2** | 1/4 **and** 2/3 (tie) | `hb-gnd`/`gnd`, `DC_BUS_RTN`/`s1` | HV / SELV | **9.1000 mm** | 12.6 mm | reinforced (`HV to LV`) | **(a)** |
| **U6** | 8/9 (+5 tied) | `+3V3` / `hb-gnd` | SELV / HV | **8.1000 mm** | 12.6 mm | reinforced (`HV to LV`) | **(a)** |

No part is **(b)**. For every one of the four genuine cases the constraint is
package-fixed, and the proof is the same in each: the pads carrying opposite
domains are partitioned by the part's internal function into two fixed groups
(primary/secondary, HV-side/SELV-side), so the set of HV↔SELV pad pairs is the
full cross product of those groups **regardless of which net goes to which pin
within a group**. `min` over a cross product is invariant under permutation
within either factor. Reassignment cannot move it.

## Per part

### C6 — `Capacitor_THT:C_Disc_D12.5mm_W5.0mm_P10.00mm` — (a)

Two pads, one pair, and that pair *is* the barrier: `power_in.y_cap_pe` is
declared an isolator in `elec/domain_manifest.yaml` with `hv_side: [1]`,
`selv_side: [2]`. 2.0 mm circular pads at 10.00 mm pitch → **10.00 − 2.00 =
8.0000 mm**. Confirmed by kicad-cli: *"Creepage violation (rule 'HV to LV'
creepage 12.6000 mm; actual 8.0000 mm) / PTH pad 1 [PWR_RTN] of C6 / PTH pad 2
[gnd] of C6"*. Deficit **4.6000 mm**.

The "10.00 mm max intra-package pad gap" in the framing question is the
**centre-to-centre** pitch. The 2.0 mm pad diameter is the other 2.0 mm of the
answer.

**Geometric requirement for a replacement** (no part number — that is a
procurement decision): a two-lead THT capacitor whose land satisfies
`pitch − pad_diameter ≥ 12.6 mm`.

| pad dia | min lead pitch |
|---|---|
| 1.4 mm | 14.00 mm |
| 2.0 mm | 14.60 mm |
| 2.4 mm | **15.00 mm** |
| 2.5 mm | 15.10 mm |

A 15 mm-pitch part clears 12.6 mm **exactly and only** at a 2.4 mm pad — zero
margin. 17.5 mm and 22.5 mm pitches leave real margin.

**Already actioned in `elec/`, not on the board.** `elec/src/modules.ato:~1010`
already specifies TDK B81123C1562M000 on
`Capacitor_THT:C_Rect_L26.5mm_W7.0mm_P22.50mm_MKS4` (2.4 mm pads @ 22.50 mm →
**20.1000 mm**, +7.5 mm margin). `pcb/temper.kicad_pcb` still carries the
10.00 mm disc land. That footprint is not in `pcb/libs/` — it is a stock KiCad
library part.

### K1 — `temper:Relay_SPST_Omron-G4A-E` — (c), and the brief's premise does not hold here

**K1's contact pads carry no copper.** Pads `13` (`power_in.ntc-no`) and `14`
(`w1_2`) are `(layers "F.Fab")` only — no `*.Cu`, no `*.Mask`, no `*.Paste`.
This is deliberate and documented in the footprint's own `descr`: the
G4A-1A-E's contacts are #250 Faston **tab terminals** that protrude from the
opposite face of the relay body and have **zero PCB land**; representing them
as F.Cu previously manufactured a fictitious land that shorted two mains nets
(`docs/evidence/2026-07-29-intra-component-shorts-root-cause.md`).

Consequence: **K1 has no HV↔SELV pad pair on copper at all.** Its only copper
pads are `A1`/`A2` (`power_in.bypass_relay-coil1/-coil2`, both SELV, netclass
`Power`), 4.5500 mm apart, owing nothing. kicad-cli 10.0.5 reports **zero
violations of any type** naming K1 — creepage, clearance or otherwise.

The 8.000 mm figure that appears in `elec/src/modules.ato:756` and in
`pad_geometry.py`'s own docstring is `A1`↔`13` measured as pure geometry
against a silkscreen-layer marker. It is a real distance between the *physical*
terminals of the *real relay*; it is not a PCB creepage path, because there is
no copper at one end of it.

For completeness, the geometric coil↔contact distances are A1/13 = A2/14 =
**8.0000 mm**, A1/14 = A2/13 = **8.5494 mm** — so even the best coil-to-contact
pairing in this package is 4.05 mm short, and the part is (a)-shaped as a
*part*. But on this board it is not an intra-footprint copper problem. The open
question the footprint `descr` already raises — *how* `power_in.ntc-no`/`w1_2`
physically reach the tabs — is unresolved and is where the barrier actually
lives.

Also measured, and worth flagging: pads 13/14 are **0.0000 mm apart** (6.35 mm
rects on a 6.35 mm pitch — they abut exactly). Harmless today only because
neither has copper.

**Already actioned in `elec/`, not on the board.** `elec/src/modules.ato:756-770`
replaced the G4A-1A-E with TE Schrack RT33K012 on
`temper:Relay_SPST_Schrack-RT33K012` (present in `pcb/libs/temper.pretty/`).
Measured here with the canonical kernel: min coil↔contact = **17.8000 mm**,
clears 12.6 mm by +5.2 mm. `elec/domain_manifest.yaml`'s isolator entry for
`power_in.bypass_relay` still names the outgoing Omron part — stale.

### T1 — `temper:CST3015` — (a)

`ct_sense.ct`, declared isolator, `primary: [1,2]` / `secondary: [3,4]`.

| pad | net | netclass | domain |
|---|---|---|---|
| 1 (P1) | `tank-out` | HighVoltage | HV |
| 2 (P2) | `PWR_RTN` | HighVoltage | HV |
| 3 (S1) | `I_SENSE` | FinePitch | SELV |
| 4 (S2) | `gnd` | GND | SELV |

All four cross pairs (exact copper edge distance):

| pair | distance | requirement |
|---|---|---|
| 1/4 | **9.1000 mm** | 12.6 reinforced — deficit 3.5000 |
| 2/3 | **9.1000 mm** | 12.6 reinforced — deficit 3.5000 |
| 1/3 | 12.4933 mm | 12.6 reinforced — deficit **0.1067** |
| 2/4 | 12.4933 mm | 12.6 reinforced — deficit **0.1067** |

kicad-cli independently reports all three distinct values (9.1000 ×2,
12.4933) on T1. The 20.06 mm "max intra-package pad gap" is pad-1-centre to
pad-3-centre; the true edge distance for that same pair is 12.4933 mm — the
7.57 mm difference is the two pads' own half-extents.

**No reassignment helps.** Both primary pads are HV and both secondary pads
are SELV, so all four cross pairs are HV↔SELV whichever way the nets go. The
min is 9.1000 mm under every permutation. Even the package *maximum* cross
distance, 12.4933 mm, misses 12.6 mm by 0.1067 mm — so this package cannot
reach the requirement at its own best case, let alone its worst.

Note the near-miss is a genuine finding, not a rounding artifact: it is
reported identically by the Rust kernel and by kicad-cli.

Also present intra-footprint: pads 1/2 at **6.3600 mm**, `tank-out` ↔
`PWR_RTN`, HV↔HV. This owes **no** creepage under the current DRU — the only
HV↔HV creepage rule is `HighVoltageTank functional creepage` (10.0 mm), whose
A-side is `HighVoltageTank`, and `tank-out` is classed `HighVoltage`, not
`HighVoltageTank`. Recorded, not asserted as a violation.

### T2 — `temper:CST3015` — (a), and it is **not on the board**

Identical footprint, identical geometry, identical conclusion: min cross pair
**9.1000 mm** at 1/4 and 2/3 (`hb-gnd`/`gnd` and `DC_BUS_RTN`/`s1`), max
12.4933 mm.

But T2 sits at `(at 100 300 0)` — its pads span y ≈ 293.15…306.95, and the
board's `Edge.Cuts` bounding box is x [8.00, 172.00] y [20.00, 254.00]. **T2 is
entirely outside the board outline**, and kicad-cli reports zero violations of
any type naming T2. This is consistent with `elec/src/main.ato:785` and
`modules.ato:2686`, both of which record that the second CST3015-100ED has not
been placed. Its binding pair is a footprint-level fact, not a measured
board-level violation — any statement that T2 "fails to straddle a corridor"
is about a part that has no position yet.

### U6 — `lib:SOIC16W_Isolated` (UCC21550BDWK, DWK-14) — (a)

Pads 1–8 are the primary (SELV-referenced: INA, INB, VCCI_1, GNDI, DIS, DT,
NC_7, VCCI_2); pads 9, 10, 11, 14, 15, 16 are the secondary (HV, floating on
`hb-gnd`/`DC_BUS_RTN`). Positions 12/13 do not exist on DWK. Row separation
9.75 mm centre-to-centre, pad 1.65 mm long × 0.60 mm wide, 1.27 mm pitch.

**All 48 primary↔secondary pad pairs:**

- **MIN = 8.1000 mm**, attained by six directly-opposite pairs: 1/16, 2/15,
  3/14, 6/11, 7/10, 8/9. The nameable binding pair — both sides unambiguously
  domain-declared and carrying a live 12.6 mm rule — is **8 (`+3V3`, SELV,
  netclass `Power`) ↔ 9 (`hb-gnd`, HV, netclass `HighVoltage`)**, rule
  `HV to LV`, deficit **4.5000 mm**. kicad-cli confirms: *"actual 8.1000 mm /
  Pad 8 [+3V3] of U6 / Pad 9 [hb-gnd] of U6"*.
- **MAX = 11.7145 mm**, attained by the two package diagonals 1/9 and 8/16.

That maximum is the decisive number: **the largest primary-to-secondary pad
separation this package can offer is 11.7145 mm, 0.8855 mm short of 12.6 mm.**
Every primary pad is SELV by the isolator's construction and every secondary
pad is HV, so no assignment of nets to pins — and no depopulation of end pins —
can produce a package where all HV↔SELV pairs clear 12.6 mm. **(a)**, proved by
the package extreme rather than by enumeration of proposals.

`9.75 mm row pitch − 1.65 mm pad length = 8.10 mm` is where the number comes
from. The "13.19 mm max intra-package pad gap" is centre-to-centre 1↔9; its
true edge distance is 11.7145 mm.

**Intra-row pairs, physically unsatisfiable — a different class of problem.**
Secondary-side neighbours sit at `1.27 − 0.60 = 0.6700 mm`:

| pair | nets | netclasses | rule fired | actual |
|---|---|---|---|---|
| 9/10 | `hb-gnd` / `input` | HighVoltage / **Default** | `HV to LV` 12.6 mm | **0.6700 mm** |
| 10/11 | `input` / `+15V_LS` | **Default** / HighVoltageSignal | `HighVoltageSignal to LV` 12.6 mm | **0.6700 mm** |

Both are reported by kicad-cli today. Both are the SOIC-16W land pattern
itself, unsatisfiable at any placement or rotation, and **both are artifacts of
`input` resolving `Default`** — the misclassification PR #1360 fixes.

## The `input` / `discharge.*` misclassification, accounted for

`input` is declared **HV** in `elec/domain_manifest.yaml` (it is UCC21550 pin
10 = OUTB, referenced to `VSSB` = `hb-gnd`, ≈ −170 V wrt `PWR_RTN`), but is
absent from **both** enforced surfaces on `origin/main`:
`TEMPER_NET_ASSIGNMENTS` has no entry, and `pcb/temper.kicad_pro`'s
`netclass_assignments` has no entry → resolves `Default`. PR #1360 (open)
classifies it `HighVoltageSignal` on both. PR #1363 (open) does the same for
the six `discharge.*` nets — **none of which touch C6, K1, T1, T2 or U6**, so
they do not affect this analysis.

Recomputing U6 with `input = HighVoltageSignal`:

- **Cleared, both 0.6700 mm false positives**: 9/10 becomes
  HighVoltage↔HighVoltageSignal and 10/11 becomes
  HighVoltageSignal↔HighVoltageSignal — both excluded from every reinforced
  rule's B-side. Also cleared: 10/14 (4.4800 mm) and 10/16 (7.0200 mm),
  HVSignal↔HVIsolated.
- **Newly surfaced**: pad 10 against the primary row — 7/10 at 8.1000 mm,
  6/10 at 8.1558 mm, 5/10 at 8.3935 mm, and so on, under
  `HighVoltageSignal to LV`.

This reproduces PR #1360's own measured delta (10 cleared / 10 new, the new
ones "not novel — pads 9/11/14/16 already produce the byte-identical shape").
**It does not change U6's binding pair**: pad 10 was never the minimum, and
8/9 / 1/16 / 3/14 / 6/11 remain at 8.1000 mm either way.

## One coverage gap noticed in passing, not acted on

`GateDriveHV` (pad 15, `GATE_HS`) is excluded from the B-side of every
reinforced creepage rule and is the A-side of none, so `GATE_HS` owes **zero
creepage to any net on this board**, including the SELV primary row 8.1000 mm
away (pair 2/15). That exclusion was added deliberately to kill same-domain
false positives (`docs/evidence/2026-08-11-creepage-gatedrivehv-false-positive.md`)
and PR #1360 explicitly rejected moving `input` there for the same reason.
Whether it over-shoots for the genuine `GateDriveHV`↔SELV direction is a
separate question. **Recorded, not resolved, and nothing here was reclassified
to make anything pass.**

## Reproduction

```
git worktree add -b analysis/isolation-pad-pair-binding <path> origin/main
cd <path> && env -u CONDA_PREFIX make venv-isolate
env -u CONDA_PREFIX .venv/bin/python scripts/generate_kicad_dru.py   # gitignored, required
env -u CONDA_PREFIX .venv/bin/python scripts/measure_isolation_binding_pairs.py
kicad-cli pcb drc --format json --output /tmp/drc.json --severity-error pcb/temper.kicad_pcb  # x3, intersect
```
