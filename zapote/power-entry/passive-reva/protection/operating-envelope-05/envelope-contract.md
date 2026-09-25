# Operating-envelope contract: evidence baseline and open derivations

Status: research baseline established; full electrical envelope not yet derived.
Hardware: unavailable. This contract does not authorize a powered procedure.
Source branch:codex/power-entry-pkgs-1-4, base5dde29ab3; current standalone
protection source identity is bound by the immutable f2-shutdown-04 receipt.

## Authority

The passive-reva milestone controls the product baseline. Current electrical
source controls installed/configured parts and connections. Manufacturer data
controls its own exact-part conditions. Experiment04 controls only observations
under its declared model. Legacy top-level doubler values, stale manifests and
uncited firmware constants do not override the current passive milestone.

| Quantity | Established value or status | Type / authority | Remaining task |
|---|---|---|---|
| Mains |120VAC nominal;108–132VAC | Requirement; `zapote/power-entry/passive-reva/MILESTONE.md:17` | Source impedance, line fault and transient contract |
| Line current |≤15Arms | Requirement; `zapote/power-entry/INTERFACES.md:13–15` | Implement low-line power foldback and verify actual RMS waveform |
| Power |1800W nominal AC-input class; no accepted continuous/burst output rating | Product class, not output guarantee; same interface | Derive permitted output from voltage, PF, efficiency and thermal duration |
| Line frequency |60Hz used in existing calculations | Model assumption; `zapote/power-entry/evidence/pfc-control-calculation.md:14–18` | Record selected range before claiming frequency coverage |
| PFC bus nominal |389.615V single bus | Interface/source configuration; `zapote/power-entry/INTERFACES.md:11,22–26` | Derive normal ripple/tolerance and allowed min/max; reject legacy340V split-bus transfer |
| Switching frequency |16.2kΩ programming; ~130kHz design point | Source configuration and conditional calculation | Use actual controller frequency/tolerance;04's100kHz PWM is a test stimulus |
| Boost inductor |Würth760800301,180µH nominal | Selected source part | Obtain applicable L(I,T), core/copper loss and saturation behavior |
| Peak fault current |Unknown | No physical maximum established; conditional PCL analysis exists in02 | Combine threshold, shunt/filter delay, controller delay and L(I,T); compare with allowable energy region |
| VD diode-side voltage |Final operating/fault ceiling unresolved |04's500V is a provisional local-node screen | Derive from local cap and semiconductor limits, duration, temperature and parasitics |
| VB bulk-bank voltage |Four450V-rated electrolytics; allowable system waveform not established | Component rating, not allowed450V continuous system target | Apply temperature/ripple/surge conditions and margin independently of VD |
| VDS / diode reverse |Selected650V-rated parts | Component absolute/blocking ratings under exact datasheet conditions | Bound switching/fault overshoot and duration; bus voltage alone is insufficient |
| VGS |Exact-part limits and actual load required | ST ±25V absolute rating; not recommended drive swing | Include positive/negative overshoot, common-source L, gate charge and driver load |
| Local reservoir |TDKB32776P6226K00022µF±10%,630V candidate | Proposed part; not fitted to retained baseline | Validate effectiveC/ESR/ESL/ripple/temp;19.8µF is only nominal tolerance floor |
| F2 |MersenA70QS50-14F withUS141/Z331153 candidate | Proposed interrupter/installation | Actual DC capacitor-discharge clearing, arc and let-through/withstand evidence |
| Auxiliary15V |14.25–15.75V proposed run range; producer not qualified | Prior interface proposal, not an established port waveform | Close startup/dropout/load/OV envelope and connection protection |
| Logic5V |Required external port in revisionB; producer absent | Circuit interface | Choose/bound producer; composite allowed run range is constrained by all powered parts |
| Aux overvoltage |IRM proposal OVP can extend to20.25V; UCC27511A recommended max18V, absolute20V | Concrete producer/receiver mismatch from official source conditions | Define prevention/clamping/disconnect disposition; an undervoltage comparator cannot close OV |
| Shutdown time |Full worst-case bound unknown;2µs provisional target |04 observes0.749/1.536µs isolated and0.870µs doubled-load plant turnoff | Derive allowable delay from A3/A4 and validate actual loaded/corner response |
| Temperature |40°C cooling-inlet target | Requirement; passive-reva milestone:20–21 | Define ambient/case/junction/PCB limits and exact installed heat/loss budget separately |

Local source citations and official manufacturer URLs are expanded in
`research/requirements.md` and `research/components.md`. Physical part ratings
are constraints on derivation; none is silently promoted to a product limit.

## Quantity and node rules

- Keep VAC RMS, rectified instantaneous line voltage, bus DC and switching peaks
  separate.15Arms line current, nominal40A controller PCL and a51A simulated
  F2-opening current constrain different quantities.
- Distinguish VD local reservoir from VB electrolytic bank. F2 opening isolates
  them; only VD's local capacitance receives credit for post-open absorption.
- Track switch channel turnoff separately from remaining passive/diode current.
- Keep maximum trip thresholds paired with applicable delays, slopes, overdrive,
  temperature and initial conditions. Typical propagation is not a maximum.
- The current04 result set proves conditional model behavior at selected points.
  It does not establish a bound between points or at new controller states.
- Firmware40/50A flags are not accepted PFC operating limits. Legacy150µH/340V
  assumptions are not current parts or bus requirements.

## Open rows that decide the next implementation

1. **Node-voltage and current/energy region.** Derive maximum admissible current
   and shutdown delay as functions of effective C, L trajectory, source inflow
   and allowed VD/VDS/VB waveforms. Retain conditional curves where physical
   inputs are missing; do not fill unknown fields with the test values.
2. **Actual current limiting and controller retry.** Establish applicable
   UCC28180 PCL/standby/OVP timing and consistent parameter corners; obtain
   magnetic evidence or identify a separately bounded design solution.
3. **Supply producers and fault envelope.** Resolve5V generation and15V OV
   handling, real ARM/PERMIT isolation/protocol, and partial-power failure states.
4. **Steady and transient power.** Establish low-line foldback and load startup
   behavior, including output power after losses and required duration.
5. **Whole assembly and short faults.** Keep F1 line interruption, F2 bank
   interruption, local energy outside F2 and installed cooling as separate
   obligations. Gate shutdown cannot open a failed-short power switch.

These rows are implementation inputs, not reasons to restart general research.
Each has an explicit owner and completion test in the plan. The next model work
can proceed conditionally, with unresolved applicability recorded rather than
presented as a pass.
