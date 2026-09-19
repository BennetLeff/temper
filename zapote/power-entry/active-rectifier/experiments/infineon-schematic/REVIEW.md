# Review and checks

## Completed

- Atopile 0.2.69 built `src/main.ato:InfineonActiveBridge` successfully.
- The generated netlist has 25 named nets and no singleton component pin in
  the retained connections. The independent netlist review checked that AC_L
  and AC_N each reach the passive bridge, one upper MOSFET, and its 800 V
  sense extension; PREBOOST_POS reaches both upper sources and both lower
  drains; HOT_GND reaches both lower sources and the passive bridge negative.
- The UCC21530 input, enable, dead-time, both floating references, both outputs,
  bootstrap diodes, and 220 nF bootstrap capacitors are all present in the
  netlist. The low-side IR11688S outputs reach Q3/Q4 through R8/R9.
- Q1/Q2 are D=PREBOOST_POS, S=AC_L/AC_N; Q3/Q4 are D=AC_L/AC_N,
  S=HOT_GND. IR11688S Gate2/O_A produces UCC INA and Q4 control; Gate1/O_B
  produces UCC INB and Q3 control. All-gates-off therefore leaves the passive
  body-diode rectifier path rather than a DC rail short.
- KiCad 10.0.4 exported the PDF and XML netlist. The rendered page was visually
  inspected; values, references, and the HOT-domain banner are legible.
- Native ERC with a local project, standard KiCad table, and candidate-local
  exact footprints reports **0 errors and 0 warnings**. ERC does not prove
  isolation spacing or electrical intent.

## Not established

- The UCC21530BQDWKRQ1's 8.9-V maximum turn-on / 8.4-V maximum turn-off UVLO
  and 9.2-V recommended operating floor against the full tolerance and
  cold-start behavior of the IRM-10-15 rail.
- Bootstrap hold-up for an 8–10 ms half-cycle, quiescent/leakage/Qg corners,
  recharge timing, minimum on-time, and UVLO behavior.
- Gate-driver output-to-output PCB spacing, creepage, clearance, slotting, or
  isolation-system qualification.
- Active-bridge surge sharing, short-circuit interruption, thermal performance,
  EMI, reverse recovery, or a production BOM.

The bootstrap resistor footprint is a 50-mm placeholder only: the RH05047R0FE02
mechanical drawing and pulse curve are not yet retained, so placement and BOM
release remain blocked. ERC's clean result does not resolve that mechanical
identity.
