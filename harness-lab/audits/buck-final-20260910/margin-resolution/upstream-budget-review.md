# Upstream 15 V source and VIN-budget review — 2026-09-10

## Finding

The actual declared upstream source is Mean Well **IRM-10-15** (`PS1`),
instantiated by `elec/src/modules.ato::AuxSupply` and connected to the
`+15V` rail in `elec/src/main.ato`. The source anchors are
`elec/src/components.ato:84-91` (exact component/MPN and input range),
`elec/src/modules.ato:1564-1580` (AuxSupply and PS1 instantiation), and
`elec/src/modules.ato:1571-1573,1622-1625` (15 V rail and ±10% Atopile
assertion). Its retained primary datasheet is the official
[IRM-10-SPEC PDF](https://www.meanwell.com/Upload/PDF/IRM-10/IRM-10-SPEC.PDF),
file name `IRM-10-SPEC 2025-08-08`, retained at
`margin-resolution/IRM-10-SPEC.PDF`, SHA-256
`1aab6b30492328818e4d0900416676891eeb1076f409d56dc2277d7119ed208a`.

The source data provide a useful upper bound on what the buck may receive,
but they do **not** derive a tight VIN switching-ripple budget:

Page 2 was visually checked against the retained PDF. The columns are ordered
IRM-10-3.3, -5, -12, **-15**, -24: the 15 V column has 0.67 A, 10.05 W,
200 mVp-p, ±2.5%, ±0.3%, ±0.5%. The OVP row directly below maps the
15 V column to **17.25–20.25 V**; the adjacent columns are separate 3.3 V,
5 V, 12 V, and 24 V variants.

| IRM-10-15 item | Manufacturer value / condition | Meaning for buck VIN |
|---|---|---|
| DC output | 15 V nominal; **±2.5% output-voltage tolerance** under the datasheet's stated 230 Vac / rated-load / 25 °C test condition (page 2 note 1) | This is approximately 14.625–15.375 V under that condition. Temper's 13.5–16.5 V envelope is a wider board-level condition requiring system evidence. |
| Rated/current range | 0.67 A, 0–0.67 A; 10.05 W | The buck's 0.5 A / 1 A pulse is only part of the complete 15 V rail budget; gate drivers, relay and other loads must be included. |
| Ripple and noise | **200 mVpp maximum**, measured at 20 MHz with 12-inch twisted pair terminated by 0.1 µF + 47 µF (IRM-10-SPEC p.2, row “RIPPLE & NOISE”, Note 2) | This is the only retained manufacturer VIN-noise number. It already exceeds the proposed 125 mV buck input criterion and is measured at the module output under the datasheet setup, not at C9/U3. |
| Voltage tolerance | ±2.5% (includes setup, line and load regulation) | About ±0.375 V around 15 V; it does not specify source impedance or switching-edge transfer. |
| Line regulation | ±0.3% | Low-frequency line sensitivity only. |
| Load regulation | ±0.5% | Low-frequency load sensitivity only. |
| Overload | 115–190% rated output power, hiccup and automatic recovery | Source behavior under overload is nonlinear; it cannot be represented as a fixed Thevenin resistance. |

The IRM datasheet's 200 mVpp number is therefore a source-side noise ceiling,
not a permitted buck VIN ripple budget. It makes a 125 mV requirement
unsupported as a closure criterion unless the source is filtered, the system
budget allocates the 200 mV differently, or a measured transfer proves that
the C9/U3 pin sees less. No source impedance, output impedance versus
frequency, cable inductance, or interaction with C9 is declared in the
retained IRM evidence.

The existing `AuxSupply` declaration adds `c_out = 100 uF ±20% X7R 25 V` and a
100 nF high-frequency capacitor (`elec/src/modules.ato`, `AuxSupply` block),
but these declarations do not specify effective capacitance, ESR, or a
frequency-domain impedance. The buck's 50 mVpp requirement in
`harness-lab/audits/buck-20260910/engineering/requirements.json` is an output
ripple target, not an upstream-source requirement, so it cannot be algebraically
reused as a VIN budget.

## Can a VIN budget be derived now?

No hard numeric VIN switching-ripple budget exists in the source chain. The
available hard requirements are:

* `elec/src/modules.ato::AuxSupply` asserts 15 V ±10% at the design level
  (`elec/src/modules.ato:1622-1625`); the exact source datasheet gives 15 V
  nominal, ±2.5% tolerance under stated conditions, and 200 mVpp noise under
  its own test fixture.
* `engineering/requirements.json` adopts 13.5–16.5 V as the buck test range,
  3.3 V ±5% output and 50 mVpp output ripple at 20 MHz.
* `elec/src/main.ato` has a separate **20 V / <10%** DC-bus ripple assertion;
  that is the HV doubler bus and does not constrain the isolated 15 V output.

The only defensible present conclusion is a **source-noise sensitivity**, not
a requirement: evaluate the C9/U3 network with a 0–200 mVpp source-noise
excitation using the IRM's 20 MHz measurement convention, then include the
switching current waveform. The 100 mΩ value appearing in the retained replay
is a model input; it is not an IRM guarantee and must not be converted to
`I_L,peak × R` at C9. A proper RLC/time-domain source transfer or an actual
measurement at the module output and U3 VIN pins is required.

The 125 mV candidate should remain **rejected pending this upstream/system
budget**. Adding C9 cannot be judged necessary or unnecessary from the
available source data because the source impedance and excitation waveform
are unknown. The current BOM can remain in place while this evidence is
collected.

## Existing procedure and fixture evidence

The repository already contains the relevant buck electrical procedure in
`harness-lab/audits/buck-20260910-followup/requirements-proposal.md`: ripple is
measured at the output-capacitor terminals with 20 MHz bandwidth, and startup,
load-step, efficiency and thermal conditions are specified. It is a procedure
proposal, not a completed hardware run. The current audit's
`components/qualification-ledger.md` and `components/current-buck-bom.md`
retain the exact C9/C11/C12 source evidence and explicitly leave combined
effective capacitance unresolved.

For L2, the existing plan already names the required standalone approach: the
`Inductor hot-current criterion` section of the follow-up proposal calls for
an exact-part 20%-drop L(I,T) curve or a controlled thermal/current test. The
current ledger repeats that this must be a standalone DC-bias fixture at the
8.35 A / 105 °C criterion; no executable hardware fixture or measured result
is present in this audit. No new infrastructure is needed for this review.

## Recommended next evidence

1. Treat 200 mVpp as the IRM source-noise sensitivity ceiling under its stated
   test setup, not as a buck acceptance limit.
2. Define the allowable source-to-C9 transfer (including harness, PS1 output
   capacitors, C9 ESL/ESR and U3 switching current) before choosing a VIN
   ripple requirement or extra capacitance.
3. At the existing six buck operating points, capture PS1 output and U3 VIN
   simultaneously; record the source/load condition and measurement setup.
4. Keep the existing L2 standalone fixture proposal and 8.35 A fault criterion
   unchanged pending parent scope review.

## Read-only peer review of startup and binary-capture work

The current startup resolution artifact is useful as an instrument/replay
check, but its fixed 0.5 A sink is not a valid physical load at a discharged
output. The recorded negative-output behavior is a valid falsifier for that
setup; it must not be reported as buck startup qualification. The compliant
post-rail load law already proposed in
`harness-lab/audits/buck-final-20260910/startup-protocol-resolution/README.md`
should govern the physical run, with the full 20 ms observation interval
after the 13.5 V input crossing. The existing 1 ms instrument window cannot
close that requirement.

The in-progress binary decoder in
`harness-lab/src/simulation_validation.rs` validates bounds, finite values,
exact byte length, and monotonic time, which are appropriate integrity gates.
It nevertheless reads the entire raw file into memory before parsing, while
the readiness proposal describes a file-backed/sequential design. At the
declared 8 GB raw-file limit this can fail from host memory pressure before
the parser's row limit is meaningful. The actionable boundary is to either
implement bounded streaming validation/decoding or adopt and document a
much smaller measured memory ceiling; this review does not change the limit.

These findings are review boundaries only. They do not alter the startup
protocol, binary implementation, or authoritative requirements.
