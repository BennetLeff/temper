# PFC experiment campaign — coordinator closeout

Date: 2026-09-17
Campaign: `2026-09-17-pfc-campaign`
Evidence commit: `a975fff03e5599d805d19da3788e9e756d6b809d`
Contract: `runs/contract-C1.1.json` sha256
`0accd9bc55afbf875b08ed4dcdd8b7bbaf009d6f6fd1824f6b03c58797a825d6`
Status: **closed on the no-bench path.** One measurement remains; it is scoped
in [PHYSICAL-TEST-PLAN.md](PHYSICAL-TEST-PLAN.md) and is **not authorized** by
this campaign.

This campaign ran the corrected wave, not the original 26-task plan. The
original plan's ordering was invalidated by measurement before fan-out; the
reasons are recorded here and in the plan's coordinator status update.

## 1. The answer

**The cooker PFC's heat is concentrated in two components, and the model this
campaign was built on overstates its dominant term by about 30%.**

Known loss subtotal at C1 nominal (120 V, 400 V bus, 1796.31 W requested):

| Term | Analytic model | Independent vendor model | Evidence class |
| --- | ---: | ---: | --- |
| Boost switch + gate | 45.50 W | **~34.6 W @25 C** | independent device *model*, not measured |
| Input bridge (GBJ2510-F) | 28.30 W | — | source-bound, one datasheet test point |
| Boost inductor, DC only | 4.50 W | — | source-bound |
| Shunt + reference | 2.27 W | — | source-bound |
| Relay + bleeders + divider | 1.16 W | — | source-bound |
| **Known subtotal** | **81.73 W** | **~70.8 W** | ~95.5% / ~96.0% before unknown terms |

The switch and the bridge together are ~89% of the known subtotal. Every other
term is small, or unknown and unquantified.

## 2. Findings that changed the plan

1. **The six-task frequency sweep is degenerate.** In
   `zapote-erc::pfc_currents` every current moment depends only on the product
   `L*f`. Holding `L*f` fixed leaves Pin and every current moment bit-identical
   and moves only the f-proportional terms, so the sweep is strictly monotone
   with its minimum at the lowest frequency. Measured
   (`tests/frequency_lf_axis_probe.rs`, `F-AXIS/`): total switch/gate loss
   15.55 W (30 kHz) to 60.88 W (180 kHz), Pin 1796.3100 W and I_sw_rms
   11.99950 W at every point. The sweep was never going to find an interior
   optimum.
2. **G0 as specified duplicated an existing solver.** The required
   matched-power true-RMS inversion already existed as
   `pfc_candidates::LineModel`. G0 was implemented as a parameterization of it
   plus a campaign binding, and reproduces the retained control exactly
   (45.502337 W). See `G0.md`.
3. **The device axis is source-gated.** All three K-* datasheets were captured
   and hashed; none publishes Eon/Eoff, two of three omit the Miller plateau,
   and the gate biases (10 V, 18 V) do not match C1's 12 V.
4. **No external per-device anchor was available from either reference.**
   B-TI and B-INF both returned INSUFFICIENT_EVIDENCE and convergently named
   the same missing observation: a device-level clamped-inductive capture.
5. **The one external reference obtained did not falsify the model.**
   B-INF's board is a measured 2.5 kW single-switch boost using IPZ60R040C7;
   at the gate resistance tied to its measured data (3.3 ohm) the model's
   switch-only loss is 30-35% of the board's whole-board loss, which is
   consistent. `B-INF-GATE` established the populated gate element is the
   R9/R16 trimmer and that the previously reported "10 ohm" gate resistance was
   a misattribution.
6. **The dominant term is contradicted by an independent vendor model.**
   `N-DPT` ran a clamped-inductive double pulse in ngspice with Infineon's
   vendor CoolMOS C7 models. For the baseline IPW65R045C7, `(Eon+Eoff)*f` =
   26.76 W at 25 C against the analytic 37.3682 W overlap: **ratio 0.72**
   (0.68 at 125 C). `N-DPT-ST` reproduced the control at 26.7615 W (ratio
   1.0001, `.meas` lines byte-identical), so the result is reproducible.
   Convergence was shown by 10x timestep refinement, and a DC Rds(on) control
   reproduced the datasheet (43.4/102.0 mOhm vs 45/~99 mOhm).
7. **The frequency trade dies on magnetic evidence regardless.** M065/M090
   found real candidates (760801202 at 65 kHz, 760801403 at 90 kHz) but
   `M-CORE` could not bound core+AC loss in either direction: the core material
   and geometry are unpublished. Both candidates need forced air at 15 A rms,
   and the retained baseline choke's real inductance at bias is ~160 uH rather
   than the 180 uH that C1 and the whole `L*f` rule assume.
8. **The largest claimed lever is unverifiable no-bench.** The analytic model
   says the board part STW65N65DM2AG costs 2.05x the C7 on switching (93.183 W
   vs 45.5023 W). Its vendor model is unpublished-reachable and its datasheet
   carries no Eon/Eoff. Only a measurement settles it.

## 3. Task and attempt census

Dispatched and completed (13 attempts, all manifests re-verified against bytes
on disk):

| Task | Kind | Outcome | Evidence class |
| --- | --- | --- | --- |
| G0 | infrastructure | corrected adapter implemented, baseline parity | accepted |
| R0 | verification | 120 V control = 45.502337 W; 108 V derated to 1617.01 W | accepted |
| F-AXIS | coordinator run | 6-point degeneracy table | accepted |
| K-SILICON | source | IPZ60R040C7 captured; all 6 model params at 0/+10 V | accepted, bias-gated |
| K-SIC15 | source | NTH4L060N065SC1 verified; plateau+Eoss absent | accepted, 2 nulls |
| K-SIC18 | source | IMZA65R048M1H captured; supports 18 V; plateau absent | accepted, 1 null |
| B-TI | reference | INSUFFICIENT_EVIDENCE | accepted (negative) |
| B-INF | reference | INSUFFICIENT_EVIDENCE + whole-board bound | accepted |
| B-INF-GATE | reference | gate network resolved: R9/R16, 3.3 ohm | accepted |
| M065 | source | 760801202 candidate; core/AC null | accepted, gap |
| M090 | source | 760801403 candidate; core/AC null; at Isat | accepted, gap |
| M-CORE | source+compute | UNKNOWN: material/geometry unpublished | accepted (negative) |
| N-DPT | independent model | C7 26.76 W; ratio 0.72 to analytic | accepted |
| N-DPT-ST | independent model | control reproduced; ST uncapturable | accepted (negative) |

Not dispatched, with reasons:

| Task(s) | Reason |
| --- | --- |
| F030, F045, F065, F090, F129, F180 | degenerate axis; F-AXIS supersedes |
| D12, D15, D-SPLIT | gate-drive axis is model-sensitive and the model is now known to be ~30% optimistic; do not rank through an uncalibrated term |
| A-INTERLEAVED, A-BRIDGELESS, A-TOTEM | screen-only, no numerical ranking; the bridge (L-BRIDGE) is the more certain first target |
| L-DIODE, L-AUX | lower value than L-BRIDGE; both remain open |
| X1, V0 | require a frozen shortlist that the campaign did not reach |

No result was rejected as INVALID evidence. Three negative results
(B-TI, B-INF, M-CORE) and one capture failure (N-DPT-ST) are retained as
findings, not failures.

## 4. Comparison groups

- **Group A — analytics/whole-board bound** (unequal conditions, bounded
  claim only): model switch-only loss vs B-INF's measured whole-board loss at
  the board's own operating points. Consistent at 3.3 ohm.
- **Group B — independent switching energy** (comparable): C7 and IPZ60R040C7
  vendor-model DPT at identical bus, gate network, currents, temperature.
  STW65N65DM2AG could not enter this group.
- **Group C — frequency** (not comparable): the six frequency points carry no
  independent information; the axis is a single monotone curve.

No cross-group ranking is asserted. Groups A and B use different devices,
lines and frequencies.

## 5. Uncertainty ledger

| Uncertainty | Magnitude | Can reverse a decision? |
| --- | --- | --- |
| Measured switching energy of the board part | unknown; model claims 2.05x the C7 | **yes** — the largest single lever |
| Analytic-vs-vendor switching model gap | ~30% (0.72x) | yes — invalidated the frequency axis |
| Carrier/core loss of any candidate choke | unbounded both ways | yes — decides the frequency axis |
| Bridge forward drop beyond one test point | 0.85-1.30 V band, ~28 W +/- a few W | no — the bridge stays dominant |
| Gate network on the reference board | 3.3 vs 20 ohm (as-shipped undocumented) | no — bound holds at the measured value |
| Thermal rejection capability | no contract; entirely unquantified | **yes** — "too hot" is unanswerable today |

## 6. Shortlist and recommendation

**Keep, in priority order:**

1. **The input bridge is the largest certain term (28.3 W).** It is
   source-bound, has a documented synchronous-rectification break-even
   (~62 mOhm per device), and does not depend on the contested switching model.
   It is the best-evidenced target in the campaign.
2. **The boost device swap is the largest lever but is unproven.** C7 vs the
   retained board part is worth ~48 W on the analytic model, ~33 W even after
   the 30% correction. One measurement settles it; see the test plan.
3. **The gate-drive axis (D12/D15/D-SPLIT) is not yet rankable** — it is the
   most model-sensitive axis in a model now known to be ~30% optimistic.
   Revisit only after the switching model is anchored.

**Drop:** the frequency axis (F030-F180) and, for now, the topology studies.
Neither can be ranked without first fixing the switching model.

## 7. What was not done

- No bench or powered operation of any kind.
- No production model, CAD or BOM change.
- No qualified candidate; `hardware_qualification = NOT_PERFORMED` everywhere.
- No whole-assembly total: `total_loss_w` and mass/volume/cost remain absent
  with explicit unknown terms.
- No thermal ranking: no ambient/cooling contract was frozen, so the stated
  motivation (heat) is not yet expressed as a temperature.

## 8. Reproduction

```bash
# G0 adapter + acceptance tests
cd zapote && cargo test -p zapote-harness --test pfc_campaign
# R0 control (must reproduce 45.502337 W at 120 V)
/Users/bennet/Desktop/temper/target-shared/debug/zapote-pfc-campaign \
  power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/R0/attempt-001/input.json
# degeneracy probe
cargo test -p zapote-harness --test frequency_lf_axis_probe -- --nocapture
# whole-board bound probe
cargo test -p zapote-harness --test reference_loss_bound_probe -- --nocapture
```

Every attempt directory carries `dispatch.json`, `inputs.json`, `result.json`,
`REPORT.md`, `raw/` and `manifest.json`. All manifests were re-verified against
the bytes on disk at the evidence commit above.
