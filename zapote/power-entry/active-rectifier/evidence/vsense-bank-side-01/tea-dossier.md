# TEA dossier: all retained evidence for the package-spacing determination

Compiled 2026-09-19 from committed bytes only. No new measurements, no new
claims. The reader's determination goes here: ___________________________.

## 1. The failing geometry (measured)

- U1 = TEA2209T/1, SOIC-16, 1.27 mm pitch. Footprint pads 1.95 × 0.60 mm
  (`candidate/candidate-libs/Package_SO.pretty/SOIC-16_3.9x9.9mm_P1.27mm.kicad_mod`).
- Skip-one copper edge gap = 2 × 1.27 − 0.60 = **1.94 mm**, confirmed in
  native extraction (`evidence/vsense-bank-side-01/native.json`, bridge pads
  F.Cu) and in the suite (`evidence/vsense-bank-side-01/common/power-entry.json`,
  `DRC.NATIVE.CLEARANCE_PROFILE` fails on `bridge.3 / bridge.5`,
  `bridge.14 / bridge.16`, `bridge.10 / bridge.12`).
- Estimated pin-to-pin surface path ≈ 1.27 − 0.49 ≈ **0.78 mm** (pitch minus
  TEA §13 max lead width `bp` 0.36–0.49; solder mask uncredited; package
  leads/solder meniscus unmeasured).

## 2. Pin functions and contract nets

From NXP TEA2209T §7.2 Table 3 (p.4) and
`zapote/packages/zapote-erc/src/power_entry_active.rs`:

| Pair | Pins | Functions | Contract nets |
|---|---|---|---|
| 3–5 | GATEHL / GATELL | high-side / low-side left gate drivers | `gatehl` (→RECTIFIER_L) / `gatell` |
| 10–12 | GATELR / R | right low-side gate / upper-right MOSFET source (mains input) | `gatelr` / `RECTIFIER_R` |
| 14–16 | GATEHR / VR | right high-side gate / rectified mains voltage | `gatehr` (→RECTIFIER_R) / `RECTIFIER_POSITIVE` |

Between each pair sits an HVS pin (4/11/15): "high-voltage spacer; not to be
connected", plus COMP (pin 9) left open. The four NCs are enforced present,
unique, and unconnected by the Rust binding (6 native-binding tests pass).

## 3. Electrical facts

- TEA limiting values, §9 Table 6 (pp.8–9, vs GND): HV pins (L/R/VR, both
  gates high-side, VCCHx) −5…+440 V operating, −5…+700 V mains transient
  (10 min/lifetime); low-side gates/VCC/COMP −0.4…+14 V; float differentials
  ≤14 V. These are terminal survival limits, not coordination inputs.
- TEA §12 (p.12): mains transients/surges must be held below 700 V on
  VR/L/R. No PCB-layout, clearance, or creepage figure anywhere in the
  19-page datasheet (retained PDF SHA
  `fb611299c890a0dcaf7d610ed3fe742a3ab8debf21a75b540b8cede2e7badc99`,
  `active-rectifier/sources/manifest.json`).
- Declared by owner 2026-09-19: **120 V mains**. Nominal bus 390–400 VDC
  (`CLOSEOUT.md` §2: 179.24 J at nominal 2240.47 µF; tolerance/Vmax/T excluded).
- Campaign surge assumption: 1 kV L–L / 2 kV L–PE with MOV clamp ~400 V —
  LA-series curve UNVERIFIED (HTTP 403 capture failure retained,
  `AR-VERIFY/attempt-001/raw/capture_failures.json`).
- Derived working differentials (120 V sine, 390 V bus): pairs 3–5/10–12
  ≈ 120 V RMS (≈184 V peak); pair 14–16 ≈ 408 V RMS (≈560 V peak).

## 4. Applicable clauses (retained transcriptions, cited by path)

- `docs/evidence/2026-07-28-creepage-determination-brainstorm.md` §3.1–3.2:
  Table 15 (rated voltage + OVC → impulse; 120 V row ii, OVC II → 1500 V),
  Table 16 (impulse → clearance {0.5…11.0}, interpolation Note 1),
  29.1 (+0.5 mm soldered construction ≥1500 V), 29.1.5 (V_det for
  above-rated working voltages), Table 15 Note 2 (raise for generated
  overvoltages).
- `docs/evidence/2026-08-12-hv-hv-creepage-determination.md` §3.1: Table 18
  functional creepage transcribed in full; 29.2.4 binds functional
  insulation to Table 18 with a clause-19-test exemption (unrun); Table 18
  ≡ Table 17 row-for-row above 500 V.
- PD3 default for cooking appliances, IIIa/IIIb absent CTI data: cited in
  the hv-hv determination and `docs/evidence/2026-08-11-pd2-decision-record.md`;
  no enclosure record earns PD2 for this open prototype.

## 5. Requirement vs available (the determination input)

| Pair | Working RMS | Table 18 PD3/III | Required creepage | Available surface |
|---|---|---|---|---|
| 3–5 | ~120 V | >50–125 → **2.2 mm** | ~0.78 mm | short ~3× |
| 10–12 | ~120 V | >50–125 → **2.2 mm** | ~0.78 mm | short ~3× |
| 14–16 | ~408 V | >400–500 → **6.3 mm** | ~0.78 mm | short ~8× |

Clearance cross-check (29.1.5, illustrative): V_det ≈ 1514 / 1890 V →
≈1.0–1.4 mm basic vs 1.94 mm copper (passes *if* Table 16 applied to
functional separations — unestablished — and *if* the 1500 V rating
survives Note 2 — unverified clamp).

## 6. Analysis trail (superseded reasoning preserved)

- `evidence/rust-integration-01/` — original 12-spacing/8-current findings,
  both failed/intermediate runs retained with warnings intact.
- `evidence/vsense-bank-side-01/tea-insulation-analysis.md` — first pass:
  no relieving clause on file, floor stands (clearance-framed).
- `evidence/vsense-bank-side-01/tea-determination.md` — corrected pass:
  clearance likely passes, creepage governs and fails.
- This dossier adds no verdict; it assembles the inputs for the owner's.

## 7. Open tracks (design decision, not analysis)

1. Different controller/package with compliant pin spacing.
2. Layout reclamation (slots, coating, barriers) — each needs its own
   clause basis, none on file.
3. Clause-19 exemption test with the functional insulation shorted
   (retained path, plausibly winnable per hv-hv §5, unearned).
4. Product-context challenge (rated mains, appliance class, environment) —
   decided 120 V above; remainder not declared.

Board/schematic bytes this dossier describes: PCB
`e274d8ad1181f426f731f170e46202e16f969bb751538837a45ee221c3b09ceb`,
schematic `f0b3682aa653ae900c78f9e3d8f3edfd0f7fd2d4496199e781a797489e80e6f8`
(`FREEZE.md`). Any byte change voids it.
