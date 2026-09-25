# F2-open current and shutdown timing audit

2026-09-19. **Simulation only; physical current and complete shutdown-time bounds
remain INDETERMINATE.** This audit supersedes using the previous 40 A / 10.66 µs
example as a design limit. Its arithmetic remains valid for its assumptions.
The user confirmed that no physical prototype is available.

40 A is a nominal controller threshold, not a maximum fault current. An assumed
50 A case leaves about 3 µs for shutdown under the plant assumptions below.
The current TLV1704 detector has no applicable published maximum delay to close
that budget. No circuit or PCB was changed by this audit.

## Current path and scope

The baseline uses UCC28180D, HCSM2818FT10L0 (10 mΩ), Würth 760800301,
STW65N65DM2AG and C3D20065D. Proposed F2 lies between diode cathode VD and
bulk bank VB, with a proposed 22 µF reservoir from VD to controller return.
Following F2 opening and healthy switch turn-off, the loop is rectifier positive
→ inductor → healthy boost diode → reservoir → controller return → shunt
→ rectifier negative. Line-fed current is sensed in both switching phases.

The internally powered bank → failed-short diode → switch loop bypasses the
shunt. These calculations do not bound it. Gate disable cannot stop a
failed-short switch. F1/F2 interruption coordination and local reservoir
discharge into shorts remain separate unresolved cases.

## Current-limit audit

The UCC28180 electrical table gives an input-referred PCL threshold magnitude
of 0.400 V typical and 0.438 V maximum. With 10 mΩ this is 40 A nominal and
43.8 A at nominal resistance. Including the shunt's 1% initial tolerance gives
**44.242 A**, before transient overshoot.
[TI UCC28180, §7.5 and worked example](https://www.ti.com/lit/ds/symlink/ucc28180.pdf).

Equation (3) is inconsistent with the table and worked example if its extra
factor of 2.5 is applied to that input-referred voltage. Figure 26 shows the
internal gain; equations (54)–(55) explicitly calculate 0.438 / 0.032 =
13.688 A. The screen follows the electrical table and that example; it does
not apply the gain twice.

For an **assumed shunt body temperature −40 to +100 °C**, including ±75 ppm/K
TCR from 25 °C gives Rmin=9.84375 mΩ. Adding specified worst-magnitude 2.95 µA
ISENSE bias across an assumed 1%-high 220 Ω resistor gives a conditional
steady-state threshold of **44.562 A**. This is not an instantaneous-current
maximum. That bias specification is tested at ISENSE=0 V; carrying it to the
negative trip voltage is another assumption, not a published guarantee there.
Shunt temperature remains unestablished.
[Stackpole HCSM](https://www.seielect.com/catalog/SEI-HCSM.pdf); retained source:
`sources/Stackpole-HCSM-2019.pdf`.

The existing 220 Ω / 1 nF filter has nominal τ=0.22 µs; assumed 1% R and 10% C
give 0.24442 µs. For a sustained monotone linear current ramp, extra filter
error is at most slope × τ. This does not cover arbitrary edge transients or
initial states. The UCC Figure 26 annotation of 300 ns blanking is not a
guaranteed maximum PCL-to-gate response. No complete maximum was found in the
datasheet; its gate fall-time specification measures something different.

The inductor's 180 µH ±20% specification is a small-signal measurement. The
43 A saturation figure is **typical**, at 30% inductance reduction. It is not
a current clamp or guaranteed Lmin at fault current and temperature.
[Würth 760800301, pp. 1–2](https://www.we-online.com/components/products/datasheet/760800301.pdf).

## Conditional shutdown envelope

`budget.rs` generates `budget.txt`. Inputs: 132 Vac crest, Cmin=19.8 µF,
bank=410 V and prior conditional static trip=432.085945 V. The 500 V ceiling
is a provisional screen, not an established installed component limit.
Capacitor voltage derating, temperature and effective capacitance remain open.

Low incremental L makes current rise faster; high incremental L bounds stored
energy. Assuming these limits hold over the entire trajectory:

```text
Iend = Istart + Vin_max / Lmin * delay
Vend = Vstart + Iend / Cmin * delay
Vpeak = Vin_max + sqrt((Vend − Vin_max)^2 + Lmax/Cmin * Iend^2)
```

The envelope permits simultaneous maximum current growth and capacitor
charging during the delay, then includes line energy during commutation.
It assumes healthy diode and switch and omits wiring spikes, fuse arcing,
surge, additional capacitance variation and parasitic ringing. It is a
conservative envelope only within those assumptions, not a transistor model.

| Assumed current at static threshold | Nominal 180 µH: allowable delay | Assumed Lmin=100 µH, Lmax=216 µH: allowable delay |
|---:|---:|---:|
| 40 A | 10.661 µs | 6.396 µs |
| 45 A | 8.406 µs | 4.693 µs |
| 50 A | 6.205 µs | 3.004 µs |
| 60 A | 1.928 µs | No nonnegative delay satisfies this envelope |

**50 A and 100–216 µH are assumptions, not established physical bounds.**
Current is specified at the voltage threshold, not necessarily at F2 opening.
Failure of this pessimistic screen is not proof of a physical overvoltage.

A comparator specified at 20 mV overdrive needs a further **3.557846 V** bus
reserve at the minimum assumed divider gain. Starting at 435.643791 V, with
50 A at that later point and L=100–216 µH, leaves **2.527 µs**. This remaining
delay still includes filter lag and every downstream stage. The previous
±8 mV static error allowance has not been qualified for a replacement part.

At that conditional operating point, a 2 µs delay gives a 496.861 V envelope
peak; 5 µs gives 515.425 V. **2 µs is a provisional design target**, with little
voltage margin, not a demonstrated delay or complete acceptance criterion.
Increasing capacitance buys time but adds energy outside F2; no such change
is selected here.

## Detector → latch → driver → switch

The compiled 21-part experiment ends at FAULT_N_RAW; the remaining path is
unimplemented. TLV1704 published propagation delays are typical, so they cannot
close a maximum-delay budget. [TI TLV1704](https://www.ti.com/lit/ds/symlink/tlv1704.pdf).

A candidate next circuit uses two **TLV3202** dual comparators, **SN74HCS21**
combining logic, **SN74HCS74** retained fault latch and proposed **UCC27624**
gate buffer. This is not a completed BOM or validated selection. Push-pull
comparator outputs must feed separate logic inputs, not be wired together.

| Stage | Published maximum or missing term | Conditions and limitation |
|---|---|---|
| Divider/filter | Complete ramp-to-threshold delay unknown | 100 pF, tolerances, actual ramp, initial state, parasitics, input loading and noise |
| TLV3202 | 55 ns | 5 V table, −40..125 °C, stated overdrive and 15 pF load; actual waveform applicability remains open |
| SN74HCS21 | 22 ns per gate | 4.5 V, 50 pF, full temperature; specified input-edge test conditions |
| SN74HCS74 CLR → Q | 19 ns | 4.5 V, 50 pF, full temperature; CLR pulse width and waveform must apply |
| UCC27624 EN disable | 27 ns | 12 V / 1.8 nF fixture; not automatically the proposed 15 V loaded gate |
| UCC27624 output fall | 14 ns | Fixture's 90–10% transition, not cessation of drain current |
| STW gate discharge and current fall | Applicable maximum unknown | Qg=120 nC, Qgd=58 nC, turn-off delay=114 ns and fall=11.5 ns are typical at their stated tests |

Sources: [TLV3202 §§6.5–6.6](https://www.ti.com/lit/ds/symlink/tlv3202.pdf),
[SN74HCS21 §§6.6–7](https://www.ti.com/lit/ds/symlink/sn74hcs21.pdf),
[SN74HCS74 §§6.6–7](https://www.ti.com/lit/ds/symlink/sn74hcs74.pdf),
[UCC27624 §5.6](https://www.ti.com/lit/ds/symlink/ucc27624.pdf),
[STW65N65DM2AG tables 6–7](https://www.st.com/resource/en/datasheet/stw65n65dm2ag.pdf).
Their different fixtures and timing reference levels prevent treating the sum
as an end-to-end guarantee. TLV3202 output edge times are typical, while logic
propagation tests use specified input edges. Published STW switching times use
325 V, 30 A, 4.7 Ω and 10 V gate drive, unlike this proposed circuit.

The latch must retain faults and require a fresh arm after valid rails and
healthy inputs. Rail dropout, charged buses with unpowered logic, input
back-powering, EN's internal pullup and startup with an already-open F2 still
need circuit treatment. A Boolean test cannot supply analog timing evidence.

## What closes the remaining unknowns

1. Obtain applicable manufacturer limits for incremental L(I,T), effective C,
   shunt temperature and installed voltage acceptance. A typical magnetic
   curve alone is insufficient.
2. Obtain the controller's maximum blanking/detection response and loaded
   switch-off response, or design an independently bounded current-limit path.
   Changing the shunt also changes soft-overcurrent behavior and rated-power
   capability; it is not a free correction.
3. Close the replacement detector's static threshold and overdrive budget;
   simulate the full actual circuit at adverse filter states, fault phase,
   rails and device corners. A typical macro-model cannot resolve absent limits.
4. When hardware exists, retain synchronized VD, VB, inductor current, detector
   output, latch Q, EN, VGS and switch-current traces. Establish total time from
   the defined unfiltered threshold to current cessation and peak VD including
   ringing over the accepted operating envelope. Hardware verification has
   not been performed.

`constraints.json` leaves current and end-to-end maxima null. This is the
evidence boundary reached with simulation and published sources.

## Checks and reproduction

From the repository root:

```sh
rustc --edition=2021 -O zapote/power-entry/passive-reva/protection/f2-timing-02/budget.rs -o /tmp/temper-f2-budget
/tmp/temper-f2-budget
rustc --edition=2021 --test zapote/power-entry/passive-reva/protection/f2-timing-02/budget.rs -o /tmp/temper-f2-budget-tests
/tmp/temper-f2-budget-tests
cargo run --locked --offline --manifest-path zapote/Cargo.toml -p zapote-harness --bin zapote-claims -- zapote/power-entry/passive-reva/protection/f2-timing-02/claims.json
```

Six Rust checks pass. The independent manufacturer example checks the current
threshold interpretation; other tests check arithmetic properties, not physical
validity. No new SPICE or hardware result is claimed. The prior idealized SPICE
check remains historical evidence under its original assumptions. The existing
claims checker verifies declared structure and hashes, not engineering truth.
