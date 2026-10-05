"""Render the D27 source reconciliation and audit all pinned file/line citations."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'zapote').is_dir())
BASE = '212c497f9e762f87ed59ba38842dfaeedc7aa538'
PS = 'zapote/power-stage-120v/'
P = PS + 'prototype-closure/'
R = PS + 'validation-results/01-switching-parasitics/'
ALIASES = {
    'D': PS+'DECISIONS.md', 'S': R+'STATUS.md', 'F': R+'FINDINGS.md',
    'H': 'docs/hardware/power-section-120v/POWER-SECTION.md',
    'LOSS': 'docs/hardware/power-section-120v/LOSS-REFACTOR.md',
    'COIL': 'docs/hardware/power-section-120v/COIL-MC.md',
    'P': P+'README.md', 'C': P+'round2/cooling/README.md',
    'CI': P+'round2/cooling/interface.json', 'CB': P+'round2/cooling/build_revision.py',
    'E': P+'round2/d22/README.md', 'T': P+'round2/d17/README.md',
    'OLD': P+'power/README.md', 'MFG': P+'manufacturing/first-unit.md',
    'PK': P+'round3/packaging/README.md', 'IN': P+'round3/inlet/README.md',
    'CE': P+'round3/control-energy/README.md', 'AUD': P+'round3/integration/source-audit.md',
    'FW': P+'round4/firmware/README.md', 'SUP': P+'round4/supervisor/README.md',
    'FIELD': P+'round4/fields/README.md', 'JOIN': P+'round4/coupled-model/README.md',
    'R5FW': P+'round5/firmware/README.md', 'PWM': P+'round5/firmware/esp32/mcpwm_target.c',
    'PINS': P+'round5/firmware/esp32/pins.h', 'BOARD': P+'round5/boards/README.md',
    'PROT': P+'round5/protection/README.md', 'MODEL': P+'round5/model/RESULTS.md',
    'INT': P+'round5/integration/README.md',
    'D18': R+'round17/delegation/out-D18/README.md',
    'D20': R+'round17/delegation/out-D20/CONTROLLER-REQUIREMENTS.md',
}
ROWS: list[dict] = []


def row(topic: str, kind: str, finding: str, left: str, right: str) -> None:
    ROWS.append(dict(id=f'R{len(ROWS)+1:02}', topic=topic, classification=kind,
                     finding=finding, prototype=left.split(), decisions=right.split()))


row('Board outline', 'AGREES', 'Current cooling imports native19; its 240 × 160 mm allocation matches the revised D1 outline. This is an envelope match, not a fabrication release.', 'CI:43-53 C:3', 'D:11')
row('Layer/fabricator basis', 'ONE-SIDED', 'D3 specifies the native power-board JLC041622-7628 stackup, copper and CTI verification. The prototype manufacturing hold does not requalify it; round5’s new four-layer supervisor is a different board.', 'MFG:12 BOARD:7-13', 'D:13')
row('Mains/coil orientation', 'AGREES', 'Cooling’s right intake and left outlet preserve D6’s coil-right/mains-left ordering. Coordinate directions are the component-side convention, not the rear-panel view.', 'C:11 CI:663-715', 'D:12 D:16 D18:59')
row('Shared sink and PE', 'AGREES', 'Separate main/sink PE studs and insulated live device interfaces implement the shared PE-bonded sink architecture; removable mechanical fasteners are not its sole bond.', 'C:7-14', 'D:12 D:49-51')
row('MOS interface and insulator', 'AGREES', 'Ceramic/shim/compound candidates preserve ≤1 °C/W and electrical isolation as requirements; they do not revive rejected K-10/400 or claim qualified contact resistance.', 'C:7-10 C:18-24 C:36', 'D:66 D:15')
row('Cooling thermal allocation', 'AGREES', 'Prototype repeats ≤0.15 °C/W sink, ≥20 CFM and 50 °C fin inlet. D18’s bridge/interface loss assumptions remain conditional.', 'C:36', 'D:66 D18:75-77')
row('Duct direction and isolation', 'AGREES', 'Closed right-push/left-pull routing follows D18; actual sealing, recirculation and exclusion of coil/controller air remain assembly tests.', 'C:11 C:38', 'D:66 D18:59')
row('Fan identity and supply rating', 'ONE-SIDED', 'Both use DC0602512W2B-BT0. Prototype records an unresolved manufacturer-page 6.48 W versus catalog 11.4 W discrepancy and retains 22.8 W/two-fan planning. Do not silently treat either as a reconciled ordered-part rating.', 'C:36', 'D18:83 D:66')
row('Dedicated fan power', 'AGREES', 'Dedicated fan supply required; PS1/J4.1 cannot supply the two catalog fans plus controller. The prototype instruction is not a selected/verified 12 V supply design.', 'C:36', 'D:66 D18:83')
row('Sink selection and size', 'ONE-SIDED', 'Prototype allocates a custom 200 mm sink. D18 provides catalog examples, not a selected cut-down assembly. No curve establishes the custom sink’s thermal target; the geometric results below cannot supply one.', 'C:11 C:36 CI:61-88', 'D:66 D18:81-87')
row('Pressure, exhaust fan temperature and mounting', 'ONE-SIDED', 'Prototype adds leg sleeves, narrow bypasses, pressure-loss and pull-fan ambient screens. These refine packaging without proving D18’s delivered-flow or mounting-temperature acceptance.', 'C:36-38', 'D18:77 D18:87')
row('R5 orderable identity and Kelvin-positive net', 'SUPERSEDES', 'The corrected WSK25121L000FEA / T2.21 / ocp_kelvin_p native19 record supersedes the hardware overview’s old WSK2512R0010FEA and pad-2 LEG_RET wording. Refresh that prose/BOM handoff before procurement; this report makes no edit.', 'H:75-77 H:140 T:11-27', 'D:66 F:35')
row('R5 sustained rating and local ambient', 'ONE-SIDED', 'D18/decision retain 1 mΩ, 1 W only with the conditional sustained envelope and ≤100 °C local ambient; ≥2 W needs review above that. Prototype cold packaging and current-retune hold do not demonstrate this local ambient.', 'C:36-38 H:140-142 MFG:11', 'D:66 D18:89-93')
row('Native19 copper versus native18 carry-over', 'SUPERSEDES', 'Native19 R5/Kelvin copper changes supersede the native18-only identical-copper inference. Round17 already records changed A/B regions and an A verdict carry-over; do not transfer D4’s native18 approval mechanically to new copper.', 'T:11-27 P:15-20', 'D:64 D:66 F:35')
row('R9/R17 selected parts', 'AGREES', '49.9 kΩ ±0.1% remains selected. The prototype’s historical 348 ns reproduction is explicitly an instrument check, not permission to restore 39 kΩ.', 'H:130 OLD:7', 'D:27 D:60 F:21')
row('Dead-time reference planes', 'AGREES', 'Conditional all-off delay is not complementary dead time; 391–498 ns command-gap results cannot be compared as if they were die-VGS or loaded driver crossings. D26’s gate-crossing result is not a reversal of F7.', 'OLD:9-12 FW:83-86', 'D:74 D20:71 D20:76')
row('Hot off-gate threshold', 'AGREES', 'The conditional turnoff experiment uses 1.9 V and reports rebound/exceedance without claiming population-hot or survival qualification.', 'OLD:19-29', 'F:19 S:26')
row('S4 recovery remains unresolved', 'ONE-SIDED', 'Prototype joined/catch models omit or simplify the recovery physics and cannot close D24’s named waveform measurement. Carry the <1.9 V off-gate and ≤520 V die-VDS S4 gate into the prototype test plan.', 'JOIN:23 MODEL:56-60', 'D:72 F:16')
row('Negative-bias reserve', 'ONE-SIDED', 'Prototype native19/catch work does not implement F6. Returned-energy capture cannot substitute for its local gate-drive remedy; F6 remains conditional on the S4 measurement, including its unresolved hot model.', 'P:15-20 CE:13', 'F:20 D:72')
row('Driver approximation', 'AGREES', 'Prototype’s forced-current work explicitly inherits the typical-resistance driver. D23/D26 do not qualify a replacement; retain model limitations and the prescribed physical timing measurements.', 'OLD:9 OLD:29', 'D:74 F:32 F:33')
row('Controller complementary gap', 'ONE-SIDED', 'Decision selects 200 ns/16 ticks. Prototype’s 125 ns/50 kHz setup is explicitly inhibited test stimulus, not a conflicting released value. The target must gain an approved production configuration before commissioning.', 'FW:81-86 PWM:88 R5FW:57', 'D:68 D20:72')
row('Shared timer and four outputs', 'AGREES', 'One timer, one operator per leg and four complementary pins match the structural allocation. Pin assignment and an inhibited build do not prove physical waveforms.', 'PWM:89-114 PINS:6-9 R5FW:51', 'D:68 D20:67')
row('Inter-leg modulation policy', 'CONTRADICTS', 'Decision fixes legs 180° apart at 50% duty; prototype’s intended fixed-frequency control varies phase over 0..half a period. These are different operating policies. Resolution C1 below requires an explicit owner choice and revalidation.', 'FW:56-73 PWM:48-54', 'D:68 D20:67-69')
row('Live frequency/phase updates', 'ONE-SIDED', 'Decision requires timer-zero shadow updates. Prototype target changes comparator settings only after inhibit/stop and rejects period/deadtime changes; its own README leaves live atomic control unimplemented. A disabled setup is not evidence of the required live update path.', 'PWM:49-78 R5FW:60-65', 'D:68 D20:73-75')
row('Inductive-side CT phase inhibit', 'ONE-SIDED', 'D20/decision require tank-current phase qualification. Prototype’s hypothetical pan map/fast-capture proposal and incomplete target do not supply a measured phase margin or end-to-end CT_ZC inhibit.', 'FW:153-166 R5FW:103-116', 'D:68 D20:69 D20:99')
row('Burst start/stop', 'ONE-SIDED', 'Prototype deliberately defers/inhibits burst. Decision requires both legs off at each boundary when implemented; disabled burst is neither that acceptance test nor authorization to remove the requirement.', 'CE:11 FW:70-73', 'D:68 D20:68')
row('PWM failure and pull state', 'CONTRADICTS', 'Prototype inhibit resets then drives each GPIO but never disables pull-up/enables pull-down; early init failures return without invoking it. This misses D25’s all-path final pin state. Resolution C2 below covers this separate implementation, not just draft #1643.', 'PWM:21-34 PWM:82-120', 'D:72 F:22')
row('External PWM pull-downs', 'ONE-SIDED', 'Decision adds ≤10 kΩ external pull-down per controller PWM. The prototype ESP32 carrier/pin proposal supplies no accepted schematic/BOM evidence for those four resistors; gate-source 10 kΩ on the power board is not this requirement.', 'R5FW:45-49 PINS:6-9 H:81-83', 'D:72 D20:65 D20:75')
row('PERMIT ownership and failure interlock', 'AGREES', 'Prototype suppresses requests by default and requires a hardware permission chain; J4.9 must have one producer. The proposed intercept explicitly requires disconnecting the old producer, not paralleling push-pull outputs.', 'PWM:35-40 SUP:35 FW:90-95', 'D:72 D20:55 D20:79')
row('STM32 versus ESP32', 'ONE-SIDED', 'Prototype adds an upstream STM32 electrical supervisor; ESP32 remains the bridge/cooking target. This is a new supervisory partition, not evidence that D20’s ESP32 controller requirements vanished.', 'SUP:15 R5FW:3-10', 'D:68 S:86 D20:101')
row('J4 bus receiver/ADC identity', 'ONE-SIDED', 'Decision requires OPA2388 differential receiver on unshared GPIO2/ADC1_CH1. Prototype’s separate AMC3330/ADS supervisor channel and ESP pin contract do not implement or expressly supersede that receiver. Keep the D11 requirement open.', 'SUP:11 SUP:59 R5FW:17-18 PINS:1-22', 'D:62 D20:84-87')
row('Bus sample rate and freshness', 'ONE-SIDED', 'Native J4 receiver needs 20 ksample/s and 150 µs stale deadline. Supervisor ADS at 3906.25 sample/s and fast-capture 500 µs-age proposal concern different channels; neither closes the native bus acquisition deadline.', 'R5FW:17-18 R5FW:77-85', 'D:62 D:68 D20:88 D20:90')
row('Bus calibrated thresholds and recovery', 'ONE-SIDED', 'D11’s 1.210 V latch, <100 mV invalid and 1.100 V manual re-arm remain native receiver requirements. Prototype bus/catch analog guards and supervisory reset sequence use other reference planes; no demonstrated substitution exists.', 'SUP:59-67 FW:20-55', 'D:62 D:68 D20:89-94')
row('Independent wide-range bus sensing', 'ONE-SIDED', 'Prototype adds AUX-powered wide-range sensing for discharge/catch qualification because the J4 AMC1311 becomes nonlinear near 240 V and loses HOT5 power. This complements, rather than extends, D11’s specified linear range.', 'AUD:24-36 SUP:59', 'D:62 D20:83')
row('Independent native U7 OVP', 'AGREES', 'Native 280 V OVP remains. The proposed 230 V bus / 250 V catch guards are additional study protection, not a retune of U7 or a claim of linear J4 sensing to 280 V.', 'AUD:33-36 SUP:63 H:39', 'D:62 D20:94-95')
row('J4 power direction and backfeed', 'AGREES', 'J4.1 is native PS1 output; upstream AUX must not be paralleled onto it. Separate supervisor/controller rails and named interface returns require their own power budget.', 'AUD:11-14 FW:90-95', 'D20:47-50 D20:64')
row('Tank CT local burden/clamps', 'AGREES', 'Hardware overview retains local CT termination and SELV CT_ZC/CT_MON; new line/proof CT cards operate at line frequency and must not replace the tank CT capture path.', 'H:85-88 H:99-105 BOARD:38', 'D:19 D:21 D20:96-99')
row('CT_MON receiver and digital capture', 'ONE-SIDED', 'Prototype fast-capture FPGA/AD7380 is a proposed implementation, not the qualified high-impedance CT_MON receiver, wiring and CT_ZC behavior required by D20.', 'R5FW:97-116', 'D20:97-99')
row('Physical timing evidence', 'AGREES', 'Inhibited builds, host tests and source capture contracts do not prove driver/gate timing. Both lines retain hardware waveform and fault-chain validation.', 'R5FW:160-182 MFG:14-16', 'D:74 D20:76 D20:101')
row('D22 filter allocation and topology', 'AGREES', 'Prototype carries D22’s separate damped DM+CM module ahead of native filtering and preserves the 110 × 80 × 50 mm body allocation. Fuse/disconnect/precharge are outside that volume.', 'C:13 E:25 IN:31-46 PK:12', 'D:70')
row('EMI margin transfer to installed system', 'SUPERSEDES', 'Prototype’s long PE route/new assembly invalidates inheritance of the old coupling assumptions. D22’s converged 9.28 dB model result is historical conditional evidence, not an installed margin; rerun coupled CM/DM with actual wiring.', 'C:14 E:3 E:29', 'D:70 S:85')
row('D22 heat and inlet load law', 'SUPERSEDES', 'Round2 tests expose startup/damper-open peaks and a constant-power diagnostic that exceeds the 8 W/15 A screens. This adds coupled-system limits beyond D22’s periodic RF study; it does not refute the original calculation under its own assumptions.', 'E:15-19 E:33-41', 'D:70')
row('D22 placement outside exhaust/FEM', 'AGREES', 'The declared module pose implements the exclusion requirement. D27’s new nominal fit receipt below finds no intersection, but the 0.20 mm duct-wall gap has no tolerance or insulation allowance.', 'CI:620-630 C:13', 'D:70 S:97-111')
row('Filter wire corridor and installed coupling', 'ONE-SIDED', 'Decision also excludes the module wiring corridor from both leg regions. Cold allocation omits final wire bends/terminations; module-only separation cannot close wiring or installed field coupling.', 'C:30 C:38', 'D:70 S:97-111')
row('PE functional versus protective bonds', 'AGREES', 'Native R38’s single functional bond and direct chassis PE plus separate PCB/sink branches have different roles. Prototype calls for explicit harness/bond review; extra instrument or AUX bonds cannot be assumed harmless.', 'H:67-68 C:14 PK:28', 'D:15 D:49-51 D20:66')
row('Control load law for D22', 'ONE-SIDED', 'Prototype introduces completed-line-cycle conductance control with inlet current limiting; the joined model’s RMS surrogate is not executable closed-loop firmware. Round17’s filter allocation does not choose this law or its pan map.', 'FW:62-66 JOIN:25', 'D:70 D20:68 S:85')
row('Precharge and external inlet pod', 'ONE-SIDED', 'Independent AUX, redundant source contacts, bypass/proof and manual restart are new prototype hardware. Round17 D17 remains a fault-chain hold; the original filter envelope never reserved this hardware.', 'IN:3-10 IN:31-46 PK:11-24', 'S:82 D20:80 D:70')
row('Precharge resistor revision', 'ONE-SIDED', 'Prototype round5 PC125 selects two HS40025RJ branches and their cutoffs, superseding its own older 11 Ω study. No DECISIONS/round17 row adopts or qualifies this external circuit; do not copy older round3 values into a build.', 'PROT:9-16 SUP:55', 'S:82 D20:80')
row('Source opening versus gate shutdown', 'AGREES', 'Mechanical opening stops new line energy after a delay; it cannot establish semiconductor survival or eliminate already stored tank/catch energy. Prototype and D20 keep the complete fault-to-gate chain open.', 'SUP:10 JOIN:27-31 PROT:125-150', 'D20:80 S:82')
row('Catch accessory and return node', 'ONE-SIDED', 'Prototype adds diode-isolated catch storage on J8/J10, retaining D3. DECISIONS approves the original TVS/bulk/link topology, not the accessory’s new fuse, diode, cable inductance or fault-energy rating.', 'CE:13-14 AUD:15 PROT:83-101', 'D:38-52 S:82')
row('Finite stored energy and reachability', 'SUPERSEDES', 'Prototype finite-energy and coupled models extend earlier stiff-source/all-off experiments, but keep initial states, source arc, delay and catcher inductance conditional. They do not turn D17 into a survival bound.', 'T:39-68 MODEL:17-18 MODEL:29-60', 'S:82 D20:80')
row('OCP current and retune hold', 'AGREES', '45 A is not an approved operating limit; shunt/CT threshold intervals and dynamic gate-off remain open. Prototype does not silently raise the native trip by treating a diagnostic peak as allowable.', 'H:12-18 T:72-89 OLD:29 COIL:10-19', 'D:14 D:19 S:82 D20:80')
row('Both leg field solutions', 'SUPERSEDES', 'Prototype has finite-height native19 A and B four-port solutions with independent pair evidence. This advances the blanket “leg B queued” progress statement; it does not supply the outstanding native17→19 B carry-over or full best-matrix verdict campaign.', 'FIELD:3 FIELD:22-55', 'S:8-10 S:78 F:35')
row('Matrix fidelity and reference geometry', 'AGREES', 'Prototype finite-height/coarse solutions are not substitutes for round17’s best reference-geometry extrapolation. Bulk/local partial matrices cannot be spliced into a qualified full coupled matrix; mesh/self-L limits remain.', 'FIELD:67-109 MODEL:56-60', 'S:35 F:17 F:28-30 F:34')
row('Capacitor ESL stale finding', 'SUPERSEDES', 'Prototype already uses the D7-backed 1.06 nH local value with sensitivity; current STATUS records verified local/bulk values. FINDINGS M4’s licence/unknown-value wording is stale. Value availability does not remove installed package/routing uncertainty.', 'OLD:7 OLD:15', 'F:31 S:91')
row('Aborts and incomplete simulations', 'AGREES', 'Prototype keeps incomplete batches and failed refinement separate from completed diagnostic rows. Round17’s solver fixes and D23/D26 limits likewise cannot convert an aborted case into a pass.', 'JOIN:17-19 MODEL:5 FIELD:3', 'F:20 F:36 D:74')
row('Joined model versus device-qualified simulation', 'ONE-SIDED', 'Prototype joins inlet, precharge, energy and control through reduced models; D2’s local transistor/matrix verdicts cannot validate the omitted global physics. Neither line supplies the complete executable-firmware, nonlinear, cross-leg installed model.', 'JOIN:21-31 MODEL:47-60', 'F:17 F:32 F:35 S:82')
row('Coil/pan and current envelope', 'ONE-SIDED', 'Prototype explicitly retains measured coil/pan characterization and approved current limits as holds. Round17’s selected transient currents are scenarios, not a replacement measured cooking map.', 'MFG:9-16 COIL:106-120', 'S:17-26 D20:68')
row('Original TVS and bulk/local capacitors', 'AGREES', 'Hardware overview preserves MRT130KP295CV, TDK bulk/local parts and HV_RET returns through R5 current pads. The added catch does not approve moving those returns onto LEG_RET.', 'H:75-83 H:136-139 CE:13', 'D:38-40 D:14')
row('Resonant capacitor bank', 'AGREES', 'Retained CDE bank is still not high-frequency/hot/pulse qualified by these records. Prototype’s diagnostic tank and model limits do not select a replacement bank.', 'H:85-88 H:133 MODEL:5', 'D:41 D20:101')
row('Both bring-up links and terminals', 'AGREES', 'Both rectifier rails are removable; rectifier-side studs remain live with mains present. Catch/accessory return belongs to HV_RET, not a Kelvin node. PE and coil terminals retain separate functions.', 'H:63-77 H:158-159 AUD:15', 'D:42-52')
row('Protection diode/resistor revision', 'ONE-SIDED', 'Decision explicitly adopts BAS116H and faster PERMIT/DIS resistors. Prototype native19 import/loaded-interlock model is related evidence, not a new authorized value change or proof of end-to-end delay.', 'P:15-20 T:72-89', 'D:21 D20:80')
row('C1/C2 physical part correction', 'AGREES', 'Hardware overview names R463N410000N1M; decision records the corrected pitch and retained placement. Added filter geometry must not revive the old wider-pitch part.', 'H:152', 'D:23')
row('PTH land policy and fabrication hold', 'ONE-SIDED', 'Native17’s outer-land correction/neutral narrowing remain decision-controlled manufacturing facts. Prototype imported native19 and retained fab hold; it does not demonstrate a new independent remeasurement of those screens.', 'MFG:12 P:54-58', 'D:25 D:14')
row('Insulation and nominal gaps', 'AGREES', 'Prototype ceramic overhangs, bare nominal spacing and board DRC are not insulation approval. The 8 mm/group-IIIa placement basis and unresolved package/high-frequency rules still apply; no automatic waiver follows from a collision-free STEP.', 'C:22 BOARD:34 BOARD:46-50', 'D:15 D:50-51')
row('Additional supervisor boards and pod fit', 'ONE-SIDED', 'New nine-board supervision adds a 275 × 240 mm central board, explicitly not a drop-in fit for the older 115 × 100 mm control reservation. This new packaging work has no matching DECISIONS adoption; R4 filter fit cannot close it.', 'BOARD:3-13 PK:22', 'D:70 D20:101')
row('Bring-up conditions and release authority', 'AGREES', 'D4 asks for loaded OCP-node and all-four-VGS measurements before increasing current. Prototype manufacturing/electrical holds retain those measurements and do not convert source integration into build permission.', 'MFG:11-17 P:54-74', 'D:14 D:19 D20:101')
row('Historical loss estimates', 'SUPERSEDES', 'Hardware/LOSS comparison explicitly labels inherited resistance/switching proxies. D18’s round17-based conditional loss allocation is the cooling comparison basis; historical efficiency/loss tables do not qualify the new sink.', 'LOSS:11-16 H:47-53', 'D:66 D18:101')
row('Common-clock capture versus software state', 'AGREES', 'Prototype rejects missing/stale captures and admits that its physical capture hardware/target path is incomplete. D20 forbids using requested/cached timing as hardware proof.', 'FW:56-61 R5FW:160-182', 'D20:75-76 F:15')
row('Round17 test/cache identity defects', 'ONE-SIDED', 'Closed grid/cache/port/crop bugs describe round17’s particular harness. Prototype has its own hash, finite-data and incomplete-run checks; those do not prove immunity to every listed historical defect. No design choice is reversed by these software rows.', 'JOIN:15-19 FIELD:49-55', 'F:43-55')
row('Signed mutual verification', 'AGREES', 'Prototype’s independent pair solve is the appropriate type of external excitation check, consistent with round17’s signed-mutual requirement. It validates the named pair/case only.', 'FIELD:49-55', 'F:37 F:54')
row('Legacy status/board-count prose', 'SUPERSEDES', 'Prototype’s current native19 inventory is 142/89; old native18 135/83 and historical packet counts in overview tables are provenance, not the current assembly census. Refresh source-pinned handoffs, not historical receipts.', 'P:15-20 P:34-46 H:20 H:169-172', 'D:66 F:35')
row('S1/S2/S3 evidence scope', 'AGREES', 'Prototype distinguishes conditional all-off/energy experiments from repetitive commutation/ZVS tests. Nominal F7 S1/S2 passes and light-load ZVS failures cannot be generalized to its variable-phase pan/control envelope.', 'OLD:7-12 JOIN:23-25', 'S:17-21 F:18 F:21')
row('Fault latches, restart and independent timers', 'ONE-SIDED', 'Prototype chooses START/RESET/STOP, discharge admission, watchdog and independent precharge/proof timeouts. D20’s independent hardware inhibit and reset requirements constrain this design but do not approve those particular thresholds or budgets.', 'FW:20-55 SUP:43-51', 'D20:65 D20:79-80')
row('Native bus accuracy and harness qualification', 'ONE-SIDED', 'D11’s ±6%, ±5 V, ±250 µs and receiver/harness/calibration acceptance remain outstanding for the native bus pair. AMC3330 card capacitance statements apply to a different interface and cannot satisfy AMC1311/OPA2388 acceptance by analogy.', 'BOARD:36 SUP:59 R5FW:77-85', 'D:62 D20:82-95')
row('Remaining J4 harness/supply/thermal interfaces', 'ONE-SIDED', 'Prototype adds an isolated JCTRL and candidate carrier but does not supply a released D20 mating-face harness, total startup/rail budget, instrument-bond inventory, RTD and interlock acceptance packet. Separate sensor-card progress cannot close these controller requirements.', 'FW:88-95 R5FW:45-49 BOARD:46-50', 'D20:47-66 D20:100-101')


row('Superseded 39 kΩ external timing request', 'SUPERSEDES', 'FINDINGS/STATUS still request TI limits at the fitted 39 kΩ. Prototype and the accepted native18/19 identity use precision 49.9 kΩ. Refresh the external request to the selected part/reference planes; physical timing remains required.', 'H:130 OLD:7', 'F:62 S:93 D:60 D:74')
row('Extrapolation progress wording', 'SUPERSEDES', 'FINDINGS M2 still asks for the fine 1/2/3 mm parabola, while STATUS already names that corrected best matrix. Prototype coarse/finite-height results do not supply an excuse to replace it; reconcile the stale progress text with the current matrix provenance.', 'FIELD:67-74', 'F:29 S:16 S:35-37')
# Add repeated STATUS/FINDINGS statements to the same subject rather than count them twice.
SUPPLEMENTS = {
 'R01': 'D:3-7', 'R67': 'D:29-34 D:54-58',
 'R54': 'S:16 S:36-38 S:42-49 S:62-69',
 'R17': 'S:27-29', 'R55': 'S:39 S:72 F:65',
 'R56': 'S:40', 'R71': 'S:53-59',
 'R18': 'S:70 F:61', 'R39': 'S:71 F:63',
 'R70': 'S:79 S:116-122', 'R19': 'S:80 F:64',
 'R15': 'S:81 F:15', 'R06': 'S:83', 'R41': 'S:84',
 'R27': 'S:87', 'R20': 'S:88-89', 'R31': 'S:92',
 'R43': 'S:112',
}
for item in ROWS:
    item['decisions'] += SUPPLEMENTS.get(item['id'], '').split()


def main() -> None:
    (HERE/'inventory-status.json').write_text(json.dumps({'status': 'INCOMPLETE'})+'\n')
    audit = []
    table = ['## Source overlap inventory', '',
             'Each row is one reconciled subject, not one file or component. ONE-SIDED means the cited comparison scope has no matching adopted choice or demonstrated implementation; it is not a claim that a word never occurs anywhere in the repository. SUPERSEDES advances evidence/provenance, not owner approval. Sources are pinned to the base commit; ranges preserve their qualifications.', '',
             '| ID / subject | Class | Reconciliation and consequence | Prototype side | Decision / round17 side |',
             '|---|---|---|---|---|']
    cited = set()
    for r in ROWS:
        cells = []
        for side in ('prototype', 'decisions'):
            links = []
            for ref in r[side]:
                alias, interval = ref.split(':')
                path = ALIASES[alias]
                numbers = [int(n) for n in interval.split('-')]
                start, end = numbers[0], numbers[-1]
                source = (ROOT / path).read_text().splitlines()
                if not 1 <= start <= end <= len(source):
                    raise ValueError(f'Invalid citation {r["id"]}: {ref} ({len(source)} lines)')
                audit.append(dict(row=r['id'], side=side, path=path, start=start, end=end,
                                  excerpt='\n'.join(source[start-1:end])))
                cited.add(path)
                links.append(f'[{ref}](https://github.com/BennetLeff/temper/blob/{BASE}/{path}#L{start}-L{end})')
            cells.append('<br>'.join(links))
        table.append(f'| {r["id"]} {r["topic"]} | **{r["classification"]}** | {r["finding"]} | {cells[0]} | {cells[1]} |')
    table += ['', '### Citation path key', '']
    table += [f'- **{key}** = `{path}`' for key, path in ALIASES.items()]
    preface = (HERE/'REPORT-PREFACE.md').read_text() if (HERE/'REPORT-PREFACE.md').exists() else ''
    (HERE/'README.md').write_text(preface + '\n' + '\n'.join(table)+'\n')
    (HERE/'overlaps.json').write_text(json.dumps(ROWS, indent=2)+'\n')
    (HERE/'citation-audit.json').write_text(json.dumps(audit, indent=2)+'\n')
    files = subprocess.check_output(['git','ls-files',P,'docs/hardware/power-section-120v'], cwd=ROOT, text=True).splitlines()
    inventory = []
    for file in files:
        raw = (ROOT/file).read_bytes()
        inventory.append(dict(path=file, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw),
            treatment='cited primary narrative/code/geometry' if file in cited else
            'packet support: generated design/evidence/source; reviewed by packet and topical search, not a separate independent decision'))
    (HERE/'source-census.json').write_text(json.dumps(inventory, indent=2)+'\n')
    pins = {path: hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in sorted(cited)}
    # A line-by-line coverage index prevents omissions from the decision/status inventories.
    coverage = []
    for alias in ('D','S','F'):
        for number, line in enumerate((ROOT/ALIASES[alias]).read_text().splitlines(),1):
            if not line.strip() or line.startswith(('#','| ---')):
                continue
            covering = sorted({item['row'] for item in audit if item['path']==ALIASES[alias] and item['start']<=number<=item['end']})
            coverage.append(dict(source=alias, line=number, text=line, rows=covering,
                disposition='mapped' if covering else 'context/provenance/method statement; inspect in COVERAGE.md before accepting completeness'))
    (HERE/'coverage-index.json').write_text(json.dumps(coverage, indent=2)+'\n')
    counts = dict(Counter(r['classification'] for r in ROWS))
    result = dict(base=BASE, rows=len(ROWS), classes=counts, citations=len(audit),
                  census_files=len(files), cited_files_sha256=pins)
    (HERE/'inventory-check.json').write_text(json.dumps(result, indent=2)+'\n')
    (HERE/'inventory-status.json').write_text(json.dumps({'status': 'COMPLETE_CITATIONS_VALIDATED', 'rows': len(ROWS)})+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='cited_files_sha256'},indent=2))


if __name__ == '__main__':
    main()
