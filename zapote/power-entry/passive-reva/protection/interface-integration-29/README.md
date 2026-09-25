# Revision 29: HOT receiver-session watchdog candidate

Status: **compiled connectivity candidate; package geometry candidate created, but not yet registered into the compiled Atopile project; not a complete receiver or source-reset implementation.** Revision 29 copies Rev28 and adds the TPS3431 plus wiring for the unused second half of the retained SN74HCS74. It changes no PCB. The local footprint review now contains a DRB0008A land-pattern candidate based on TI's drawing. The source footprint field remains review-only until the offline Atopile build and KiCad project library registration are verified together.

## What the circuit does

The new `TPS3431SDRBR` is powered from HOT `logic5`. `RECEIVER_SESSION_ACTIVE` drives EN through a 10 kΩ pulldown. ENOUT and WDO share `watchdog_ok_n` with one 10 kΩ pullup to `logic5`; TI explicitly permits this wired-open-drain connection. That node no longer drives `/CLR2` directly. A HOT `SN74LVC1G08` combines it with the existing TPS3890 `rails_ok` supervisor output. Its supply has a local 100 nF bypass, and a 10 kΩ output pulldown biases the AND output low while the gate is unpowered or high impedance (0.5 mA load when high at 5 V). The AND output drives the second HCS74 `/CLR2`. Its D2 is tied high and CLK2 receives `SESSION_QUALIFIED_PULSE_5V`; Q2 is the qualified link-good signal feeding Rev28's existing link AND gate.

This rail qualification addresses a real startup hole: TPS3431 ENOUT is not a defined clear source below its 0.8 V POR threshold, while HCS74 Q power-up state is not guaranteed. TPS3890 is specified from VDD=1.5 V, the LVC AND gate from VCC=1.65 V, and HCS74 from VCC=2 V. Above the HCS74's 2 V minimum, the TPS3890 supervisors hold `rails_ok` low until their monitored rails cross threshold and the release delay expires, independently keeping `/CLR2` asserted. This establishes the intended clear sequence in the HCS74 operating range, subject to supervisor thresholds, net behavior, and timing corners.

There is still an explicit lowest-rail gap below the TPS3890's 1.5 V specified supply range. The TPS3890, LVC AND gate, and HCS74 outputs/latch state are not claimed there. The output pulldown biases the AND output but does not make behavior of unpowered silicon a datasheet guarantee. No startup-safety claim is made for that interval; a complete design needs a power-ramp analysis showing the gate-driver disable remains safe through the entire partial-power region.

This creates the intended latch sequence:

| Condition | `/CLR2` | Q2/link-good |
|---|---:|---:|
| Boot, after logic5 enters its valid operating range | low from `rails_ok` supervisor | low |
| EN reasserted; startup delay expires without a qualified-session pulse | high | remains low |
| One new qualified-session pulse with watchdog good | high | high |
| Watchdog timeout | low during WDO reset pulse | clears low |
| WDO returns high | high | remains low until a new qualified-session pulse |
| Receiver session drops and EN goes low | low | clears low |

`latch-sequence-tests.rs` starts Q2 as unknown and high, then checks that the supervisor-qualified clear resolves it low once logic5 is valid. It also checks that a session pulse held high through clear release cannot set Q2; a new rising edge is required. The lower, invalid rail region remains unmodeled. These tests do not model silicon thresholds, metastability, analog rise time, actual reset delays, or failure modes inside the receiver.

## Timing and electrical limits

The prototype value is 1 nF C0G on CWD with SET1 high. TI's formula gives 132.4 ms typical and ideal-capacitor bounds of 119.82–144.98 ms. The 10% timing limits exclude capacitor tolerance and board parasitics. A watchdog timeout drives WDO low for `tRST` (170–230 ms); the retained latch means the WDO pulse need not stay asserted after timeout. This timeout is a **review/prototype value**, not a qualified product limit: the system's maximum permitted shutdown latency has not been specified. The 1 nF timing shall not be used to claim safety response.

The receiver must provide all three external functions: `RECEIVER_SESSION_ACTIVE`, `VALIDATED_HEARTBEAT_5V`, and `SESSION_QUALIFIED_PULSE_5V`. The last two must meet the TPS3431 WDI and SN74HCS74 clock high-input requirements at HOT 5 V over operating corners; nominal 3.3 V GPIO is not accepted as a guaranteed high. Session-active is compatible with a 3.3 V source under the TPS3431's fixed 0.8 V VIH specification, but its pull-down and reset behavior must be assured by the actual receiver. Heartbeat edges must be generated only by received, integrity-checked peer traffic; a free-running timer cannot establish link health.

The second latch's Q2 drives the retained Rev28 link-good net and its 10 kΩ pulldown, about 0.5 mA at 5 V, plus the SN74LVC1G08 input. TI's SN74HCS74 output-high guarantee at 4.5 V under 6 mA exceeds the Rev28 gate's 3.15 V high threshold at 4.5 V. This verifies the nominal load path; power ramp through the invalid rail region, temperature, and actual board interconnect still need review.

TI's TPS3431 package is DRB0008A: 3 mm × 3 mm, 0.65 mm pitch, exposed thermal pad to GND. The stock KiCad 3 mm footprints found here use 0.5 mm pitch or materially different exposed-pad geometry. A local exact-pattern candidate and dimensional review are in [`footprint-review/README.md`](footprint-review/README.md); the footprint parses and renders in KiCad, and its geometry guard passes. The source still sets `TBD_REVIEW_ONLY:TPS3431SDRBR_DRB0008A`: the local library has not been registered in the Atopile/KiCad project or rebuilt into its compiled artifacts. The exposed pad is modeled as pin 9 and tied to HOT GND. `TPS3431SDRBR` is the TI orderable MPN; supplier stock and assembly capability have not been checked. The passives have candidate MPNs in the source and also need BOM sourcing review.

## What remains outside this candidate

- No receiver MCU, protocol decoder, isolation barrier, reset supervisor, or level translation is selected here. The three named signals are unimplemented boundary requirements.
- This is a receiver/session watchdog. It does not provide the separate source-side reset/abort capture path. The existing ESP32 `EN` reset network is an external RC/button reset path; tapping EN alone misses internal software/watchdog resets while EN stays high. The existing SELV TPS3823's 0.9–2.5 s `WDT_RESET_N` is diagnostic as currently wired. A source-health latch on `PERMIT_TX` remains a separate unbuilt design. The established ISO7741 allocation uses all three forward channels and its single reverse channel, so it has no spare direct abort channel.
- No exact maximum disable latency has been established, no assembled prototype exists, and no bench captures exist. Gate turn-off and relay release remain unmeasured.
- The command-model's `source_healthy` state is not wired by this candidate. A receiver or source reset that fails to drive the named session input low remains outside the proof.

## Reproduction

From `source-candidate/`, build offline with the preserved Atopile 0.2.69 cache command recorded in Revision 26's [build environment](../interface-integration-26/build-environment.md):

```sh
UV_CACHE_DIR=/private/tmp/temper09-uv-cache \
UV_TOOL_DIR=/private/tmp/temper09-uv-tools \
/Users/bennet/.local/bin/uv tool run --offline \
  --python /opt/homebrew/opt/python@3.12/bin/python3.12 \
  --from atopile==0.2.69 ato --non-interactive build \
  elec/src/power_entry_pfc_control_candidate.ato:PowerEntryPfcLinkClearCandidate
```

Run the compiled netlist audit from the worktree root:

```sh
rustc --edition=2021 --test \
  zapote/power-entry/passive-reva/protection/interface-integration-29/audit-rev28-rev29.rs \
  -o /tmp/rev29-audit
REV28_NET=zapote/power-entry/passive-reva/protection/interface-integration-28/source-candidate/build/default.net \
REV29_NET=zapote/power-entry/passive-reva/protection/interface-integration-29/source-candidate/build/default.net \
  /tmp/rev29-audit
```

Run the temporal logic check:

```sh
rustc --edition=2021 --test \
  zapote/power-entry/passive-reva/protection/interface-integration-29/latch-sequence-tests.rs \
  -o /tmp/rev29-latch-tests && /tmp/rev29-latch-tests
```

Primary reference: [TI TPS3431 datasheet](https://www.ti.com/lit/ds/symlink/tps3431.pdf), especially pin functions, §7.3, and timing tables. The datasheet explicitly permits the WDO/ENOUT shared open-drain node, specifies WDO's finite reset pulse, and gives the external timing equation. The source-candidate netlist and tests verify wiring and logical latch behavior only.
