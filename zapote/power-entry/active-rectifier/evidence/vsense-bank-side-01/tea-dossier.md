# TEA dossier: all retained evidence for the package-spacing determination

Compiled 2026-09-19 from committed bytes only. Revised same day after
external review (review text retained in session; its determination is
recorded in §8). No new measurements.

Owner determination: **WITHHELD pending correction of the electrical-stress
model and insulation-path assessment** (owner, 2026-09-19 — see §8 for the
full text). No compliance pass is established; the earlier stated threefold
and eightfold creepage deficits are also not established.

## 1. Geometry extracted from retained CAD, and unresolved assembly geometry

CAD extraction (measured from retained files):

- U1 = TEA2209T/1, SOIC-16, 1.27 mm pitch. Footprint pads 1.95 × 0.60 mm
  (`candidate/candidate-libs/Package_SO.pretty/SOIC-16_3.9x9.9mm_P1.27mm.kicad_mod`).
- Endpoint copper separation, ignoring the intervening pad: 2 × 1.27 − 0.60
  = **1.94 mm**, confirmed in native extraction
  (`evidence/vsense-bank-side-01/native.json`, bridge pads F.Cu) and in the
  suite (`evidence/vsense-bank-side-01/common/power-entry.json`,
  `DRC.NATIVE.CLEARANCE_PROFILE` fails on `bridge.3 / bridge.5`,
  `bridge.14 / bridge.16`, `bridge.10 / bridge.12`).

Unresolved assembly geometry (expressly unmeasured): package lead true
widths and positions, solder meniscus/fillets, mask registration over the
gaps, and the complete molded-package surface path. Binding tests (6
passing) substantiate pin/net relationships in the tested representation;
they do not substantiate assembled insulation distances.

Candidate geometric quantities for the three HVS-separated pairs (3–5,
10–12, 14–16) — components of a path assessment, not verdicts:

| Quantity | Calculation | Result |
|---|---|---:|
| Endpoint copper separation, ignoring intervening pad | 2(1.27)−0.60 | 1.94 mm |
| One adjacent PCB-pad gap | 1.27−0.60 | 0.67 mm |
| Sum of two adjacent PCB-pad gaps | 2(1.27−0.60) | 1.34 mm |
| One projected adjacent-lead gap | 1.27−0.49 | 0.78 mm |
| Sum of two projected adjacent-lead gaps | 2(1.27−0.49) | 1.56 mm |

Open rule question (no applicable text on file): how the intervening
conductive spacer pin and its pad are treated — for clearance (air path)
and creepage (surface path) separately. "Unconnected" alone does not
answer it, and the spacer may not be assumed at half endpoint voltage.
Until the measurement rule is established, none of the rows above is the
pair's creepage or clearance, including 0.78 mm. An earlier revision's use
of 0.78 mm as the complete pair creepage (→ "short ~8×") is retracted, as
is the asymmetric treatment (endpoint separation for clearance, single
adjacent gap for creepage).

Observation, not a verdict: the endpoint copper separation (1.94 mm) is
below the Table 18 values in §5 under every treatment that does not find
additional path length beyond it. Only extra surface path (package/solder),
a different classification, or an applicable alternative route could
relieve — each unestablished.

## 2. Pin functions and contract nets

From NXP TEA2209T §7.2 Table 3 (p.4) and
`zapote/packages/zapote-erc/src/power_entry_active.rs`:

| Pair | Pins | Functions | Copper nets (net vs reference node) |
|---|---|---|---|
| 3–5 | GATEHL / GATELL | high-side / low-side left gate drivers | `gatehl` (gate copper; source-referenced to L) / `gatell` |
| 10–12 | GATELR / R | right low-side gate / upper-right MOSFET source (mains input) | `gatelr` (gate copper; source-referenced to rectifier negative) / `RECTIFIER_R` |
| 14–16 | GATEHR / VR | right high-side gate / rectified mains voltage | `gatehr` (gate copper; source-referenced to R) / `RECTIFIER_POSITIVE` |

Between each pair sits an HVS pin (4/11/15): "high-voltage spacer; not to be
connected", plus COMP (pin 9) left open. The four NCs are enforced present,
unique, and unconnected by the Rust binding (6 native-binding tests pass).
"High-voltage spacer" is a pin description, not a board-level clearance,
creepage, or acceptance criterion.

## 3. Rail connection established from the compiled manifest (corrects §5's inputs)

`candidate/source-manifest.json` bridge nets (49 groups, compiled from
`elec/src/power_entry_active_unit.ato`):

- `RECTIFIER_POSITIVE`: U8.1 (l_boost.1), U57.2, U55.2, U1.16 (bridge.16/VR).
- `a1`: U10.1, U10.3, U9.2, U8.2. `BOOST_DIODE_POSITIVE`: U40.1, U66.1, U10.2.
- `PFC_BUS_PLUS_390V`: U20.1, U66.2, U36–39.1, U52.1, U53.1.

Pin 16 (VR) sits on `RECTIFIER_POSITIVE` — the inductor's bridge-side
terminal, i.e. the **pre-boost rectified-mains node** — not on the 390–400 V
bulk bus. The bus energy figure (179.24 J nominal) describes a different,
downstream net and was wrongly substituted onto pin 16 in the prior
revision. The 408 V RMS / 560 V peak model is retracted in full.

Corrected differentials at declared 120 V mains (reviewer's derivation,
accepted): with the bridge DC-negative node as reference, V_R(t) and V_VR(t)
give V_VR − V_R = max[v(t),0] — a half-wave of ≈84.9 V RMS, ≈169.7 V peak
for pair 14–16, plus the gate-drive waveform. Pairs 3–5/10–12 see
≈120 V RMS (≈184 V peak with offsets). All three pairs fall in the same
Table 18 working-voltage band (>50–125 V); the >400–500 V row previously
assigned to pair 14–16 is withdrawn.

## 4. Electrical facts retained (with limits distinguished)

- TEA limiting values, §9 Table 6 (pp.8–9, vs pin 7/GND): L, R, and the
  high-side gate outputs −5…+440 V operating; **VR, VCCHL, VCCHR −0.4…+440 V
  operating** (corrected: not −5 V); all listed pins −5…+700 V mains
  transient (10 min/lifetime cumulative). Terminal survival limits — not
  insulation-coordination inputs.
- TEA §12 (p.12): mains transients/surges must be held below 700 V on
  VR/L/R. No PCB-layout, clearance, or creepage figure anywhere in the
  19-page datasheet (retained PDF SHA
  `fb611299c890a0dcaf7d610ed3fe742a3ab8debf21a75b540b8cede2e7badc99`,
  `active-rectifier/sources/manifest.json`).
- Declared by owner 2026-09-19: **120 V mains**. Nominal bus 390–400 VDC
  (tolerance/Vmax/T excluded).
- Campaign surge assumption: 1 kV L–L / 2 kV L–PE with MOV clamp ~400 V —
  LA-series curve UNVERIFIED (HTTP 403 capture failure retained,
  `AR-VERIFY/attempt-001/raw/capture_failures.json`). Withheld from any
  argument that would rely on the clamp, including clearance.

## 5. Applicable clauses (retained transcriptions, cited by path)

- `docs/evidence/2026-07-28-creepage-determination-brainstorm.md` §3.1–3.2:
  Table 15 (rated voltage + OVC → impulse; 120 V row ii, OVC II → 1500 V),
  Table 16 (impulse → clearance {0.5…11.0}, interpolation Note 1),
  29.1 (+0.5 mm soldered construction ≥1500 V), 29.1.5 (V_det for
  above-rated working voltages), Table 15 Note 2 (raise for generated
  overvoltages). **This 0.5 mm adder IS included wherever a clearance
  figure below is stated.**
- `docs/evidence/2026-08-12-hv-hv-creepage-determination.md` §3.1: Table 18
  functional creepage transcribed in full; 29.2.4 binds functional
  insulation to Table 18 with a clause-19-test exemption (test unrun;
  exemption therefore unavailable today).
- PD3 default for cooking appliances, IIIa/IIIb absent CTI data: cited in
  the hv-hv determination and `docs/evidence/2026-08-11-pd2-decision-record.md`;
  no enclosure record earns PD2 for this open prototype. Provisional
  screening assumptions, distinguished from established requirements.

Gaps in the chain (needed for an outside reviewer to reproduce; not on file):
standard edition and amendments (retained text is IS 302-1:2008, i.e.
IEC 60335-1 Ed. 4.2-era; current IEC 60335-1:2020 + applicable Part 2 such
as 60335-2-6 unrecovered), the measurement rule for intervening conductors
(§1), the governing functional-clearance provision with complete
calculation, and the full conditions of the 29.2.4/Clause 19 route. The
2.2 mm figure below is therefore a **reported table value**, not an
independently confirmed requirement for this assembly.

## 6. Requirement vs available (corrected determination input)

All three pairs at ≈85–120 V RMS working → Table 18 band >50–125 V →
**2.2 mm at PD3/IIIa–IIIb** (reported value, per §5 caveats). Against this,
candidate path components from §1 (endpoint copper 1.94 mm; adjacent-gap
sums 1.34/1.56 mm) all fall short — but the evaluated physical path is
undetermined pending the §1 measurement rule and the §4 assembly geometry,
so no deficit factor is stated.

Clearance cross-check (conditional, not a pass): 29.1.5 on corrected peaks
gives V_det ≈ 1514 V (pairs 1–2) and ≈1870 V (pair 3) → Table 16
≈0.5–0.9, **plus the 0.5 mm soldered-construction adder** → ≈1.0–1.4 mm
basic vs 1.94 mm copper. This remains conditional on Table 16 applying to
functional separations (unestablished), the 1500 V rating surviving Note 2
(unverified clamp), altitude/material treatment (unstated), and corrected
peak assumptions — it is shown for completeness, not as a pass.

## 7. Analysis trail (superseded reasoning preserved, marked)

- `evidence/rust-integration-01/` — original 12-spacing/8-current findings;
  both failed/intermediate runs retained with warnings intact.
- `evidence/vsense-bank-side-01/tea-insulation-analysis.md` — first pass
  (retained, challenged): no relieving clause on file, floor stands.
  Status: superseded by the §3 correction, kept for the trail.
- `evidence/vsense-bank-side-01/tea-determination.md` — second pass
  (retained, challenged): clearance passes / creepage fails 3–8×. Status:
  withdrawn insofar as it rests on the retracted 408 V model and the 0.78 mm
  verdict; its Table 18 identification and assumption bookkeeping stand.
- Hypothesis (not evidence): the clause-19 exemption route is available and
  may be winnable; the evidence for that is the applicable exception text,
  a proposed test basis, and an eventual result — none yet in hand.

## 8. Owner determination (recorded verbatim in substance)

Determination withheld pending correction of the electrical-stress model
and insulation-path assessment. The retained CAD reportedly provides
1.94 mm endpoint copper across the three HVS-separated pairs; this is not
yet an assembled clearance or creepage determination. Disposition requires
corrected pairwise stresses and geometry, then either demonstrated
dimensional compliance or a completed applicable alternative route. No
controller replacement is committed on the strength of the withdrawn
argument. First checks ordered: pin-16 rail connection — answered in §3
(pre-boost node, not the bus) — and the full insulation-path evaluation
around the spacer metal — open (§1 rule question, §4 assembly geometry).

## 9. Revision scope

This assessment applies to the identified design revision (board
`e274d8ad1181f426f731f170e46202e16f969bb751538837a45ee221c3b09ceb`,
schematic `f0b3682aa653ae900c78f9e3d8f3edfd0f7fd2d4496199e781a797489e80e6f8`)
and the documented component, material, assembly, and operating assumptions
above. Changes require an impact review and revalidation of affected claims;
textual edits that alter no assumption do not.

## 10. Supplement: primary-text recovery from IS 302-1:2008 (agent, 2026-09-19)

Fetched the BIS RTI text cited by the repo's hv-hv determination; SHA-256
matches the cited artifact byte-for-byte
(`2695a4bc1b2c87dd24a6126d984d01ad30be53c8d905ff196b73241b73f99251`,
312769 bytes). Read first-hand, not via the repo's transcription:

- **29.1.4**: "For functional insulation, the values of Table 16 are
  applicable. However, clearances are not specified if the appliance
  complies with 19 with the functional insulation short-circuited." The
  governing functional-clearance provision is now on file; the §5 gap is
  closed. Lacquered winding conductors count as bare (not relevant here).
- **Annex L**: at PD3, clearances for basic AND functional insulation are
  measured against Table 16 (no impulse-test reduction); Table 18 governs
  functional creepage. Confirms the Table 16 functional route used in §6.
- **Fig. 12 note pattern**: where a spanning clearance meets the higher
  requirement, sub-segment clearances of lesser insulation are not measured
  — the spanning treatment for clearance has textual support (analogous
  construction, not this exact geometry).
- **Clearance result**: required ≈1.0–1.4 mm basic (29.1.5 on corrected
  peaks ≈1514/1870 V, interpolation Note 1, +0.5 mm solder adder included)
  vs 1.94 mm span → PASSES, subject to Table 15 Note 2 (generated
  overvoltages; clamp unverified, Q3) and altitude (unrecorded).
- **29.2 creepage measurement is delegated**: "The way in which creepage
  distances are measured is specified in IS 15382 (Part 1)" (= IEC 60664-1),
  which is not recovered anywhere in this repository. The spacer-metal
  creepage rule is therefore still genuinely open — confirmed, not resolved.
- **PD is now the hinge**: 29.2 applies PD2 *unless* conductive pollution
  (→PD3). At >50–125 V / IIIa-IIIb, Table 18 reads 1.4 mm (PD2) vs 2.2 mm
  (PD3) — the 1.94 mm endpoint span passes one and fails the other. The
  repo's PD3 default rests on the cooking-appliance installed environment;
  an open bench prototype has no enclosure record either way. Determining
  PD for the assessed configuration may determine the verdict by itself.
- 2 N force applies to bare conductors when measuring (assembly-position
  caveat retained alongside §1). A force is applied to try to reduce
  creepage — measured paths assume worst-case positions.
