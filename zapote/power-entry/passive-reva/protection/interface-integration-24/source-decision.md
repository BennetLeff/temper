# AUX source boundary decision for integration fixture 24

Status: **engineering recommendation for an isolated low-voltage integration
fixture and a safe-shutdown design target**. This does not select a production
source, approve mains connection, or close the source waveform, cutoff,
thermal, startup, or hardware safety requirements. Revision 11 remains the
latest compiled candidate.

## Recommendation

Evaluate **the documented IRM-10-15 → Revision 19 LT4363-1/FDB33N25 →
protected AUX fanout** path first, with the TPS54202 and all AUX consumers
downstream of the clamp. In a SELV-only fixture, a characterized isolated
programmable DC source represents the IRM output at `AUX_RAW`; do not connect
the mains-fed IRM module to that fixture. This keeps the graph tested in
Revisions 20–23 while replacing their invented source/load with measured or
bounded inputs. Treat clamp resistor/capacitor choices as provisional until
the physical source, load, startup and FET SOA evidence is obtained.

For product behavior, target **safe, latched shutdown after a source fault,
followed by deliberate re-arm**. Continuous AUX through an arbitrary source
fault is not presently required. On fault detection or AUX loss, inhibit the
PFC switch and relay, control stored energy by their separate rated paths,
clear RUN/authorization, and prevent source recovery or an LT4363 input power
cycle from restarting power conversion. The LT4363-1 itself latches off after
its timer fault, but SHDN or an input interruption can reset that latch; the
system must retain the no-restart condition independently. This is a design
target, not proof of gate turn-off, relay release, reset propagation or
residual-voltage safety. Shutdown timing and the source fault envelope still
need product limits and hardware evidence.

Evaluate **IRM-10-15 → TPS26601RHFT → AUX fanout** as a separate cutoff
alternative if the product permits a safe output outage. Do not silently put
TPS26601 in series with LT4363 or substitute it in a Revision 20–23 deck:
either changes startup, fault charge, reset and component-count behavior.

This is a fixture recommendation because it retains the existing 15 V port
contract and active clamp graph while avoiding a second linear stage's dropout
and heat. It does not claim the IRM-10-15's output OVP stays below the driver's
limit or that the LT4363 has already been qualified. Use 18 V as
the conservative receiver ceiling while the integrated driver remains the
UCC27511A; TI specifies 4.5–18 V recommended VDD and 20 V absolute maximum.
If integration instead adopts UCC27624, re-check against its own ratings.

## Source comparison

| Path | Normal envelope evidenced by source records | Fault / source boundary | Implications |
|---|---|---|---|
| **IRM-10-15 direct, followed by active protection** | Mean Well specifies 15 V ±2.5% (14.625–15.375 V), 0.67 A, 10.05 W and 200 mVpp ripple under the datasheet's 0.1 µF + 47 µF measurement fixture. Existing interface run window is 14.25–15.75 V at the consumer pins. | Output OVP trigger range is 17.25–20.25 V. Mean Well says shutoff / zener clamping and overload hiccup recovery, but gives no DC output fault waveform, source impedance, clamp-current/energy limit, output peak, or downstream-fault charge. | OVP range crosses 18 V, so the LT4363 protection candidate must be qualified or a different independent limiter/cutoff selected. 0.67 A is a rating, not an assembled-load or startup guarantee. Hiccup/restart must not arm PFC or replay a command. |
| **Historical IRM-10-24 → TPS7A4701 15 V → TPS54202 5 V** | IRM-10-24 is 24 V ±2.5% (23.4–24.6 V), 0.42 A, 10.08 W. TPS7A4701's published ±2.5% output accuracy applies for input at least output +1 V; at 15 V this is satisfied by the nominal source. TPS54202 is rated 4.5–28 V input. | IRM OVP trigger range is 27.6–32.4 V, still not a guaranteed transient clamp. Its existing 35 V raw-input limit is an explicit design assumption, not a Mean Well fault bound. TPS7A4701 input is recommended only through 35 V, 36 V absolute, leaving 1 V absolute-rating margin at that assumed edge. | Adds an LDO barrier and separates nominal 15 V and 5 V rails, but adds dropout and potentially material heat. The existing screen estimates 2.116 W at 32.4 V and 2.417 W at 35 V under its conditional 115.74 mA load. TPS26601 after the LDO can isolate LDO pass-through; it still does not clamp the protected rail. The upstream 47 µF LDO capacitor is not downstream hold-up/overshoot capacitance after inserting the cutoff. |

The published 200 mVpp ripple figure is measured with external 0.1 µF and
47 µF capacitors at 20 MHz bandwidth; it does not define output impedance
versus frequency or a fault-source Thevenin model. The shared IRM family spec
gives AC input surge-immunity test levels, not a post-module DC output surge
waveform. Neither path has a manufacturer-bounded downstream fault source,
including rise rate, hold time, impedance, current limit, or charge after
fault onset.

## Alternative cutoff screen and normal operating conditions

If the separate TPS26601 cutoff alternative is pursued, TPS26601 is rated for up to 60 V input and provides adjustable OVP cutoff,
UVLO, current limit and reverse protection. TI's Rev G timing table's 6 µs
OVP entry ends at **FLT assertion**; it is not a maximum FET turn-off time or
an output-peak guarantee. OVP is cutoff, not clamping. Earlier screening with
130 kΩ / 10 kΩ and stated ±1% total resistance error plus ±100 nA pin leakage
calculates 16.066–17.485 V static trip range. That leaves static margin below
18 V and no established allowance for dynamic charge or parasitic excursion.
It is a screening result, not an adopted divider.

Use the following inherited run envelopes for fixture planning only:

* AUX at UCC28180 / gate-driver pins: 14.25–15.75 V while run permission is
  asserted. This is a chosen interface requirement, not a manufacturer
  guarantee for either complete supply.
* Logic5: 4.75–5.25 V while logic is enabled.
* TPS54202 input: remain within its 4.5–28 V recommended range, including
  startup and cutoff transients.
* In the TPS26601 alternative, external UVLO must permit the 14.625 V minimum source
  output; do not accept factory UVLO behavior that can require 15.75 V.
* In the TPS26601 alternative, current limit must exceed the measured maximum simultaneous load
  and charging demand over tolerance and temperature, yet bound fault charge.
  The 120 kΩ candidate's specified minimum active limit (85 mA) is below the
  114.474 mA *conditional* historical load calculation; it is therefore not
  usable as-is. That calculation assumes 75 mA direct AUX, 75 mA at 5 V and
  70% buck efficiency, and omits new interface loads and actual inrush.

The cutoff alternative's required OVP evidence remains:

```text
Vpeak = Vbefore + Qnet / Cdownstream,min + Vparasitic < 18 V
```

Measure or guarantee source voltage and source impedance, cutoff current over
time, actual FET interruption, effective downstream capacitance at tolerance,
bias and temperature, and layout/probe parasitic peak. If continuous AUX during
a source fault is required, the cutoff alternative cannot satisfy it by design.
The Revision 20 LT4363-1 model also latches off for its declared 35 V / 50 ms
fixture, so the proposed active-clamp path cannot yet claim continuity. A
ride-through requirement would need a qualified regulating clamp or another
specified architecture with MOSFET SOA and thermal proof.

## Startup, dropout, and power state

For IRM-10-15 direct, the rated tolerance lower point is 14.625 V. There is
only 0.375 V above the 14.25 V interface floor before cutoff resistance,
connector/wire drop, ripple and load-step sag. The complete IRM startup,
hiccup recovery, output impedance and loaded rail transient are not bounded by
the datasheet conditions cited here. For the IRM-10-24 path, the TPS7A4701's
15 V accuracy condition has at least 8.4 V raw headroom at the source's 23.4 V
low static corner, but regulator startup/dropout under the actual load,
thermal environment, and its behavior during source fault are not measured.

TI gives TPS54202 a 5 ms **typical** internal soft-start, not an input current
waveform or guaranteed load pulse. The prior clamp screens' 150 mA pulses are
synthetic sensitivity fixtures, not TPS54202 behavior. Startup acceptance
needs simultaneous source voltage/current, protected AUX, buck VIN current,
LOGIC5, enable, cutoff FLT, and driver VDD. Include full/partial discharge,
load state, temperature, and source current-limit/hiccup recovery.

Fault recovery must leave the command and run-permission paths disarmed until
a deliberate re-arm after rail qualification. An IRM hiccup restart, LT4363
input power cycle or eFuse auto-retry cannot be allowed to create an accepted
start. The design target permits indefinite gate-driver AUX loss only when
switch, relay and stored-energy behavior remain safe; physical verification
is needed before that becomes an acceptance claim.

## Decisions required to leave fixture status

1. **Select the product producer and protection**: direct IRM-10-15 or
   IRM-10-24 plus TPS7A4701; qualify the proposed LT4363 clamp, select the
   separate TPS26601 cutoff alternative, or specify another protection path.
   The recommendation above only chooses which graph to evaluate first.
2. **Define source fault contract**: maximum normal/fault voltage, source
   impedance/current limit, rise rate, duration/repetition, AC-input event
   coverage, and permitted Mean Well hiccup/recovery behavior. The 35 V raw,
   0.5 Ω, 1 ms ramp and 50 ms hold used by prior screens are explicit fixture
   assumptions, not supplier guarantees.
3. **Bound fault disposition**: the current engineering target is latched
   safe shutdown with deliberate re-arm. Define maximum time to remove
   switching and relay drive, stored-energy handling, permissible outage,
   and whether essential control or diagnostics need a separately qualified
   supply.
4. **Close real loads**: maximum steady current on each port, startup charge
   and waveform, temperature extremes, and whether the 5 V buck is downstream
   of the protected AUX cutoff.
5. **Approve the protected receiver envelope**: confirm the 14.25–15.75 V run
   window, the 18 V upper fault ceiling for the selected driver, and reset /
   re-arm behavior after source retry or cutoff retry.

Until these are specified and verified, no divider, current-limit resistor,
capacitor, source impedance, or fault duration in the fixture is a product
limit.

## Evidence

Local design records:

* [`INTERFACE-DESIGN.md`](../../INTERFACE-DESIGN.md) — direct IRM-10-15 producer proposal and 14.25–15.75 V consumer envelope.
* [`controller-integration-06/supply/README.md`](../controller-integration-06/supply/README.md) — historical IRM-10-24 → TPS7A4701 → TPS54202 path and conditional load/thermal screens.
* [`interface-physical-14/aux/report.md`](../interface-physical-14/aux/report.md) — source waveform/impedance gap and passive-barrier rejection.
* [`interface-handshake-13/aux-decision.md`](../interface-handshake-13/aux-decision.md) — TPS26601 static threshold and unresolved charge-through-interruption requirement.
* [`interface-dynamics-23/README.md`](../interface-dynamics-23/README.md) — synthetic startup-pulse sensitivity and missing physical input waveform.

Manufacturer primary sources:

* [Mean Well IRM-10 specification, revision 2025-08-08](https://www.meanwell.com/Upload/PDF/IRM-10/IRM-10-SPEC.PDF) — output ratings, tolerance, ripple test fixture, OVP trigger ranges, overload hiccup and mains surge-immunity tests.
* [TI TPS2660 Rev G](https://www.ti.com/lit/ds/symlink/tps2660.pdf) — TPS26601 input limits, adjustable cutoff, UVLO/current limit and timing endpoints.
* [TI TPS7A4700/TPS7A4701 Rev F](https://www.ti.com/lit/ds/symlink/tps7a47.pdf) — input limits, output accuracy conditions and dropout.
* [TI TPS54202 Rev C](https://www.ti.com/lit/ds/symlink/tps54202.pdf) — 4.5–28 V input and typical 5 ms soft-start.
* [TI UCC27511/UCC27512 Rev F](https://www.ti.com/lit/ds/symlink/ucc27511.pdf) — 4.5–18 V recommended VDD range and 20 V absolute maximum.
* [ADI LT4363 Rev C](https://www.analog.com/media/en/technical-documentation/data-sheets/4363fb.pdf) — LT4363-1 timer latch-off and SHDN/input-interruption reset behavior.
