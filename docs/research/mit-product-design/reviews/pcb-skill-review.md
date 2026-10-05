# Independent review: `temper-pcb-power-review`

## Raw-source spot check

I compared the skill and `references/source-rules.md` with the downloaded course PDFs, using PDF page numbers, not the author's synthesis. Material claims checked:

| Skill claim | Raw source result |
|---|---|
| Fast commutation loops need low inductance; short, close gate drive and return | Confirmed. 6.622 Lecture 38 PDF pp. 1–2 explains switching-loop overshoot/ringing/EMI and derives the length, spacing, width relationship; p. 2 applies it to gate drive. |
| Flying-node area couples charge; shielding can lower coupling to a sensitive node but raises total capacitance | Confirmed. Lecture 38 pp. 2–3 says both. |
| Faster transitions trade switching loss against overshoot/EMI; snubbers can move loss | Confirmed. Lecture 15 pp. 2–4 covers both. Its buck formulas must not be copied directly to this full bridge. |
| Resonant load variation can cause peaking; induction heating is a relevant application | Confirmed with a qualification. Lecture 35 pp. 1–4 names induction heating and derives Q, gain and bandwidth for an elementary series RLC. A pan/coupling model is the skill's engineering extension, properly labeled. |
| Junction-to-case-to-interface-to-ambient and transient thermal analysis | Confirmed. Lecture 16 pp. 2–4 gives the thermal circuit, shared sink and transient impedance. |
| LISN and parasitic filter effects; common- and differential-mode paths | Confirmed. Lectures 28 pp. 1–3 and 30 pp. 1–3. |
| Lab DRC means configured rules were checked, not appliance clearance compliance | Lab 3 p. 1 indeed instructs DRC on its example low-voltage board and includes example spacing settings. The stronger interpretation is a sound engineering inference, correctly labeled in the reference. |
| Brownout and sequencing matter | Confirmed. 2.996 Lecture 4 PDF pp. 23 and 26 discuss brownout and sequencing. The fault-state analysis is explicitly marked as an extension. |

I found no material page-citation mismatch in these samples. The skill appropriately refuses to promote 2007 lab spacings or MIT lecture examples to safety limits. The MIT sources are useful for physical review methods, but device ratings, protection requirements and product compliance must come from current authoritative material.

## Forward test: actual answer produced using only the skill and supplied scenario

**Decision: not ready to order a PCB or declare protection and thermal design ready.** The supplied evidence identifies a concept and four partial observations; it omits the schematic, native PCB, selected part data, product requirements, operating envelope and representative tests. No numerical protection threshold, spacing or junction limit can be accepted from the scenario alone. A controlled evaluation build could be planned after the missing artifacts are reviewed, but this is not an order release.

| Artifact / finding and mechanism | Evidence class | Minimum next verification |
|---|---|---|
| 120 V full-bridge concept: “650 V MOSFET” and “455 V MOV clamp” do not establish switch survival. The MOV voltage depends on its specified test current, tolerance, surge waveform, lead inductance and coordination; bridge switching, tank resonance and faults can put a different voltage across each FET. An MOV can fail short or age. | Given claims; device-stress concern is a hypothesis. Lecture 15 pp. 2–4 supplies switching/SOA reasoning; Lecture 35 pp. 1–4 supplies resonance reasoning. | Select exact FET, MOV, fuse and snubber parts. Build a voltage/current/energy corner matrix, including surge, no pan, detuned pan, startup, shutdown and fault transitions. Check datasheet curves and capture device-pin waveforms at representative corners. Verify MOV end-of-life and upstream interruption. |
| One “40 ns comparator” feeding isolator and external latch does not establish a safe interruption time or safe off-state. Detection delay includes sense bandwidth/blanking, comparator overdrive, isolator propagation and CMTI, latch behavior, driver delay, switch turn-off and fault-current decay. Tank/bus energy can continue flowing after gate disable; possible freewheel paths require tracing. Loss of gate supply or control power can defeat an assumed latch state. | Given comparator claim; failure paths are hypotheses. 2.996 Lecture 4 PDF pp. 23–26 supports brownout/sequencing questions; the full fault-chain method is an engineering extension. | Supply the native schematic and timing budget with worst-case component data; trace the actual current path after each trip. Bench-inject faults and brownout with current/voltage captures and independent safety controls. Verify latch reset, power-loss state, driver UVLO, isolator CMTI and shoot-through interlock behavior. |
| “CAD zero overlap” does not establish electrical spacing, creepage, insulation or loop quality. Fast commutation and gate returns can still have high parasitic inductance; switch-node copper can inject into sensing; a rule pass checks only configured rules. | Geometry claim is given; implications are hypotheses. Lecture 38 pp. 1–3 and Lab 3 p. 1. | Provide native layout, stackup, fab rules and chosen insulation standard/requirements. Inspect physical forward and return paths, live/access/chassis domains, creepage and clearance rules, slots and coating assumptions, then run board checks and measure switching waveforms. |
| Thermal readiness is unsubstantiated. FET, snubber, film-cap ESR/ripple, rectifier, magnetics and shared enclosure heat need corner-dependent loss estimates and a junction-to-ambient path; a 5 µF value alone says nothing about capacitor voltage, ripple or temperature margin. | Component values given; thermal concern is hypothesis. Lectures 15 pp. 1–4 and 16 pp. 2–4. | Provide component data, switching frequency and waveform, duty, ambient, cooling geometry and enclosure. Calculate steady/transient losses and temperature with shared heat paths; instrument representative builds at the governing corners. |
| The spreadsheet's “100% pass” under assumed pan distributions is conditional on those assumptions. It gives no evidence about no pan, atypical pan, misplacement, metallic utensils, ageing, line tolerance or sensor failure. | Given spreadsheet claim; coverage concern is an inference from Lecture 35's Q/load sensitivity. | Inspect model assumptions, selected operating envelope and actual test samples. Use deterministic boundary/fault cases plus representative measured pan/load data, recording conditions and observed maxima. |

The 5 µF bus holds energy proportional to voltage squared; since the bus voltage and discharge path are unspecified, its energy and safe discharge time remain open. Conducted/radiated EMI and assembly/test access also remain open; a native board and enclosure package are needed before these can be assessed (Lectures 28 and 30; 2.996 Lab 3). I would record each finding against the actual revision once supplied. No MIT course certifies this appliance.

## Usefulness and failure review

The skill changes the decision from apparent readiness based on nominal ratings, a fast comparator, CAD output and a perfect spreadsheet score to an evidence-gated **no order**. It forces topology-specific current and return paths, a complete trip-to-safe-state chain, thermal corners, insulation requirements and a boundary test matrix. It also preserves provenance by asking for an exact artifact revision.

The answer above makes no numeric limit or pass claim. It avoids treating MOV nominal clamp as a hard ceiling, comparator delay as total shutdown time, zero overlap as clearance compliance, or an assumed distribution as full coverage. It correctly labels fault paths as hypotheses until the circuit is inspected. Course citations are attached to the physical principle; the product-specific checks are engineering extensions.

Potential gaps in the skill: it does not explicitly call out MOV fuse coordination/end-of-life, residual resonant energy and freewheel after gate disable, the full sense-to-turnoff delay chain, isolator CMTI, or deterministic stress cases that defeat a probabilistic pan model. The generic fault paragraph covers most of these in spirit, but a model could easily skip them. The example output table also labels a layout observation while the layout may be missing; its own opening rule prevents this, but the example could use a missing-artifact row. The reference file duplicates some lecture links across sections; a little verbosity, no substantive overreach.

Minimal corrections suggested:

1. In **Electrical stress and fault path**, explicitly ask for protection timing from sensing through actual current extinction, including remaining bus/tank energy and passive current paths; mention protection component failure and coordination.
2. In the same section, require a deterministic boundary/fault matrix alongside any statistical load/pan claim.
3. In **Mixed domains**, clarify that CAD overlap and default DRC settings cannot establish the applicable insulation system or minimum separation.
4. Add one missing-native-layout example row to **Report and evidence**, labeled “hypothesis / artifact missing,” so the example cannot be copied as an observed finding.

## Pass/fail rubric

| Criterion | Result | Reason |
|---|---|---|
| Source fidelity | Pass | Eight claims sampled against raw PDFs; no false transfer of classroom numeric limits. |
| Grounding in supplied artifacts | Pass | Skill requires actual revision and evidence classes; forward answer did not invent a layout or part specification. |
| Correct release decision on test case | Pass | Blocks order release with clear, minimal evidence needed. |
| Safety mechanism coverage | Conditional pass | Core categories present; the four mechanisms above should be more explicit for reliable agent use. |
| Actionability and brevity | Pass | Findings identify specific blocked decisions and verifications. |

**Overall: pass with targeted edits.** This is useful as a review skill, not a certification procedure or an autonomous claim that Temper is ready to build.
