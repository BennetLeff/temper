# Independent Revision 19 review

## Figure 5 topology

I inspected `/tmp/temper19-reference/mirror-15.png` directly. In Figure 5,
the LT4363 GATE output is the lower node labelled `GATE`; the MOSFET gate is
above the vertical series resistor labelled `R3`. The added R1/C1 branch
leaves the **lower, controller-side node** of R3. Thus the reference topology
is:

```
LT4363 GATE_DRV -- R6 -- Q_GATE (Q1 gate)
        |
        +-- R7 -- CG -- ground
        +-- D1 (anode at GATE_DRV, cathode at CG)
```

The diode cathode is the bar on the right, at the C1/CG node. Its anode is at
the controller-side branch node. The Figure 5 visual therefore supports the
auditor's intended contract, not the Revision 18 live netlist.

## Exported Revision 19 fixture

`interface-dynamics-19/clamp.net` currently exports:

* `GATE_DRV`: U1.4 and R6.1
* `Q_GATE`: Q1.1, R6.2, **R7.1, D1.2**
* `CG`: R7.2, D1.1, C3.1

That is a MOSFET-side branch. It is inconsistent with Figure 5 and with the
auditor's explicit expected contract, which requires R7.1 and D1.2 on
`GATE_DRV`. The `red-old-wiring.log` failure (`D1.2 expected GATE_DRV,
exported Q_GATE`) is therefore a real failure of the current live netlist,
not evidence that the expected contract is wrong. The handback text that says
the Revision 18 netlist confirms the intended topology inverted this result.

The correct repair is to move both R7.1 and D1.2 from `Q_GATE` to
`GATE_DRV`, leaving R7.2/D1.1/C3.1 on `CG`; then rerun native export and the
auditor. Do not only flip the diode: the resistor branch endpoint must move as
well.

## Reset/timing scope

The 120 ms figure can remain a controller timer/cooldown requirement. It does
not establish a 120 ms MOSFET VGS fall time, capacitor discharge time, output
disconnect time, or safe-off guarantee. The branch topology correction should
be followed by a dynamic check of VGS, gate-node discharge, output voltage,
and restart inhibition under the selected C3 corner. Avoid describing 4 V at
VCC as proof that the external MOSFET is safely off; it is only the LT4363 UV
comparator operating requirement.
