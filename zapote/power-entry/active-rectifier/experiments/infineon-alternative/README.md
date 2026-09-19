# Public active-bridge alternative

Status: **feasible prototype candidate; not a released or safety-qualified
replacement** (2026-09-19).

This bounded study answers whether the TEA2209T spacing problem can be avoided
without waiting for an NXP response. It evaluates Infineon's public active
bridge reference and replaces its no-longer-new-design driver with a current
TI dual isolated driver. It does not change the current KiCad board, Atopile
source, BOM, or Rust contract.

## Decision

The architecture is a viable next construction experiment, with a clear
qualification path:

* Keep the existing UCC28180 boost controller, inductor, bus, F2 location, and
  passive bridge used for surge/backup conduction. The active bridge is an
  input rectifier daughter section, not a replacement for the PFC controller.
* Use the Infineon control split: IR11688S senses the two low-side MOSFET VDS
  paths and drives the low-side pair; a separate two-channel isolated driver
  drives the two high-side gates. The reference's T1/T2 800 V sense-extension
  transistors are required because IR11688S alone is limited to 200 V sensing.
* Use **UCC21530DWKR** as the current high-side-driver candidate. TI lists the
  orderable as Active, with 4 A source / 6 A sink, 3.3 mm channel-to-channel
  spacing, 5.7 kVrms reinforced input isolation, and 1850 V internal
  output-to-output working-voltage capability. It is a conceptual replacement
  for the reference's 2EDF7275F only; it is not pin-compatible.
* Retain four 600 V MOSFETs. The current project candidate is
  IPW60R017C7 in TO-247-3; the Infineon reference uses four
  IPT60R022S7 in TOLL. Package, heatsink isolation, gate-loop inductance and
  surge behavior therefore need a new placement and routing experiment.

This clears the immediate TEA land-pattern blocker as an architectural choice,
but it introduces a larger, honest design task: two separate floating driver
supplies, high-side domain spacing, and a new timing/fault review. It is a
candidate to prototype, not evidence of a compliant appliance.

## Why this is not a drop-in claim

Infineon's 2019 application note reports a 2400 W PFC system headline, but the
same note says the tested low-line setup reaches about 1200 W at 115 Vac and
2400 W at high line (pp. 3, 11). Our maintained screen is 120 Vac nominal,
108--132 Vac, 15 A true-RMS input ceiling, and 1796.4 W ideal input power at
120 Vac. Thus the public result is useful architecture evidence, not a
qualification at our 1.8 kW low-line point. At 108 Vac the current ceiling
cannot deliver the 1796.4 W target (the maintained screen requires about
16.66 A), regardless of rectifier choice.

The Infineon board is a 35 mm × 6 mm × 30.5 mm, four-layer daughter card and
the reference PFC retains a diode bridge for surge protection (pp. 5, 15, 17--19).
Neither fact transfers its thermal, mechanical, or protection qualification to
our 310 mm × 210 mm two-layer prototype.

## Proposed next experiment

Build a schematic-only and then a routed active-bridge daughter unit with the
following frozen interfaces:

1. AC1/AC2 enter through the existing fuse/CMC/NTC path. Keep the passive
   bridge in parallel for surge and degraded-operation analysis.
2. Q1/Q2 are the high-side line devices, Q3/Q4 the low-side devices. The two
   conducting devices in each half-cycle are the MOSFET channel pair; body
   diode conduction during controller blanking remains part of the loss model.
3. IR11688S `GATE1`/`GATE2` continue to control the low-side pair through the
   reference's VDS filter and 800 V T1/T2 sensing extension. Do not connect a
   bare IR11688S directly to the line-domain sense nodes.
4. A UCC21530DWKR channel drives each high-side gate: `OUTA`→Q1 gate with
   `VSSA` referenced to the Q1 source/line-L domain, and `OUTB`→Q2 gate with
   `VSSB` referenced to the Q2 source/line-N domain. `VDDA` and `VDDB` each
   need a local 13.5--25 V output-side bias supply for the selected
   UCC21530DWKR 12 V UVLO variant. The 8 V UVLO UCC21530B variant is a possible
   alternate, but its orderable identity and lifecycle must be checked before
   it is substituted. The primary VCCI side remains the controller logic
   domain. The existing `AUX_15V_IN` name is only a nominal interface in the
   current source; its tolerance and isolation behavior are not yet a driver
   supply qualification. The exact isolated supply/bootstrap arrangement is a
   design input, not an assumed connection.
5. Keep the two high-side output domains physically separated from each other
   and from the logic side. Use the driver's >8 mm package clearance/creepage
   as a component datum, but apply the product insulation contract to the PCB
   paths; the driver datasheet explicitly warns that pads and PCB traces can
   reduce the package distance.

The first routed artifact should be a small driver/bridge prototype with
explicit domain labels and no connection to the frozen product board. It must
pass the existing Rust physical stackup and semantic net checks, then receive
an independent timing, bootstrap, surge, and thermal review.

## Evidence and limits

The source packet and exact hashes are in [SOURCES.md](SOURCES.md). The
connection and spacing assumptions are tabulated in [ARCHITECTURE.md](ARCHITECTURE.md).
The loss screen is a first-order comparison only; it does not include body
diode blanking, reverse recovery, gate-drive supply loss, surge conduction,
MOSFET hot RDS(on), or the retained bridge's interaction. Those terms stay
open until the prototype and model inputs exist.
