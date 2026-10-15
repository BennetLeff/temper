# Return-current rules (native-21)

This page lists the rules that govern return current on the native-21 power-stage board. For each rule it gives
the reason and what enforces it. The rules come from `DECISIONS.md` entries, review findings and gate docstrings;
this page collects them and does not add new ones. When a rule changes, edit the gate first, then record the
change in `DECISIONS.md` and here.

**Enforcement levels used below:**

- **Gate:** fails `native-21/layout/gates/chain.sh` (run under `set -e` / `pipefail`), or is a hard gate in
  `scorecard.py`, where a failing board is not a candidate.
- **Metric:** a `scorecard.py` performance figure. It is ratcheted against the benchmark but does not block a board.
- **Analysis:** a study run outside the chain; its result is carried as a constant or a decision.
- **Placement:** fixed in `tools/floorplan.py` / `native-21/layout/place.py`, with no geometric check.

All limits are native-21 acceptance values from the stage reviews. None of them is a manufacturer number or a
general standard; datasheets say "as close as possible".

## 1. Power commutation loop

| # | Rule | Why | Enforced by |
|---|---|---|---|
| P1 | BUS_P and HV_RET are a plane pair on In2 / In1, across the 0.5 mm core (`native-21/stackup.json` `plane_roles`). | Where both planes overlap, the return mirrors the forward current, so loop inductance is µ0·h per square. | **Analysis.** `stackup.json` is the single source for layer roles (`layers21.PLANE_ROLE`). `validation-results/11-candidates/g02-g03-power-path/scripts/plane_l.py` screens the overlap (±50 %, no via or ESL terms). No gate checks plane overlap or necks. |
| P2 | Each leg has its own HF film pair (C38/C39 leg A, C40/C41 leg B) beside the FETs, alongside the C5/C6 bulk film. | Keeps the high-di/dt commutation loop local to each leg. | **Analysis.** The FEM-extracted loop matrices feed the switching decision matrix. Acceptance means every case stays inside die VDS limits; there is no nH limit. Native-21 measured 37.6 nH (native-19: 24.9 nH) and passed 252/252 cases (`DECISIONS.md`, 2026-10-08 power-loop entry; `validation-results/01-switching-parasitics/`). Not in the chain. **Open: S3** (the matrices come from board `76ec8cca`, not the current board). |
| P3 | The gate series resistor, the hold-off resistor and the F6 network (Cgs, PMEG + 1 Ω) sit directly under each gate pin. Driver VDD–VSS cap stacks straddle each output pin (2.07–2.2 mm loops, no vias). | Short gate loops; Infineon gate-loop guidance. This is why the HF film row moved 6 mm away from the FETs (cost: P2's +51 %). | **Placement** (`tools/floorplan.py`, `place.py`). The gate loops are included in the FEM extraction (P2). |

## 2. Shunt and Kelvin topology

| # | Rule | Why | Enforced by |
|---|---|---|---|
| S1 | Every bus-side return lands on **HV_RET, never LEG_RET**: bulk C5/C6, HF C38–C41, BR1 minus, the TVS string, the bleed resistor and R5 pad 4. Only the low-side sources land on LEG_RET (R5 pad 1). R5 is the only path between the two nets. | A return on LEG_RET would let shoot-through or rectifier current bypass R5 and blind the DC overcurrent comparator. | **Gate.** `audit.rs` requires the exact `hv_ret` membership (scorecard `audit_rs`). Mutation tests move each HF cap and BR1 to `leg_ret` and require a failure (`local_bus_capacitor_cannot_bypass_shunt`, `rectifier_feeds_bus_and_returns_on_the_capacitor_side_of_the_shunt`). On copper, scorecard `drc_errors_0` / `drc_unconnected_0` / `drc_parity_0` catch a short or bypass. |
| S2 | OCP sense is taken only from R5's Kelvin fingers (pads 2 / 3, CSS2H Kelvin land, net-tied in the footprint). It leaves as a tight pair, and the HOT protection block returns in a star to R5.2. There is one Kelvin path, so there is no Kelvin loop. | DC current returned through the Kelvin copper shifts the OCP trip point. | **Gate** for the footprint (`audit.rs`). **Gate** for the floor: `validation-results/02-protection-timing/kelvin/kelvin_plane.py` and `kelvin_budget.py` compute the shift and band, and scorecard `kelvin_floor` requires `meets_floor_at_bound` and a floor of at least 64.17 A (`KELVIN_FLOOR_MIN_A`). The second condition catches `kelvin_budget.py`'s silent 44 A fallback for a tag missing from its `FLOOR` table. `kelvin_band_low_A` is also a **Metric**. |

## 3. Fast-signal reference planes

`native-21/layout/gates/return_path19.py`, a **Gate** (scorecard `return_path19`). It walks every fast signal in
0.25 mm steps and finds the nearest adjacent poured layer (`layers21.ADJ`). The acceptable return nets for each
signal are:

| Signal group | Acceptable return |
|---|---|
| bus_fault_hot, ocp_ok_hot, hot5_ok_hot, ovp_ok_hot | `ocp_kelvin_p` |
| pwm_ha / hb / la / lb, ct_zc, permit, bus_fault*, bias_good, line_zc, hb_rx, hsb_good | `v3v3` / `selv_gnd` |
| mon_good_ha, mon_good_hb, monitor_ls-good | `n_ls` / `hv_ret` / `leg_ret` |

| # | Rule | Limit (`return_path19.py` constant) | Applies to |
|---|---|---|---|
| R1 | Every sample has the right reference plane under it, or a coupled return track beside it (same layer, edge gap ≤ 0.3 mm) or over / under it (≤ 0.5 mm). | `COPLANAR_GAP`, `BROADSIDE_GAP` | Asserted for `ASSERT_PLANE`: bus_fault_hot, pwm_ha/hb/la/lb, ct_zc |
| R2 | No unreferenced run longer than 1.5 mm. Antipads and pour edges are allowed up to that length; points within 0.6 mm of the signal's own pads and vias are skipped. | `MAX_GAP` 1.5, `SKIP` 0.6 | Same |
| R3 | Each reference change at a via has a populated cap joining the two reference nets within 3.0 mm. A same-net change has a stitching via within 3.0 mm; a farther stitch counts as open. | `TRANSFER_MM` 3.0 | Asserted for ct_zc and the four PWM inputs |
| R4 | Limit the number of layer changes. | `MAX_TRANSITIONS`: pwm_hb 7, ct_zc 1 | — |
| R5 | Each dedicated transfer cap reaches both planes through its own via within 1.6 mm of each pad. | `XFER_CAPS`, `XFER_VIA_MM` 1.6 | C153–C156 (stage 19b), C169–C175 (stage 44) |

The other listed signals are **reported, not asserted**: they change state only at start, stop or on a fault, and
any disturbance can only disable the drivers. Their open changes add up to `return_path_open_changes`, a **Metric**
with target 0 (**open: S10**).

## 4. Local decoupling

| # | Rule | Limit | Enforced by |
|---|---|---|---|
| D1 | Each comparator, Schmitt buffer, rail monitor and isolator has its own 100 nF cap between its supply and return pins. A plane-backed cap pad needs a same-net via that lands in a filled pour of that net. | Set per IC in `CHECKS` (16 rows): supply pad 2.0 mm for most ICs, up to 4.5 mm where the note gives the reason (dense HOT block, board edge). Return pad 3.0–6.0 mm, or a plane via instead. Plane via 3.0–6.5 mm. | **Gate** `native-21/layout/gates/bypass_check.py` (`regate.sh`, scorecard `bypass`) |
| D2 | Converter and LDO caps sit at their power pins (RECOM R24C2T25 p.13, TI SBVS204 §9.1). | Supply side ≤ 3.0 mm; 100 nF VOUT− side ≤ 3.0 mm | **Gate** `validation-results/08-manufacturing-package/native-21/stage19-pi-si/pi_distances19.py` (scorecard `pi_distances`) |

Both gates measure straight-line distances between pad centres. That is a lower bound on the copper loop, not an
inductance figure.

## 5. Plane boundaries

| # | Rule | Enforced by |
|---|---|---|
| B1 | No two different-net pours on one layer contest copper at the same priority. Each contested pair has a named winner in `patches21.ZONE_WINNERS`. | **Gate** `native-21/layout/gates/zone_priority_gate.py` (first step of `chain.sh`). Before stage 17b, KiCad's fill order decided an In1 n_ls / Kelvin boundary. |
| B2 | Each net's reference plane lives on the inner layer `stackup.json` assigns it. The LS rails and the Kelvin pair run along the lower edge of the core plane, not across the switching loop (`native-21/FLOORPLAN.md`). | **Placement**, with `plane_roles` as the source. |

## 6. Sense-loop area under the coil

| # | Rule | Enforced by |
|---|---|---|
| L1 | Keep the Kelvin, CT and LINE_ZC loops small: the coil field is 140–640 µT at 31 kHz, and OCP gain is about 1 A per mV. | **Analysis**, run once on stage-13b copper (`validation-results/02-protection-timing/coil-pickup/PICKUP.md`; `DECISIONS.md` item 9): Kelvin pair 214 mm², at most 3.0 A pickup stack. That 3.0 A is a constant inside the 64.17 A Kelvin floor; it is not re-measured on each board. Re-spin option: route KELVIN_N's last 30 mm on In2 under the KELVIN_P pour (−56 % EMF). |

## 7. Not enforced today

- **The commutation loop (P2).** The FEM runs on the remote box, not in the chain, and the current board has no
  extraction yet (S3).
- **Plane-pair continuity (P1).** Only the `plane_l.py` screen covers it; no gate catches a neck or cut in the
  BUS_P / HV_RET overlap.
- **Sense-loop pickup (L1).** It was analysed once, and the result is carried as a constant.
- **Reported fast signals (§3).** Their open changes are a metric, not a gate (S10).
