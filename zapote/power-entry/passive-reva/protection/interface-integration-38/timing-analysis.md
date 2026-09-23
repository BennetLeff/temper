# Rev38 timing analysis — first engineering package

Status: **candidate method recorded; numerical safety acceptance OPEN**. This
document starts the authorized per-fault derivation. It does not turn Rev35/37
fixture timing, typical data, or a simulation screen into an accepted limit.
The complete joined Rev38 circuit, installed power-stage envelope, and
prototype captures do not yet exist. The AVR64DA32, two ISO774xF devices,
source and HOT TPS3431 devices, retained source/HOT memories, dual HOT TPS3890
undervoltage supervisors, four TLV3202 VD/VB channels, and UCC27624/STW driver stage
compile in a partial joined fixture; their presence does not close a
complete response path.

## Acceptance relationship and endpoints

For each gate-interruptible fault class `f`, establish two independent sides:

```text
T_implementation_worst(f) + T_margin(f) <= T_allowable(f)
```

`T_allowable` comes from the affected node's current, voltage, stored energy,
thermal/interconnect limits, operating envelope, and derating. It is never
chosen from the parts' measured speed. `T_implementation_worst` begins at a
defined fault or unfiltered threshold and ends at sustained current cessation
in the controllable STW channel. It includes detection/filtering, qualified
capture, retained clear, isolation when applicable, UCC27624 EN and output,
loaded STW gate discharge, and commutation. State the margin and uncertainty
method separately. A low EN, low gate voltage, or momentary zero-current
sample is not the end point. Gate-off does not mean VD/VB is de-energized.

For a failed-short switch or another fault the gate cannot interrupt, this
inequality is not a valid containment argument. Use F1/F2/interconnect and
stored-energy analyses instead, under their separate scope.

## Selected unexpected-reset candidate

One pre-reset committed, unexpired first START may set RUN at most once while
the current session and independent hardware permission remain valid. It
cannot be generated or retransmitted by rebooted source code. Already-running
and first-start cases share the same execution-loss deadline; accepting START
cannot give the watchdog another interval. A deliberate software restart
requires physical disarm acknowledgement before the restart request.

```text
T_reset_to_off_worst = T_postreset_feed_tail_worst
                     + T_watchdog_worst
                     + T_watchdog_trip_to_current_zero_worst

T_reset_to_off_worst + T_reset_margin
    <= min(T_allowable_first_start, T_allowable_already_running)
```

The feed-tail term is zero only after the actual ESP owner, other core,
bootloader, reset loops, queued writes, and timer/DMA/RMT paths are proved
incapable of another qualifying WDI edge. Otherwise it needs a finite maximum;
an unbounded feed tail fails the candidate. The watchdog term needs selected
CWD effective capacitance, leakage, temperature, SET1/EN state, and device
corners. The final term includes WDO assertion through source-latch clear,
physical PERMIT crossing, HOT retained clear, EN, loaded gate, and sustained
switch-current cessation. Rev35's 119.82–144.98 ms ideal-1-nF device range
is not the complete term and is not an allowable interval.

The two allowable reset times need system hazard analysis of continued PFC
operation and the first START during source execution loss, including relay,
downstream load permission, capacitor energy, and absence of UI control.
The present artifacts give no accepted values for either.

## Retrieved power-stage and component inputs

These are inputs to calculations, with their evidence class preserved. The
retained 54-part baseline has no F2, local reservoir, independent voltage
detector, or UCC27624; those are proposed additions, so their values cannot be
treated as installed measurements.

| Input | Available evidence | Use and unresolved parameter |
| --- | --- | --- |
| Line and load | 108–132 Vac, 15 Arms and 40 °C cooling inlet are requirements; 1.8 kW is an AC-input class. The nominal single bus is 389.615 V. | Obtain source impedance/transients, line and load waveforms, temperature at the parts, permissible PFC continuation and downstream permission before deriving reset or link allowable time. |
| Current path | Baseline UCC28180D, HCSM2818FT10L0 10 mΩ shunt, Würth 760800301 180 µH nominal inductor, STW65N65DM2AG switch and C3D20065D diode. | Actual `L(I,T)` over the fault trajectory, sense-filter initial state and transient current at detector assertion are unknown. The 43 A saturation figure is typical at 30% L reduction, not a guaranteed fault-current bound. |
| PCL threshold | UCC28180 input-referred PCL magnitude: 0.400 V typical, 0.438 V maximum. The F2 audit calculates 44.242 A with 1% shunt initial tolerance and a conditional 44.562 A with assumed −40 to +100 °C shunt body and ISENSE-bias behavior. | These are threshold calculations, not peak current. Obtain applicable controller blanking/PCL-to-gate maximum and shunt temperature/bias applicability or add an independent bounded detector. |
| Voltage/energy nodes | VB has four 450 V-rated electrolytics. A 22 µF ±10%, 630 V VD reservoir and F2 are proposed. VD's 500 V screen and 19.8 µF nominal-tolerance floor are conditional. STW and diode are 650 V-rated. | Derive **separate** derated VD, VB, VDS and diode-reverse limits, actual effective C/ESR/ESL, overshoot, and energy after gate disable. The 450 V VB rating does not authorize a 500 V bank waveform, and a 650 V switch rating does not by itself authorize a 650 V switching peak. |
| Driver and protection | Rev38 selects HCS21 permission fan-in, LVC1G06 open-drain shunt release, PMBT3904 AUX-biased ENA shunt, UCC27624DDAR, 10 Ω series gate resistor, 10 kΩ gate pull-down, and STW65N65DM2AG in a compiled partial stage. The HOT TPS3431 WDO and dual TPS3890 rail RESET outputs join the retained trip fan-in. The latter use 294 kΩ/100 kΩ and 1.02 MΩ/100 kΩ dividers for nominal 4.531 V logic5 and 12.88 V AUX falling thresholds, respectively. Published delays use different fixtures; STW turnoff is typical at a different gate drive. Rev35 instead uses UCC27511A. | Establish AUX and HOT rail ranges, supervisor threshold/CT/delay corners, shunt OFF clamp at temperature, base/open fault behavior, watchdog low-pulse capture, filter, loaded gate discharge and complete fault-to-current-zero maximum. The PFC PWM, F2, reservoir and AUX producers are still external. Do not sum incomparable published numbers into a guarantee. |
| Source watchdog | TPS3431 with ideal 1 nF CWD gives 119.82–144.98 ms device-only bounds in the Rev32 fixture. CPU-only reset may retain ESP GPIO/peripheral state. | Select installed CWD and its tolerance/leakage, enforce one WDI owner with finite post-reset tail, and bound every WDO-to-STW stage. No accepted reset allowance exists. |

Sources: `operating-envelope-05/envelope-contract.md`,
`f2-timing-02/README.md` and `constraints.json`,
`interface-source-reset-32/README.md`, and
`interface-integration-35/README.md`. Each source labels its own modeled,
proposed, typical, and requirement values; this table does not upgrade them.

## Per-fault work ledger

| Fault class | Independent allowable-time derivation | Candidate implementation path and missing bound | Required closure evidence |
| --- | --- | --- | --- |
| ESP execution loss; control-link loss | Bound consequences of a first START and continued RUN, plus downstream interfaces and stored energy; define the earliest unacceptable state. | Source watchdog/receiver liveness, source PERMIT clear, isolated loss observation, HOT latches, EN, loaded STW. WDI feed tail, selected timing parts, communication detection and complete shutdown are unset. | ESP reset/queue/other-core tests; selected-part corner analysis; synchronized source WDO, PERMIT, HOT clear, EN, gate and current capture. |
| Overcurrent that requires latched stop | Derive from actual sense threshold/error, maximum current at the evaluated threshold, line voltage, guaranteed incremental `L(I,T)` during growth, switch/shunt/inductor/interconnect derated current and energy limits. | Controller PCL or qualified independent detector through latch, EN, loaded STW and commutation. PCL-to-gate maximum and loaded current fall are unset. | Current-sense corner calculation and source-backed `L(I,T)`; worst-phase current waveform with pre-fault activity and sustained current cessation. |
| F2 opening, VD/VB mismatch, absolute OV | Derive permissible delay from installed VD reservoir effective C, `Lmin/Lmax` over trajectory, current at threshold, maximum rectified input, initial VD/VB, derated voltage ceiling, and commutation/remaining line energy. | Divider/filter, TLV3202 outputs, HCS combining/retained clear, UCC27624, loaded STW. Applicable filter ramp delay, pulse capture, and loaded current fall are unset. | Recompute envelope at accepted corners; synchronized VD/VB, inductor current, detector, latch, EN, gate and switch-current traces, including F2-open startup and RUN. |
| HOT logic or driver rail failure; isolator partial power | Determine the last supply level at which each output has guaranteed control and the rail slew/ripple/hold-up envelope; require inhibition before control guarantee is lost or a default-off path through the gap. | TPS3890/AUX fast comparator, POR, local EN bias, isolation defaults, driver UVLO. Intermediate-supply behavior and rail-order propagation are unset. | Selected rail/source envelope, device corner limits, powered-driver/unpowered-logic test, every relevant rail order and isolator-power permutation. |
| Physical PERMIT loss, STOP, receiver abort/reset | Derive the permitted continuation time from the function of the command/interlock and current power-stage state; distinct from a voltage-only detector limit. | Source readback-seen clear, HOT PERMIT-seen clear, `RECEIVER_ABORT_N`, retained latches, EN, loaded STW. Pulse/capture and reset-to-abort maxima are unset. | Exact-pin joined clear path, adverse pulse/reset/clock tests, synchronized hardware permission and current capture. |
| Failed-short STW, failed-short boost diode, stored-bank discharge | Gate disable cannot interrupt a failed-short channel or discharge VD/VB. Derive F1/F2 and interconnect interruption/withstand and stored-energy containment instead. | No valid gate-to-current-zero path for the failed device. | Separate fuse/interconnect/thermal/energy qualification; do not record a passing gate timing for this row. |

The fault/event rows in `fault-response.tsv` keep individual detector and
transaction cases visible. This ledger groups them only where they share a
hazard model; it does not merge their electrical producers or capture minima.
Command deadlines are separate authorization limits derived from the hazard
and communication envelope. A healthy heartbeat cannot extend START expiry.

Rev38 receiver revalidation now waits for a fresh physical
`HOT_SESSION_CLEAR_N` sample after abort release. This avoids requesting a
clock while the clear is known low; it does not replace the asynchronous
fault-to-clear path or add a supported time bound. The UCC27624 ENA corner
gap is tracked in `gate-enable-corners.md`: the new AUX-biased shunt is a
pin-level default-off candidate, but PMBT3904 hot/cold saturation, the
UCC's internal EN pull-up maximum, and intermediate HOT-rail collapse still
prevent an analog OFF proof.
The compiled partial fixture also has a finite-edge preparation-abort
reset, a six-input HOT trip fan-in, physical-PERMIT-loss detection, separate
SESSION/RUN retained latches with raw request clocks, and a separate physical-PERMIT-seen
memory. The latter's asynchronous preset is asserted by PERMIT high even
during its reset pulse, subject to an unproved minimum pulse width and
rail/logic corners. The history-reset D input now requires post-trip
disarm Q high, RUN/PERMIT low, healthy trip fan-in and asserted receiver
abort at the raw clock edge. ACK remains a receiver-firmware prerequisite;
the electrical setup/hold and coincident-trip cases remain open. These paths provide no
numerical implementation bound until their actual producers and joins
are completed.

`F2-DETECTOR.md` records the four-channel VD/VB topology and its open
threshold, pulse and power-state analysis. The VD/VB external ports still
lack the physical F2/reservoir/PFC producers in this compiled join.
`HOT-RAILS.md` records the selected HOT undervoltage producer topology and
an illustrative static threshold screen. Its 100 pF CT values and nominal
trip points do not establish rail-failure detection or capture time. The
AUX overvoltage and fast-dip paths remain separate missing producers.

## Existing conditional F2 screen — not an accepted limit

`f2-timing-02/constraints.json` records null for actual fault-current bound,
end-to-end shutdown bound, `Lmin/Lmax`, and installed voltage ceiling. Its
illustrative screen assumes 132 Vac crest, 410 V bank, 19.8 µF local
capacitance, 50 A at the evaluation threshold, `Lmin=100 µH`, `Lmax=216 µH`,
and a provisional 500 V ceiling. After a 20 mV comparator-overdrive reserve,
it calculates 2.526807 µs of conditional delay; 2 µs is only a provisional
design target. The circuit's detector/filter, loaded STW turnoff, and physical
fault current are not bounded. No one may copy those values into
`T_allowable` or mark this ledger PASS.

For the selected F2-open model, the engineering calculation to repeat with
supported limits is:

```text
I_end = I_at_threshold + V_in_max / L_min * T
V_end = V_at_threshold + I_end / C_min * T
V_peak = V_in_max + sqrt((V_end - V_in_max)^2 + L_max/C_min * I_end^2)
T_allowable = greatest T for which V_peak plus uncertainty stays below
              the derated installed voltage limit at every accepted corner
```

This model assumes a healthy controllable switch and boost diode and excludes
ringing, wiring spikes, fuse arcing, and failed-short energy paths. If those
terms matter at the chosen limit, expand the model or qualify them separately.

## Next evidence to collect

1. From the retained power-stage design and actual source/part data: accepted
   separate VD/VB/VDS and current/energy/temperature envelopes; effective
   local C over voltage/temperature; guaranteed incremental L range at fault
   current; actual shunt temperature, ISENSE bias applicability, controller
   delay, line/source impedance and operating phase. Record any datum that is
   only typical or modeled.
2. From the joined Rev38 circuit: selected comparator/filter/latch/isolator/
   watchdog/driver parts and values; pulse and clear/clock minima; rail order;
   loaded gate path; exact fault-to-EN and watchdog-to-EN topology.
3. From firmware and protocol tests: reset-time WDI ownership, last-edge
   bound, queue-to-pin behavior, single pre-reset START acceptance, timeout
   nonextension, and physical disarm before deliberate restart.
4. From an assembled isolated low-voltage fixture: simultaneous fault,
   detector, retained-state, PERMIT, EN, loaded gate and current records, with
   measurement uncertainty. Physical status stays NOT RUN until these exist.

Numerical timing acceptance remains OPEN wherever either side of the
inequality or its applicability is unsupported. Engineering may continue on
the separate candidate without treating this ledger as permission to
energize mains.

## Sources

- `docs/superpowers/specs/2026-09-23-power-entry-hot-receiver-design.md`
- `zapote/power-entry/passive-reva/protection/f2-timing-02/README.md` and `constraints.json`
- `zapote/power-entry/passive-reva/protection/f2-open-01/README.md`
- `zapote/power-entry/passive-reva/protection/operating-envelope-05/envelope-contract.md`
- `zapote/power-entry/passive-reva/protection/interface-source-reset-32/README.md`
- `zapote/power-entry/passive-reva/protection/interface-integration-35/README.md`
