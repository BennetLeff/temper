# Coordinator receipt — AR-ACTIVE attempt-001

Date: 2026-09-17
Attempt: `zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-ACTIVE/attempt-001/`
Verdict: **NOT COUNTED AS A VALIDATED RUN. Research retained as evidence.**

Written separately from the worker report; the worker report is not modified.

## 1. Admission failures

Two mechanical failures, both now enforced by
`zapote/tools/check_campaign_dispatch.py`:

```
$ python3 zapote/tools/check_campaign_dispatch.py dispatch .../AR-ACTIVE/attempt-001/dispatch.json
NOT ADMITTED: .../dispatch.json
  - expired dispatch: absolute_deadline_utc 2026-09-18T01:30:00+00:00 is not
    after the packet's issue time 2026-09-18T04:11:56+00:00

$ python3 zapote/tools/check_campaign_dispatch.py handback .../AR-ACTIVE/attempt-001
NOT COUNTED AS VALIDATED RUN: .../AR-ACTIVE/attempt-001
  - no checker was issued, so there is no machine receipt; the research is
    retained as evidence only
```

1. **Expired dispatch.** The packet was issued roughly 2.7 hours *after* its own
   `absolute_deadline_utc`. A packet cannot be issued after its deadline; the
   dispatch file's mtime is the checkable proxy for issue time.
2. **No checker receipt.** `checker_revision_and_sha256` was set
   `not_applicable`, so no machine receipt could exist. The attempt is therefore
   **not a validated harness run** and must not be counted in the campaign's run
   census. Its research value is real and is retained.

Per the campaign plan, a run admitted with an expired deadline or without a
checker is an admission failure, not a completion. The substantive findings are
still useful as **source research**, and are treated that way below.

## 2. Substantive qualifications on the retained claims

Three of the attempt's claims are unsupported as written. They are corrected
here; the underlying research is unchanged.

### 2.1 Gate bias — "a datasheet Rds(on) at VGS = 10 V is conservative" is unverified

The report cites the controller's internally regulated supply, `Vregd` typ
10.7 V (10.2-11.2 V), and concludes that VGS = 10 V resistance data is
conservative. `Vregd` is the **regulated supply**, not a guaranteed MOSFET
gate-source voltage throughout operation. High-side bootstrap drop and supply
discharge under load both reduce the voltage actually presented at the gate, so
the claim requires the actual VGS at the MOSFET to be established first.

**Status: unverified assumption.** It does not invalidate the candidate; it
removes a stated margin that was never established.

The report's separate conclusion that the controller's own consumption is
milliwatt-scale is supported by the NXP datasheet and is retained.

### 2.2 Reverse voltage — 187 V, not 170 V, and rating is not settled by line voltage

The report states the off-device blocks "about 170 V peak at 120 V RMS". The
contract's high line is 132 Vrms, whose peak is **186.7 V**, not 170 V.

More importantly, the **required device voltage rating is not settled by the
input line range alone**. Surge protection, switching transients and fault
conditions all bear on it, so "120 V-only operation" does not by itself
authorise a lower voltage class. Lower-voltage devices remain a legitimate
direction — but only against an explicit input/transient contract.

**Status: corrected figure; rating question left open pending that contract.**

### 2.3 Junction temperature is an outcome, not an assumption

The report concludes that "the C1 margin could shrink but not flip below the
break-even". That is a **withdrawn claim.** All hot resistance values in the
attempt are *typical*, taken from datasheet tables and normalized curves. They
support exploration; they cannot substantiate a bound on where the margin lands.

Tj is an **outcome to be calculated**: couple the device losses to a proposed
thermal assembly, then check the resulting temperature and, from it, the
resistance. Until that loop is closed, the device comparison is conditional on
an assumed temperature, not a result.

**Status: claim withdrawn. Tj moves to the next assignment as a computed output.**

## 3. What is retained

Retained as source research, with the qualifications above:

- The concrete circuit (four-MOSFET synchronous full-bridge) and controller
  (NXP TEA2209T/1), with the catch that the gate-bias check in 2.1 is pending.
- The exact candidate order codes, packages and 25 °C limits.
- The typical hot Rds(on) series for each candidate, as typical values.
- The observation that a favourable device could make precise bridge
  measurement unnecessary for the yes/no decision. This survives, because it
  rests on the 25 °C maxima (17 mOhm against a 51-78 mOhm band) and not on the
  typical hot series.
- The unknown list, including the slow body diode (Qrr 18 uC typ), EMI
  re-qualification and start-up inrush.

Not retained: the margin bound in 2.3, the "conservative" gate claim in 2.1, and
the 170 V figure in 2.2.

## 4. Next assignment

One complete active-rectifier design assessment: exact controller/MOSFET
circuit, gate-supply behaviour including the high-side bootstrap path, voltage
stresses against an explicit input/transient contract, commutation and start-up
losses, and a coupled thermal estimate that computes Tj rather than assuming
it. IPW60R017C7 is retained as the reference candidate; a lower-voltage
alternative is screened only against that explicit contract.
