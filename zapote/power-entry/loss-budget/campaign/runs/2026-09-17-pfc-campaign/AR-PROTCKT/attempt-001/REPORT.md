# AR-PROTCKT attempt-001 — one concrete protection circuit (internal boost-switch-short + surge)

Task **AR-PROTCKT** · Attempt **attempt-001** · Campaign 2026-09-17-pfc-campaign · engineering_design.
Contract C1.1 `0accd9bc…a825d6`. Dispatch `source_revision` `c11915ae…` is a **direct ancestor**
of HEAD `025e2fa…` (coordinator checker/hardening commits + this dispatch). Source-only; no bench,
no procurement, no CAD/BOM edit, no solver, no commits.

**Result in one sentence.** One concrete arrangement is delivered and its new part is selected, but
**coordination is NOT demonstrated**: a series high-speed DC fuse interrupts the internal loop
*only if it clears*, and clearing at 400 Vdc for a capacitor-discharge pulse is not established.

## 1. The arrangement, and the named parts

The circuit is three named elements on three distinct loops:

| Ref | Part (manufacturer, order code) | Placement | Role | Rating source (for THIS application) |
|---|---|---|---|---|
| **F2** (new) | **FWP-50A14F** (Eaton / Cooper Bussmann), 14×51 mm ferrule | series in the DC bus between the U10 boost-diode cathode and the capacitor bank (`PFC_BUS_PLUS_390V`) | **interrupts the internal discharge loop** | Cooper Bussmann High Speed Fuses, Data Sheet 720025 (FWP 690V/700V 1–50 A): **800 Vdc**, 50 A, **50 kA @ 800 Vdc**, min melting I²t **200 A²s**, clearing I²t **1800 A²s** (`raw/fwp-1-50a.pdf`) |
| **U7** (existing) | **V150LA10AP** (Littelfuse) | across L–N | surge clamp (diverts, does not interrupt) | LA Series Rev VL 16/9/2024, p.2 + Figure 10, 14 mm parts (`raw/littelfuse_LA_series_*.pdf`, `…page7_14mm_vi.txt`, `figures/littelfuse-la-p7-07.png`) |
| **F1** (existing) | **Schurter 0034.3129**, 16 A time-lag | series in the line | line-fed loop interrupter | AR-FAULT coordinator receipt (secondary; primary Schurter datasheet not captured this attempt) |

**Why F2 is in the loop.** The internal discharge path is
`caps → shorted U10 → a1 → U9 → caps`. A series element in the bus between the capacitor bank
and the boost stage is on that path for every device state, so it opens the loop **irrespective of
whether U9 is healthy or failed short** — which is exactly why it is the right class of element for
the `U9` failed-short case (no gate command can open a shorted switch). Continuous duty is not the
sizing case: the bus average is ~4.49 A and the rectified peak ~7.05 A against a 50 A rating.

## 2. Explicit fault cases (device state changes the answer)

**(a) `U10` shorted, `U9` healthy — NOT interrupted as demonstrated.**
F2 is topologically in the loop and, under the illustrative pulse model, melts when the loop action
exceeds 200 A²s (loop R < 0.896 Ω). Alternatively a healthy `U9` can open the path — but **no
detection path exists**: the shunt U12 is *not* in this loop (one terminal only) and UCC28180D /
TEA2209T have no loop OCP. The detection/latency budget is therefore **unquantified**, and turn-off
is **not credited**. Required: an in-loop current sense plus a desaturating gate drive tripping
inside `U9`'s short-circuit SOA.

**(b) `U10` shorted, `U9` failed short — the key result.**
`U9` cannot be turned off. **F2 is the only element that can act**, and whether it clears is **not
demonstrated** (see §4–5). **If demonstrated clearing is required, no available part interrupts
case (b).**

**(c) Line-fed switch short with the bridge following — NOT interrupted as demonstrated.**
The loop is `mains → F1 → CMC → NTC/bypass → bridge → U8 → shorted U9 → U12 → bridge return`.
F1 is the only series element by topology, but its breaking capacity is **160 A at 250 VAC** and the
prospective line current is unestablished; coordination with the surviving bridge/switch SOA is not
shown. **F2 is not in this loop and does not help.**

**(d) Line surge — clamped, not interrupted.** U7 clamps L–N. The required clamp at the operating
surge current is **null** (the operating MOV current is not established; see §6). L–PE/common mode
is **not clamped**.

**(e) Faults the arrangement CANNOT interrupt:** the internal discharge if F2 does not clear; any
already-bolted short (no gate command opens a failed-short device); a crowbar alone (diverts, and
is not part of this arrangement); a line-fed fault below F1's clearing threshold; line-to-PE /
common-mode surge; and case (b) where demonstrated clearing is required.

## 3. Sizing from the pulse, not the average

Pulse waveform (assumed, illustrative): a **unidirectional decaying exponential**
`i(t) = (V0/R)·exp(−t/(R·C))`, V0 = 400 V, C = 2240.47 µF; action `∫i²dt = E/R`, E = **179.238 J**.
This model assumes an overdamped, non-inductive loop with a single lumped R. AR-PROTECT's receipt
explicitly warns that a *normal-device* resistance does not describe a destructive fault, so the
model is retained only for its conditional structure. **The prospective peak current and action
I²t are NOT established** and stay **null**. What is stated conditionally: F2 melts iff
`R_loop ≤ E / 200 A²s = 0.896 Ω`, and the prospective peak is within F2's 50 kA DC breaking capacity
iff `R_loop ≥ 400 V / 50 kA = 0.008 Ω`. The window `[0.008, 0.896] Ω` existing does not show
`R_loop` lies in it, and does not show clearing. Full table: `raw/compute_result.json`
(`raw/compute_ar_protckt.py`). **The ~4.5 A average is used for continuous duty only, never for
sizing the fault element.**

## 4. Coordinated clearing — NOT DEMONSTRATED

F2's DC voltage rating (800 Vdc) exceeds the 400 V bus and its DC breaking capacity is published.
But coordination is **not** shown because: (i) the prospective peak and action I²t are unknown;
(ii) the published clearing I²t (1800 A²s) is an **AC/inductive** figure at rated voltage, not a
400 Vdc capacitor-discharge figure; and (iii) the fuse's let-through is not compared against any
sourced withstand I²t for the capacitor bank or PCB copper. For the line-fed loop, F1's total
clearing at matching conditions is not established. Verdict: **coordination NOT demonstrated.**

## 5. MOV selection and the required clamp

**V150LA10AP** (existing U7) is named. The required clamp is **`V_clamp(I_MOV)` read from the
Littelfuse LA Series Transient V-I curve (Figure 10, 14 mm parts)** at the actual MOV surge
current, and must sit below the surviving devices' limits (600 V FET blocking; 440 V controller
operating). Because the operating MOV current is not established, the **required clamp is null**.
The datasheet's `VC = 395 V max at IPK = 50 A, 8/20 µs` is an **UPPER bound at 50 A only**; it
bounds **no other current in either direction** and must not be reversed into a lower bound. The
surge contract (IEC 61000-4-5, 1 kV L-L / 2 kV L-PE) is **PROVISIONAL/ASSUMED**, not adopted; a
committed requirement document plus a V-I value at the real MOV current would settle it. **A
line-surge MOV does not help the internal discharge loop** (its terminals are not on that loop).

## 6. Evidence ledger and checker results

`claims.json` (15 claims, 5 protection claims, 2 promotions) passes:

```
zapote-claims claims.json
  No violations detected by implemented checks (15 claims, 5 protection claims, 2 promotions).
```

`zapote/tools/check_fault_loop.py --netlist raw/netlist_fault_loop.json \
  --loop-nets PFC_BUS_PLUS_390V,PFC_BUS_MINUS,a1 --assignments raw/assignments_loop_illustrative.json`
→ exit 0 `FAULT LOOP CONSISTENT`; a null assignment also passes. Both negative controls fail as
designed: the withdrawn `U12 = 34 A` model (exit 1) and a reversed MOV bound (exit 1). All outputs
retained under `raw/checker/`; receipt `raw/checker/checker_receipt.json`. The ledger advances one
rung at a time (`none → protection_identified → part_selected`) and is **not** promoted to
`coordination_demonstrated`. A clean run means no implemented check fired; it is not proof of
correctness and not physical evidence.

## 7. Quantities that remain null, and what resolves them

| Null | What would resolve it |
|---|---|
| internal-loop R, peak current, action I²t | high-current loop model: U10/U9 short residual, bank ESR at discharge frequency, fuse R, layout |
| F2 clearing at 400 Vdc cap discharge | fuse DC clearing characteristic for a capacitor-discharge waveshape (or a test) |
| line-fed prospective peak; F1 total clearing | AC source/line impedance at the fault + F1 time-current/total-clearing curves at matching conditions |
| MOV current and required clamp | committed surge requirement + LA Series Figure 10 read at the actual MOV current |
| U9 gate state at fault; energy split | fault sequence / SOA mapping |

## 8. Completion-criteria checklist

1. **Name the parts** — **MET.** F2 = FWP-50A14F (Eaton/Cooper Bussmann), sourced to Cooper Bussmann
   DS 720025 for DC rating, pulsed I²t and DC breaking capacity; U7 = V150LA10AP; F1 = Schurter
   0034.3129. Rating conditions recorded on every claim.
2. **Explicit fault cases (a)–(e)** — **MET.** Healthy and failed-short `U9` kept apart; line-fed,
   surge, and the cannot-interrupt list all stated; case (b) carries the "no available part
   interrupts it" result.
3. **Size from the pulse, not the average** — **MET.** Pulse waveform and integral stated; peak and
   action I²t left **null** with the exact inputs that would size them; average used for continuous
   duty only.
4. **Coordinated clearing** — **MET** (verdict given): **NOT demonstrated**, with reasons.
5. **MOV selection + required clamp** — **MET.** Part named; required clamp is `V_clamp(I_MOV)`
   from the manufacturer V-I (Figure 10) and is **null**; 50 A point not reversed; L–PE not clamped;
   surge contract marked provisional; internal fault kept separate.
6. **Evidence ledger passes, output retained** — **MET.** `zapote-claims` exit 0 and
   `check_fault_loop.py` exit 0, both with negative controls (exit 1), all retained under `raw/`.
7. **Nulls stated with what resolves them** — **MET.** §7.

**Single most important missing input:** the **internal discharge loop's high-current impedance at
the fault** (U10/U9 failed-short residual + bank ESR + fuse + layout). It sets the prospective peak
current and action I²t and therefore decides whether the selected FWP-50A14F melts **and clears**
inside its 400 Vdc capacitor-discharge rating. Until it exists, case (b) coordination cannot be
demonstrated, and no available part is shown to interrupt it.
