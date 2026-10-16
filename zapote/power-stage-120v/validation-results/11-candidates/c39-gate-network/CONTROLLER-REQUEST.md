# Candidate 39: request for a hardware capacitive-mode (phase) detector, 2026-10-15

Status: request from the power-stage side to the controller owner. **Requirement only**: it says what the detector
must do, not how. Nothing on the controller branch or in `firmware/` is edited from here.

## Why
- S4 (the incoming switch hard-commutates its partner's conducting body diode) is the CFD7's binding case for the
  reverse-diode limits: 70 V/ns dv/dt and 1,300 A/µs diF/dt (IPW65R018CFD7 Rev. 2.0, Table 2 p.3). These are per-edge
  ruggedness limits.
- S4 is not a steady-state point; the firmware is designed to keep the tank inductive. But it arrives in bursts:
  - a non-magnetic pan at the 35 kHz floor;
  - a restart within ~250 ms;
  - a CT_ZC calibration or polarity error;
  - a load transient.

  Once the tank is capacitive, **every edge of both legs is an S4 edge** until the 5° software latch acts. That is up to
  ~10.6 ms, about 370-740 edges per leg (`01-switching-parasitics/gate-network-2026-10-15/results/S4-EVENTS.md`).
- Candidate 39 (stage 42: 68 Ω turn-on + Cgs 4.7 nF) meets both limits at **typical** recovery charge: 49.7 V/ns and
  244 A/µs. No tested network meets them at the datasheet **maximum** charge, where the nearest tested network reads
  106 V/ns. The D-8 bench decides that basis. A hardware detector cuts the number of S4 edges per episode whatever the
  bench finds, and it is the only backstop if the maximum-charge basis does not close.
- Today no hardware detects capacitive operation. The hardware trips only on over-current (CT and shunt OCP), and a
  capacitive tank at normal current does not trip them.

## Requirement
1. **Detect** that the tank current leads the bridge voltage (capacitive mode, or the current's zero crossing after
   the incoming switch's turn-on edge) on either leg, every switching period, from 35 to 60 kHz.
2. **Act in hardware**: remove all four gate commands (or assert the drivers' DIS through the existing PERMIT /
   interlock path) without firmware in the loop.
3. **Response**: the gates are off within **4 switching periods** of the first capacitive edge (≤ 115 µs at 35 kHz;
   ≤ 8 edges per leg per episode, against ~740 today).
4. **Threshold**: it trips at a current lead of 0° or more; a margin on the inductive side (trip below a few degrees of
   lag) is allowed. It must not trip in normal operation at ≥ 45° lag and f ≥ 1.05 f_res, nor at the first edge after
   idle (S5, 0 A: no diode conduction).
5. **Low current**: it must hold down to the current where a wrong-sign edge stops being an S4 edge (the tank model
   shows no wrong-sign edges at ≥ 20 % of crest near the line zero, `05-resonant-tank-envelope` README). Below that
   it may blank, but it must not be blind for the first ~3.4 ms after a start, as the software check is (< 2 A RMS).
6. **Latch and report**: the trip latches until firmware clears it, and the controller can read the cause (separate
   from OCP) for the fault log.
7. **Fail-safe**: losing the CT_ZC signal or the detector's own supply must disable the gates or block PERMIT. It must
   never leave them enabled with the detector blind.
8. **Isolation**: any power-side signal it uses crosses to SELV on the existing reinforced barrier rules (D5 basis,
   8.0 mm); no new HOT-SELV crossing without that basis.

## Signals the power board already has
- CT_ZC (tank-current zero-crossing comparator, SELV side), the PWM_HA / LA / HB / LB commands at J4, and the
  PERMIT / BUS_FAULT interlock path.
- Whether the detector is built from these on the controller, or needs a power-board signal (for example a
  switch-node edge), is the controller owner's call. If it needs a power-board signal, ask here and it becomes a
  power-stage candidate.

## Not asked
- No change to the frequency loop, the 45° / 1.05 f_res rule or the 5° software latch; the detector adds to them.
- No change to J4 pinout from this request alone.
