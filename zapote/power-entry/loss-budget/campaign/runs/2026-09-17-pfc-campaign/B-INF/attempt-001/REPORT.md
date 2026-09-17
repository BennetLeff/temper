# B-INF report — Infineon EVAL_2.5KW_CCM_4PIN / AN201408 applicability

Task ID: **B-INF** · Attempt: **attempt-001** · Kind: source-only reference research
Campaign: 2026-09-17-pfc-campaign · Contract: C1
`3bf1125fe37e8df6a493449ec5edfa01082fdd9e40a8d5d724147b388737f183`
Base revision: `1e0d8132d66e16027bbe4f6b21844b2d208b87d2`

## 1. Question and changed variable

Which specific claims of the maintained PFC switching model can the independent
Infineon reference **EVAL_2.5KW_CCM_4PIN / AN201408** test? Actual changed
variable: **none** (source capture only; no circuit, model, solver or CAD edit).

## 2. Identity and capture result

| Role | File | Identity | SHA-256 | Bytes |
| --- | --- | --- | --- | --- |
| Application note / user guide | `raw/chipdip_appnote.pdf` | Infineon **AN_201408_PL11_027 Rev 1.2**, 2015-11-02, 31 pp. | `fdbed1c5…49ce` | 1,496,871 |
| Manufacturer slide deck | `raw/infineon_presentation.pdf` | Infineon 2.5 kW PFC eval board deck, 16 pp. | `b213daba…c78d` | 1,226,653 |

Both files verified `%PDF-1.5` before use. The application note was captured
from the `static.chipdip.ru` mirror; the deck came directly from `infineon.com`.
Two attempts failed and are retained as failure captures, never hashed as
documents:

- Mouser PDF URL → HTTP 200 but `text/html` (JS/consent wall), 13,897 B →
  `raw/mouser_appnote.html`.
- Guessed Infineon `dgdl` app-note URL → HTTP 404 `text/html`, 1,523,888 B →
  `raw/infineon_appnote_attempt_404.html`.

Full log incl. status/bytes/content-type: `raw/capture_log.txt`.

## 3. What the reference actually exposes

**Populated circuit (standard 4-pin setting).** Single-switch CCM boost PFC.
Controller `ICE3PCS01G` (IC3); isolated gate driver `1EDI60N12AF` (IC4, 6 A
headline, Out+/Out− joined); boost switch `IPZ60R040C7` (DUT1A, TO-247 4-pin,
×1); boost diode **MPN conflicts** (see §4); input rectifier **2× `GSIB2580` in
parallel** (GL1+GL2, schematic p.12); hand-wound choke **~600 µH at 100 kHz**
(2× Kool Mµ 77083A7, 64 turns); 5 mΩ shunt `R24`; 2× 560 µF bulk. No input
fuse. Board default switching frequency **65 kHz**, table tested at **100 kHz**.

**Measured operating points.** Only whole-board values are published —
`VIN, IIN, PIN, VOUT, IOUT, POUT, efficiency` in Table 3 (p.20) at 100 kHz and
a **60 °C heat-sink setpoint**. Representative rows:

| Row | VIN | IIN | PIN | VOUT | POUT | Eff |
| --- | --- | --- | --- | --- | --- | --- |
| 230 Vac full | 229.56 V | 11.178 A | 2561.5 W | 401.15 V | 2500.9 W | 97.63 % |
| 230 Vac ~1.8 kW | 229.72 V | 7.807 A | 1789.0 W | 401.24 V | 1753.2 W | 98.00 % |
| 85 Vac max | 84.31 V | 15.215 A | 1280.2 W | 401.34 V | 1197.6 W | 93.55 % |

Figures 12/13 add whole-board efficiency curves at 65/100 kHz and “3.3 Ω”.

**Waveform observability — decisive.** The document contains **no per-device
switching data**: no raw switching waveforms, no measured `Eon`/`Eoff`, no
per-device loss, no `Vgs`/`Vds`/`Id`, no event current, no junction temperature.
Figures 14–18 are conducted-EMI spectra; Figure 19 is a soft-start envelope.
Only whole-board efficiency is available. **Whole-board efficiency is not a
per-device `Eon`/`Eoff`.**

## 4. Source conflicts (excluded rows, with reasons)

- **Boost-diode MPN** — `IDH16G65C5` (§1.3 p.4, ref. 3, Fig 12/13 captions,
  deck p.5) vs `IDH16S65C5` (§3.2 p.7) vs `IDH12S65C5` (Figure 6 raster). Three
  values in one document; the populated part is not resolvable. Excluded.
- **Populated gate resistance** — `3.3 Ω` (Fig 12/13 captions) vs `20 Ω`
  (R9/R16 schematic) vs `10 Ω` (R7/R11 component list). Excluded.

## 5. Applicability table (model input → source or UNKNOWN)

Full table in `inputs.json` (`applicability_table`, 33 rows). Summary by the
maintained model surface (`zapote-erc::pfc_currents`, `::pfc_switching` +
`GatePath`, `::pfc_losses`):

| Model input | Reference provides | Status |
| --- | --- | --- |
| `bus_v` | 401.15–401.49 V | SOURCED |
| `switching_hz` | 65 kHz default / 100 kHz table | SOURCED |
| `line_rms_v` | 85 / 230 Vac | SOURCED, different lines |
| `inductance_h` | ~600 µH @100 kHz | SOURCED, different value |
| `rds_on_ohm`, `qg_c`, `qgd_c`, `coss_energy_j` | — | UNKNOWN (device datasheet, not this AN) |
| `turn_on/off_current_a`, `switch_rms_a` | — | UNKNOWN (no device waveform) |
| `gate_bias_v`, `gate_plateau_v` | — | UNKNOWN |
| `current_transfer_charge_c` | — | UNKNOWN |
| `external_gate_r_ohm` (+ path) | 3.3 / 10 / 20 Ω | SOURCE_CONFLICT |
| `intrinsic_gate_r_ohm`, `loop_inductance_h` | — | UNKNOWN |
| `driver_source/sink_peak_a` | 6 A headline | HEADLINE_ONLY |
| boost-diode Vf/Qc | identity conflict | SOURCE_CONFLICT |
| bridge Vf/slope, sharing | 2× GSIB2580 identity | IDENTITY_ONLY |
| inductor DCR/core/AC | core identity | IDENTITY_ONLY |
| `shunt` R | 0R005 | SOURCED |
| junction temperature | 60 °C heat-sink setpoint | UNKNOWN |
| ambient / installed airflow | fans named | PARTIAL |

## 6. Verdict — INSUFFICIENT_EVIDENCE (no matched switching-energy spec)

**This reference cannot test the overlap/switching-energy claim.** No matched
single-datum reference input specification exists because the model’s decisive
inputs (event currents, gate bias/plateau, current-transfer charge, device
charges/Rds, loop inductance, gate resistance, junction temperature) are absent
or conflicting, and there is no device-level energy to compare against. No
hidden parameter was fitted to make the published 97.6–98.0 % efficiency agree
with any model.

A *partial* matched identity does exist: the board’s switch is exactly the
`IPZ60R040C7` named in campaign task **K-SILICON**, with a whole-board
efficiency datum at 401 V / 100 kHz / 229.7 Vac / 1789 W in / 1753 W out
(98.00 %). That can anchor a future **whole-board efficiency consistency
check** for that device, but it is not device-level switching validation.

## 7. Accounting

Expected/attempted/valid/failed/unsupported/unrun = 0/0/0/2/0/0; the two
failures are document-capture failures. No solver invocation. All ledger terms
UNKNOWN (`result.json`); `total_loss_w`, efficiency and volume stay null.

## 8. Next observation

Find a device-level clamped-inductive switching capture (double-pulse or CCM
switching-energy figure) for `IPZ60R040C7` or baseline `IPW65R045C7` with stated
bus, event current, gate bias/resistance and temperature — that is the one
missing observation most likely to change the decision.

Files: `inputs.json`, `result.json`, `REPORT.md`, `manifest.json`, `raw/`.
