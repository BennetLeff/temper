# Revision 19 bounded verification contract

Scope: resolve the supplied review's concrete gate-network and reset-note
questions, then run the smallest dynamic experiment supported by available
models. Revision18 is frozen. The parent owns canonical CAD and verification;
Luna researchers own isolated temporary evidence only. No board or full
136-component candidate changes are included.

1. Reference connection: inspect ADI Figure5 as an image and reconcile its
   electrical nodes with native KiCad. If corrected, update the expected graph
   and auditor contract first; demonstrate failure against revision18 before
   editing the new schematic. Preserve diode polarity. Export native netlist,
   ERC, SVG/PDF/PNG and review BOM, inspect the rendering, and require unchanged
   part count/identities. External boundary ERC findings must not be waived.
2. Reset: distinguish fault-timer reset, shutdown while powered, UV/brownout,
   cold startup and fault recovery. 120ms is a timer-reset condition only.
   Neither an assumed constant-current calculation nor R*C sets a new maximum
   switch-off time. Ground-referenced gate voltage is not VGS. Required physical
   observations include Q1 current/VGS and actual driver-supply voltage.
3. Dynamic evidence: prefer authentic LT4363/FDB33N25 models. A vendor example
   or nominal waveform does not establish guaranteed corners. Missing usable
   controller models must be explicit. An ideal-source passive gate-network
   experiment may establish only network response to its imposed stimulus;
   it cannot establish startup, protection, controller latency, output peak,
   safe operating area or a hardware turn-off bound.

Every simulation attempt has a 30-second process deadline and bounded output.
A numerical probe requires a smaller-step comparison and an independent
closed-form check where possible. Preserve failed attempts. Do not enlarge
capacitors, add protection devices or loosen the <18V driver-rail objective
in response to an unresolved or failed result.
