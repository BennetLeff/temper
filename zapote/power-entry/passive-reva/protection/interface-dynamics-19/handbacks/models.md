# Rev18 model/runtime investigation

Date: 2026-09-22
Checkout inspected: `/Users/bennet/Desktop/temper/worktrees/power-entry`

## Result

No usable LT4363-1 or FDB33N25 model is present in the repository. `ngspice` is
installed at `/opt/homebrew/bin/ngspice`; no LTspice executable or local model
cache was found. I did not create substitute controller behavior or run an
unqualified simulation.

Analog Devices' official LT4363 product page explicitly lists LT4363-1 and
LT4363-2 as available LTspice models and links the official LT4363-2 demo
circuit (`LT4363-2_TA07.asc`):

`https://www.analog.com/media/en/simulation-models/LTspice-demo-circuits/LT4363-2_TA07.asc`

The product page also lists the LT4363-1 latch-off demo board DC1935A-A and
its design files. The web/runtime fetch could not retrieve the binary `.asc`
or `.zip` payloads (content-type/HTTP fetch failure), so there is no local
source hash or reproducible smoke run. The page is still a valid lead for a
follow-up download on a machine with LTspice/ADI downloads available.

Onsemi's product-recommendation page marks FDB33N25TM as having a “SPICE Live
Model”, but the page is a JavaScript app and exposes no static model URL to
the available text/runtime fetch. The official onsemi datasheet is available
at `https://www.onsemi.com/download/data-sheet/pdf/fdb33n25-d.pdf`; it gives
electrical limits but is not a transient model. No FDB33N25/FDB33N25TM
`.lib`, `.cir`, `.sub`, `.mod`, or `.spi` was found locally.

## What an externally obtained model must prove before use

The LT4363 model must expose the LT4363-1 latch-off behavior, UV/OV inhibit,
current-limit and timer/fault pull-down, gate-source clamp, shutdown input,
and supply-current behavior. The FDB33N25 model must include nonlinear gate
charge/Miller behavior and output/body-diode capacitances; a static RDS(on)
or generic MOSFET is insufficient for gate discharge, surge clamp, or SOA
claims. Model validity still needs comparison to datasheet curves and pin
mapping; vendor provenance alone does not qualify a model.

## Minimal bounded matrix after models are available

Use four capacitor corners first: `C3 = 1.30, 1.70 uF` and `C4 = 198, 495
uF` (the rev18 screened limits). Add one nominal case (`C3=1.50 uF,
C4=330 uF`) and one total-output stress case (`Cout=520 uF`, with the
downstream allocation stated explicitly). For each case run only:

1. 12 V input startup with the stated downstream load; record gate ramp,
output rise time, LT4363 VCC and timer voltage.
2. Input overvoltage step/surge within the selected MOSFET and controller
limits; record output clamp, MOSFET VDS/ID and gate stress.
3. Persistent overcurrent/short; record fault-timer expiry, gate pull-down,
and output disconnect/latch state.
4. Shutdown assertion and release; record gate discharge and restart/latch
behavior.

Keep traces small and bounded (at most 30 s per case, no campaign). These
results can inform prototype decisions but cannot establish production SOA,
surge immunity, or guaranteed startup without datasheet-corner/model
qualification and bench correlation.
