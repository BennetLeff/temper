# PFC experiment campaign — coordinator closeout

Date: 2026-09-17 (revised after audit)
Campaign: `2026-09-17-pfc-campaign`
Evidence commit: `217d78eb6` (this revision adds the audit)
Contract: `runs/contract-C1.1.json` sha256
`0accd9bc55afbf875b08ed4dcdd8b7bbaf009d6f6fd1824f6b03c58797a825d6`

**Status: evidence collection complete; design conclusions provisional.**

The no-bench evidence wave is finished. The design conclusions below are
provisional and explicitly **do not close the broader search**: the original
purpose — escaping the current architecture's local optimum — is still open.
See [LOSS-ACCOUNTING-AUDIT.md](LOSS-ACCOUNTING-AUDIT.md) for the corrected
accounting and Section 2's correction notice.

This revision fixes three errors in the first closeout: an Eoss double-count in
the headline number, a mis-framed model disagreement ("30% correction"), and an
over-broad recommendation to drop the frequency and topology axes.

## 1. The answer, provisionally

**The cooker PFC's known loss is concentrated in the boost switch and the input
bridge, and the two models disagree by ~1.45x on the switching term.** That
disagreement is a discrepancy under one tested condition — not a calibration —
and it is large enough that neither model should be used to rank candidates
until the switching term is measured.

At C1 nominal (120 V, 400 V bus, 1796.31 W requested):

| Term | Value | Evidence class |
| --- | ---: | --- |
| Boost switching (Eon+Eoff) | 25.50-26.76 W | independent device *model* |
| Boost conduction + gate | 6.62 W | analytic model |
| Input bridge (GBJ2510-F) | 28.30 W | source-bound, **one datasheet test point** |
| Boost inductor, DC only | 4.50 W | source-bound |
| Shunt + reference | 2.27 W | source-bound |
| Relay + bleeders + divider | 1.16 W | source-bound |
| **Analytic switch/gate subtotal** | **45.50 W** | analytic |

The two dominant terms are the switch and the bridge. The bridge is the largest
term **not challenged by any independent comparison**, and the more certain of
the two. Unknown terms (inductor core/AC, boost diode, capacitor ESR, EMI, PCB,
auxiliaries, cooling) remain explicit nulls; no whole-assembly total is
asserted.

## 2. Correction notice

Three items in the first closeout were wrong and are corrected here:

1. **Eoss was double-counted.** The DPT's `Eon` already includes the Coss
   discharge (N-DPT's own definition: `overlap-only = (Eon − Eoss + Eoff)·f`).
   The first closeout added the analytic `Eoss` (1.5106 W) again. The correct
   conditional switch/gate subtotal is **~33.38 W, not 34.64 W**.
2. **The disagreement was misframed as a "~30% correction".** The two models
   disagree by ~1.45x on the switching term (ratio 0.688 Eoss-inclusive, 0.683
   overlap-only). That is a discrepancy at the tested device and conditions — it
   is **not** a correction factor and must not be applied to anything else. It
   says nothing about the unmodeled ST device.
3. **The direction was misstated.** The analytic model predicts *more* loss than
   the independent model, so it is **pessimistic about efficiency**, not
   optimistic.

## 3. Findings

1. **The six-task frequency sweep is degenerate in the current model.** Every
   current moment depends only on `L*f`, so holding `L*f` fixed leaves Pin and
   all current moments bit-identical and moves only f-proportional terms; the
   sweep is strictly monotone with its minimum at the lowest frequency
   (`tests/frequency_lf_axis_probe.rs`, `F-AXIS/`). **What this shows is that
   the simplified model cannot discover the magnetic tradeoff — not that
   frequency is unimportant.** The sweep should have been encoded analytically
   at zero worker cost; it should not have consumed six agents. Frequency
   remains a design axis whose real evaluation needs a sourced choke's
   core/copper loss and volume.
2. **G0 as specified duplicated an existing solver.** The matched-power
   inversion already existed as `pfc_candidates::LineModel`; G0 parameterizes it
   and reproduces the retained control exactly (45.502337 W). See `G0.md`.
3. **The device axis is source-gated.** All three K-* datasheets were captured;
   none publishes Eon/Eoff, two of three omit the Miller plateau, and the gate
   biases (10 V, 18 V) do not match C1's 12 V.
4. **No external per-device anchor was available from either reference.** B-TI
   and B-INF both returned INSUFFICIENT_EVIDENCE and named the same missing
   observation.
5. **The one whole-board reference did not falsify the model.** At the gate
   resistance tied to its measured data (3.3 ohm) the model's switch-only loss
   is 30-35% of the B-INF board's whole-board loss — consistent.
   `B-INF-GATE` resolved the populated gate network (R9/R16 trimmer) and showed
   the previously reported "10 ohm" gate resistance was a misattribution.
6. **An independent vendor model disagrees on the switching term.** `N-DPT`
   (clamped-inductive double pulse, Infineon Level-0 vendor models in ngspice):
   IPW65R045C7 gives `(Eon+Eoff)*f` = 26.76 W at 25 C against the analytic
   37.3682 W overlap. `N-DPT-ST` reproduced the control exactly (26.7615 W,
   ratio 1.0001, `.meas` lines byte-identical). See the audit for the correct
   reading: a discrepancy, not a calibration.
7. **Frequency cannot be closed without a core-loss source, not because it is
   unimportant.** M065/M090 found real candidates (760801202 at 65 kHz,
   760801403 at 90 kHz); `M-CORE` could not bound their core+AC loss because the
   core material and geometry are unpublished. Both candidates need forced air
   at 15 A rms, and the baseline choke's real inductance at bias is ~160 uH
   rather than the 180 uH the `L*f` rule assumed.
8. **The board part is unverifiable no-bench.** STW65N65DM2AG's vendor model is
   unreachable and its datasheet carries no Eon/Eoff. Its analytic 2.05x
   switching ratio is unverified and cannot be checked without a measurement.

## 4. Task and attempt census

13 attempts, all manifests re-verified against bytes on disk:

| Task | Outcome | Evidence class |
| --- | --- | --- |
| G0 | corrected adapter; baseline parity 45.502337 W | accepted |
| R0 | 120 V control reproduced; 108 V derated to 1617.01 W | accepted |
| F-AXIS | 6-point degeneracy table | accepted |
| K-SILICON | IPZ60R040C7 captured; params at 0/+10 V | accepted, bias-gated |
| K-SIC15 | NTH4L060N065SC1 verified; plateau+Eoss absent | accepted, 2 nulls |
| K-SIC18 | IMZA65R048M1H captured; supports 18 V; plateau absent | accepted, 1 null |
| B-TI | INSUFFICIENT_EVIDENCE | accepted (negative) |
| B-INF | INSUFFICIENT_EVIDENCE + whole-board bound | accepted |
| B-INF-GATE | gate network resolved: R9/R16, 3.3 ohm | accepted |
| M065 | 760801202 candidate; core/AC null | accepted, gap |
| M090 | 760801403 candidate; core/AC null; at Isat | accepted, gap |
| M-CORE | UNKNOWN: material/geometry unpublished | accepted (negative) |
| N-DPT | C7 26.76 W; disagreement with analytic | accepted |
| N-DPT-ST | control reproduced; ST uncapturable | accepted (negative) |

Not dispatched. These are **deferred or re-scoped, not rejected**:

| Task(s) | Status |
| --- | --- |
| F030-F180 | superseded by the closed-form `F-AXIS` table; frequency stays a design axis |
| D12, D15, D-SPLIT | deferred until the switching model is anchored; not rankable through a term with an unresolved 1.45x disagreement |
| A-INTERLEAVED, A-BRIDGELESS, A-TOTEM | **open — resume**, these are the escape from the local optimum |
| L-BRIDGE | **open — next**, the largest unchallenged term |
| L-DIODE, L-AUX | open |
| X1, V0 | unchanged; require a frozen shortlist |

No result was rejected as INVALID evidence. Three negative results and one
capture failure are retained as findings.

## 5. Uncertainty ledger

| Uncertainty | Magnitude | Can reverse a decision? |
| --- | --- | --- |
| Measured switching energy (any device) | two models disagree by ~1.45x | **yes** |
| STW65N65DM2AG switching energy | no independent result exists | **yes** (largest claimed lever) |
| Bridge forward drop beyond one test point | 0.85-1.30 V band on a 28.3 W term | **possibly** — it is the largest unchallenged term |
| Carrier/core loss of any candidate choke | unbounded both ways | yes, for the frequency axis |
| Thermal rejection capability | no contract; entirely unquantified | **yes** — "too hot" is unanswerable today |
| Gate network on the reference board | 3.3 vs 20 ohm (as-shipped undocumented) | no — bound holds at the measured value |

## 6. Shortlist and next step

Evidence collection is complete; the design conclusions are provisional. The
recommended next step is to **resume the architecture screening that the
original plan intended**, not to close the search.

1. **Resume bridge/rectification architecture screening (next).** The bridge is
   the largest term not challenged by any independent comparison (28.30 W), it
   has a documented synchronous-rectification break-even (~62 mOhm/device), and
   it does not depend on the contested switching model. L-BRIDGE and the
   A-BRIDGELESS screen are the natural vehicles, and the switching measurement
   below is not a prerequisite for them.
2. **Keep the topology studies open.** A-INTERLEAVED, A-BRIDGELESS and A-TOTEM
   are the only tasks that can escape the current architecture's local optimum,
   which was the campaign's stated purpose. They must not be dropped for lack of
   a numerical ranking.
3. **Re-encode the frequency axis, don't drop it.** The switching half is
   closed-form and costs nothing; the open half is magnetic (core/copper loss,
   volume, thermal). It becomes rankable when a sourced choke's loss data
   exists.
4. **Treat the switching measurement as a parallel, separately authorized
   activity**, not the critical path — see
   [PHYSICAL-TEST-PLAN.md](PHYSICAL-TEST-PLAN.md). It settles the largest
   single uncertainty, but the bridge work does not wait on it.

## 7. What was not done

- No bench or powered operation of any kind.
- No production model, CAD or BOM change.
- No qualified candidate; `hardware_qualification = NOT_PERFORMED` everywhere.
- No whole-assembly total; no thermal ranking (no ambient/cooling contract).
- No independent verification of conduction, gate, bridge, inductor, or
  auxiliary terms.

## 8. Reproduction

```bash
cd zapote && cargo test -p zapote-harness --test pfc_campaign
/Users/bennet/Desktop/temper/target-shared/debug/zapote-pfc-campaign \
  power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/R0/attempt-001/input.json
cargo test -p zapote-harness --test frequency_lf_axis_probe -- --nocapture
cargo test -p zapote-harness --test reference_loss_bound_probe -- --nocapture
```

Every attempt directory carries `dispatch.json`, `inputs.json`, `result.json`,
`REPORT.md`, `raw/` and `manifest.json`. All manifests were re-verified against
the bytes on disk.
