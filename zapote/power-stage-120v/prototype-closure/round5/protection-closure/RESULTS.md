# Precharge isolation candidate

This is an additive, executable ECO for `PC125-CATCH-R5-2`, not a powered release or a claim that all native boards implement it. It adds two separately driven, normally-open Schneider LC1D18BD contactors around the complete two-resistor precharge network. Both contacts are open before RUN. Consequently a bypass contact opening ahead of the upstream source contacts cannot create the original **conductive** return through the precharge resistors unless both isolation routes are defeated. The existing source contacts, bypass, resistor/TCO branches and DC catch branch remain required.

The exact connector contract is in `interface.json`; receiver pins, values, primary-source conditions and static hardware permission are in `receiver-ECO.md`. These files supersede earlier exploratory dynamic-scanner/FPGA suggestions. **No FPGA is required in the product.** Optional bench instrumentation is outside this ECO.

## What changed

`isolation.c` implements the additional controller in plain C for reuse by the target/model integration owner. It does not replace the existing energy state machine. It consumes a fresh attempt-scoped cold POST token, tests each isolation contact while the source is verified open, holds each close challenge and final CONNECT energized for at least73ms regardless of early NC movement, and then permits the original precharge sequence. The73ms allocation rounds the exact contactor's72.45ms maximum closing time upward; it is not a measurement of the installed driver/contactor chain. The coil driver, supply and qualified conditions must support that allocation.

After the existing loaded bypass proof, both isolation coils turn off. Both NC mirrors must be valid and closed for10ms. `PC_REARM` then waits for the proof timer to be physically rearmed; a low command does not reset an LTC6993-1 nonretriggerable one-shot. The integration owner must observe its actual window low for2ms and wait beyond the final selected board timer maximum from the previous KT edge. The provisional131433us comment is conservative for the earlier191k1% allocation; the final board resistor/tolerance receipt owns the derived bound. `PC_REPROVE` requires a new loaded proof epoch, initially false then qualified true at least50ms after entry, with a110ms deadline. Both proof pulses require thermal/pulse-load qualification. The original446458us global source-present timer covers precharge, bypass, isolation, rearm and repeated proof; it never restarts at an internal transition.

The wrapper must drive `post_isolation_proven` only after fresh electrical evidence is continuously good for50ms. The core's minimum epoch age is a second guard, not a substitute for that measurement. `bypass_proven` retains the earlier proof/health permission during the intentional KT-low gap; actual safety/continuity failure clears `healthy`. START, all mechanical selftests, source admission and every subsequent powered state require `feedback_static`: all five excitation outputs remain high, raw mirror samples are current, and no intentional low scan slots occur while source is present.

RUN additionally needs raw KPA/KPB closed mirrors, both excitation levels high, both coil commands low and existing hard permission/supply-good in a **native combinational hardware gate**. Firmware cannot replace that gate. Faults drop all outputs; resetting requires a safe RESET-low observation followed by a fresh RESET rising edge with START low. Reset does not clear the consumed POST token. A new START requires a new cold POST.

## Verified behavior

`replay.sh OUTPUT_DIRECTORY` checks authored source hashes before compiling or launching ngspice. The C suite uses AddressSanitizer and UndefinedBehaviorSanitizer and tests:

- Four54/73ms pickup and16/24ms release combinations, checking actual modeled main-contact state before allowing RUN.
- Initial/release weld of either isolation contact, disconnected feedback, shorted feedback, stale/lost feedback, unexpected closure during RUN, missing bypass proof, missing/reused POST, non-cold attempt, lost health, held START and100ms/40ms deadline failures.
- Early NC opening cannot bypass the73ms energized dwell; held RESET cannot rearm a fault; cached pre-isolation proof cannot pass the new epoch; indefinite REARM reaches the unchanged global deadline; static excitation mode loss fails closed.
- All32 valid five-bit source-off scan masks and800 static-high/cross-channel mutations. Source-off electrical challenge cannot detect every short across an NC contact; the individual mechanical challenge is also necessary.
- Boundary checks for2ms sample age,446458us global timeout,1ms scheduler interval and output inhibition in every active state.

Two deliberately broken C candidates—removing pickup dwell and allowing level-sensitive RESET—must fail this same harness. These tests demonstrate controller behavior under the stated contact/feedback model; they do not measure contactor performance or certify single-fault safety.

## Prescribed voltage-exposure experiment

`exposure.rs` generates54 linear ngspice runs: zero/one/two open gaps,10/100/1000pF per assumed gap,10/100/1000ns voltage rise, and1/0.5µs maximum transient step. It applies **932.4886V for8ms** as an illustrative imposed exposure. That voltage is calculated from the older reported36.612kW at23.75Ω; it is not a current accepted whole-plant peak or a voltage bound. The8ms duration represents the16ms bypass versus24ms main opening mismatch. The test does not import a measured contact capacitance, arc model, fuse curve or device survival limit.

For equal open gaps the series capacitance is `Ceq=Cgap/gaps`, the parallel resistor load is `Req=23.75/2`, and `tau=Req*Ceq`. With ramp time `tr`, each resistor sees peak `V*tau/tr*(1-exp(-tr/tau))`; its peak power is the square divided by23.75Ω. Integrating both edges with long intervening hold gives each resistor energy `2*V²*tau²/(tr²*R)*(tr-tau*(1-exp(-tr/tau)))`. These independent analytical values are checked against ngspice. Equal-capacitance sharing does **not** establish either physical gap's worst-case voltage withstand.

| Open gaps | Peak each resistor over sensitivity sweep | Maximum energy each resistor |
|---|---:|---:|
|0, original conductive route|36,612W|292.922J|
|1, other isolation contact welded|0.000516–16,727.09W|0.334643mJ|
|2, both isolation contacts open|0.000129–8,560.925W|0.133319mJ|

All54 cases match the analytic peak within0.00110% and energy within0.00262%; both transient-step settings pass. The largest10ns/1nF cases still exceed4000W instantaneously. The available4000W/5s cold single-pulse specification is **not a nanosecond resistor pulse qualification**, so neither the peak comparison nor the small integrated energy proves survival. The useful result is removal of sustained conductive energy and explicit residual high-frequency pulse demand. Actual contact capacitance, asymmetric voltage sharing, restrike/flashover, harness capacitance and the joined nonlinear source/catch plant remain integration and physical checks.

An earlier full-plant stand-alone adaptation was rejected: even its unchanged original topology aborted near0.05829s at the rectifier nonlinear node. Its logs and generator remain under the output directory marked failed; no stress or pass claim is drawn from it. The parent model owner is independently updating the accepted joined model with the actual wrapper/contact timing. This smaller exposure study must not be substituted for that model.

## Alternatives and remaining limits

Keeping only the original bypass leaves the conductive diversion failure. Software ordering of that same bypass cannot cover an independently opening contact. A single added open isolation contact removes the normal path but a welded contact restores it; two independent normally-open contacts retain an open route with either single weld. Moving to a different solid-state precharge/bypass architecture would require new loss, leakage, fault and isolation analysis and is not necessary to test this correction.

The dual contacts do not solve a short bridging both, two welds, common cause driver/logic faults, arc restrike, the source-present precharge failure interval or an unbounded DC catch fault. Source-off diagnostic faults that arise later during static RUN can remain latent; a masked mirror plus a weld is an additional/common-cause scenario, not something the combinational gate has proven to detect. Preserve physical separation, insulated unused poles and independent wiring/drivers.

**FC1 remains unqualified for the actual installed DC fault.** Obtain the FWP-10A14F total DC clearing/arc envelope at the actual capacitor/source voltage and prospective current, minimum interrupting current, applicable source L/R and preloading/temperature. A700VDC voltage rating and50kA interrupting rating do not provide the needed let-through waveform. The22A²s figure at700VAC is not substituted. The2mΩ conductor used by the earlier model does not simulate clearing. No supplier contact has been made.

No assembled hardware exists. Actual coil/pan characterization, capacitor limits, cold POST, installed supply/receiver timing and leakage, two-pulse proof-load behavior, contact opening/extinction, joined model correlation and staged measurements remain necessary before power release. Native driver/receiver/gate and actual target wrapper integration are owned by peer agents; their receipts, not this candidate's unit tests, establish implementation status.

## Native admission follow-through

`discharge-window-ECO.md` and `discharge-window.rs` add the physical symmetric bus/catch discharge predicate, conditional131072-corner error screen, hardware one-token ADMIT interface and corrected repeated-proof trigger. Actual native timer isLTC6993HS6-1#TRMPBF; earlier inherited−2/nonretriggerable wording was corrected againstADI. Board integration found and is correcting ATTEMPT self-hold on repeatedADMIT and premature global-timeout bypass atfirstBYPASS_PROVEN. The native source/test receipt, not this candidate specification, determines whether those corrections are integrated.
