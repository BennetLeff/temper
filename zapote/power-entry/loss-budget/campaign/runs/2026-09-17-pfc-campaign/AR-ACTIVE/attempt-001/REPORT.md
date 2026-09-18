# AR-ACTIVE attempt-001 — Is there a worthwhile active-rectifier opportunity?

Task ID: **AR-ACTIVE** · Attempt: **attempt-001** · Campaign: 2026-09-17-pfc-campaign
Kind: source_then_numerical (no solver, no model/CAD edit). Source revision `d2c0263702d6bcc6992d725d3fd9272c428833fb` (verified).

**Hypothesis / changed variable.** The retained screen's active-rectifier row is a
conduction-only delta over two *assumed* Rds values (50 mOhm 25 C max, 100 mOhm assumed
hot) and therefore cannot say whether an opportunity exists. The changed variable is a
*concrete* circuit plus real devices with *manufacturer hot* Rds(on). Governing relation
(from `zapote/power-entry/loss-budget/2026-09-17-rectifier-alternative-net-savings.md` §3):

```
P_saved = P_bridge - 450 * R_hot - P_additional
```

## 1. Circuit chosen

- **Topology:** four-MOSFET active (synchronous) full-bridge rectifier replacing the
  four-diode GBJ2510 at the PFC input; the downstream boost PFC is unchanged.
- **Controller:** **NXP TEA2209T/1** (SO16, SOT109-1), *TEA2209T Active bridge rectifier
  controller*, Rev. 1.1, 14 April 2021. It is purpose-built for exactly this function:
  full-wave drive of all four bridge MOSFETs, integrated HV level shifters, self-supplying
  from the rectified line, integrated X-capacitor discharge, D-S overvoltage protection,
  gate pull-down fail-off.
- **Devices conducting in the line path:** **2** — one high-side and one low-side MOSFET of
  the conducting diagonal pair. The two conducting diode drops are replaced by the Rds(on)
  of those two MOSFETs; body diodes conduct only at polarity handover and start-up.
- **Gate bias:** internally regulated VCC `Vregd` typ **10.7 V** (10.2–11.2), so a datasheet
  Rds(on) at VGS = 10 V is conservative. Zero-crossing comparator delay `td` = 0.55–2.5 us.

## 2. Candidate devices (all 600/650 V, all block the 400 V bus)

| ID | Order code | Mfr | Package | Pinout / Kelvin | V_DS class |
|---|---|---|---|---|---|
| C1 | **IPW60R017C7** | Infineon | PG-TO247-3 | G=1, D=2/tab, S=3; **no** Kelvin pin | 600 V |
| C2 | **NVHL040N60S5F** | onsemi | TO-247-3L | G-D-S; **no** Kelvin pin | 600 V |
| C3 | **STW65N65DM2AG** | ST | TO-247 | G=1, D=tab, S=3; **no** Kelvin pin | 650 V |

The bridge off-device blocks the reverse line voltage (about 170 V peak at 120 V RMS), so
600 V is generous; all three also exceed the requested 400 V reference (1.5x+ headroom).
No candidate has a Kelvin/source-sense pin (not needed at line-frequency switching).

## 3. Applicable HOT Rds(on) — per device, primary sources

| Candidate | 25 C typ / max | 100 C typ | 125 C typ | 150 C typ | Basis |
|---|---|---|---|---|---|
| C1 IPW60R017C7 | 15 / **17** mOhm | ~24.8 mOhm | ~29.3 mOhm | **33 mOhm** | 25 C and 150 C are **table** rows (VGS=10 V, ID=58.2 A, p.5); 100/125 C read from Diagram 8, p.8 |
| C2 NVHL040N60S5F | 32 / **40** mOhm | 55.6 mOhm | 66.1 mOhm | 77.8 mOhm | table p.2 (VGS=10 V, ID=29.5 A) x Figure 8 normalized curve (p.4): 1.74 / 2.07 / 2.43 |
| C3 STW65N65DM2AG | 42 / **50** mOhm | 72.7 mOhm | 86.1 mOhm | 98.7 mOhm | Table 5, p.4 (VGS=10 V, ID=30 A) x Figure 10 normalized curve (p.7): 1.73 / 2.05 / 2.35 |

C1 has an **explicit hot table row** (typ 33 mOhm at Tj = 150 C). C2 and C3 publish only
**typical** normalized curves; no hot maximum exists for any candidate. The 25 C *maximum*
was never used as a hot value, and nothing outside a manufacturer's plotted range was
extrapolated. Normalized curves are read 1.000 at 25 C in both C2 and C3 (calibration check).

## 4. P_additional (sourced where possible; unknowns are null, not zero)

| Term | Value | Evidence class |
|---|---|---|
| Controller supply + gate drive | ~**3 mW** (range 2–4 mW) | TEA2209T §2.1 p.2 (IC 2 mW) and §8.2 p.5 (~1 mW mains + ~1 mW gate charge) |
| Rail generation | **0** (justified) | TEA2209T self-supplies from pin VR; no separate aux rail |
| Current sensing | **0** (justified) | TEA2209T senses L/R polarity internally (+/-250 mV); existing boost sense unchanged |
| Dead time / body-diode conduction | **null**, upper bound <1e-4 W | bound from TEA2209T td + candidate V_SD; occurs near zero line current |
| Start-up inrush body-diode loss | **null** | unknown; not characterisable without bench work |
| EMI re-qualification / added filter | **null** | obligation, no sourceable number |
| Line-commutation reverse recovery | **null** | device-specific; C1's C7 body diode is slow (Qrr typ 18 uC, trr 630 ns, p.6) — a selection risk |

Sourced P_additional ≈ 0.003 W. No term was zero-filled: the two zeros are justified
topology facts, all others are explicit unknowns.

## 5. The comparison across the 23–35 W bridge bracket

Pre-additional break-even per device: **51.1 mOhm (23 W) … 62.9 mOhm (nominal) … 77.8 mOhm (35 W)**.

| Candidate (Tj) | R_hot | P_saved @23 W | @nominal | @35 W | Beats 51–78 mOhm? |
|---|---|---|---|---|---|
| C1 IPW60R017C7 (100 C) | 24.8 mOhm | **+11.8 W** | **+17.1 W** | **+23.8 W** | **YES, whole band** |
| C1 IPW60R017C7 (125 C) | 29.3 mOhm | **+9.8 W** | **+15.1 W** | **+21.8 W** | **YES, whole band** |
| C1 IPW60R017C7 (150 C) | 33.0 mOhm | **+8.1 W** | **+13.5 W** | **+20.1 W** | **YES, whole band** |
| C2 NVHL040N60S5F (100 C) | 55.6 mOhm | -2.0 W | +3.3 W | +10.0 W | inside band only |
| C2 NVHL040N60S5F (125 C) | 66.1 mOhm | -6.7 W | -1.4 W | +5.3 W | inside band only |
| C3 STW65N65DM2AG (100 C) | 72.7 mOhm | -9.7 W | -4.4 W | +2.3 W | edge of band |
| C3 STW65N65DM2AG (125 C) | 86.1 mOhm | -15.7 W | -10.4 W | -3.7 W | **no** |

**Answer: yes — one concrete device class beats the break-even across the entire bracket.**
A 600 V CoolMOS C7-class device (~25–33 mOhm hot, 100–150 C) driven by the TEA2209T saves
roughly **8–24 W** (nominal 13–17 W) before the unquantified P_additional terms, with
18–45 mOhm of margin. Mid-Rds 40–50 mOhm-class parts are marginal and Tj-dependent, and the
retained board part STW65N65DM2AG shows no opportunity. This **confirms the source note's
own §5 hypothesis**: a sufficiently favourable device makes precise bridge measurement
unnecessary for the yes/no decision.

**Uncertainty / missing assembly terms.** The comparison is source-bound and conduction-only.
No measured bridge drop (bracket still 23–35 W), no thermal solve (Tj assumed), no guaranteed
hot maximum, and P_additional beyond ~3 mW is unknown (EMI/recovery/inrush).

## 6. Checker result and unresolved findings

No checker was issued (`checker_revision_and_sha256: not_applicable`), so there is no checker
receipt. Unresolved: (a) real Tj; (b) guaranteed hot Rds maximum; (c) EMI/commutation/inrush
P_additional; (d) C1's slow C7 body diode may force a fast-body-diode device with higher Rds;
(e) all hot values are typical, so the C1 margin could shrink but not flip below the break-even.

## 7. Recommended next observation

Measure the operating junction temperature of the four bridge MOSFETs in the actual thermal
assembly. It is the input that resolves which candidate class is acceptable and the size of
the saving; the top-level opportunity answer is already robust without it.

## 8. Accounting

- Solver invocations: **0** (source + arithmetic only). Model/CAD edits: **0**. Bench work: none.
- Case counts: expected source tasks 1; attempted 1; valid 1; failed 0; unsupported 0; unrun 0.
- Primary sources used: **4 of 8** (NXP TEA2209T; Infineon IPW60R017C7; onsemi NVHL040N60S5F;
  ST STW65N65DM2AG). Capture failures: **1**, retained in `raw/capture_failures.json`
  (infineon.com served HTTP 202 / 0 bytes HTML; recovered from the infineon.cn manufacturer mirror).
- Wall time: ~10 minutes. Invocation count for the numerical work: 0.
- Touched files: only `.../AR-ACTIVE/attempt-001/` (raw/, inputs.json, result.json, REPORT.md,
  manifest.json). No commits, no stash.
- **Deadline outcome:** the machine clock read `2026-09-18T04:20:00Z` at handback against the
  dispatch deadline `2026-09-18T01:30:00Z`, i.e. the stated deadline was already past. The
  dispatch file itself was written `2026-09-17T22:11` local (= `2026-09-18T04:11Z`), which is
  *after* the stated deadline — the two fields appear mutually inconsistent. A **complete**
  (not partial) handback is delivered.

---

**The single most important missing input:** *the real operating junction temperature of the
bridge MOSFETs under the actual thermal path*, because it selects which datasheet hot Rds(on)
applies and is the only input that moves the mid-range candidates across the 51–78 mOhm
break-even (C2 goes from +3.3 W to -1.4 W nominal between 100 C and 125 C), while the
low-Rds candidate remains below the break-even even at its datasheet's 150 C value.
