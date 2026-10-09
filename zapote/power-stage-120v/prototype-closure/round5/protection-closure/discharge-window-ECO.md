# Physical discharge window and one-attempt admission

**Candidate hardware contract; no FPGA and no powered release.** Bind the actual source names in native board generation. Existing BUS_LIMIT/CATCH_LIMIT comparators are overvoltage guards and do not establish discharge.

## Window circuit

Actual source `round4/supervisor/circuit.rs::analog_guard` uses `VBUS_GUARD` and `VCATCH_GUARD` from TLV9061 difference stages:20kΩ input/10kΩ feedback/reference resistors, nominal gain0.5 and bias `REF_1V25`. Each local bus/catch card divides by801 (8×249kΩ and2.49kΩ); AMC3330 nominal differential gain is2. Thus `GUARD=REF_1V25+Vphysical/801`. `*_DIFF_PLUS/MINUS` are summing nodes; do not connect threshold comparators there.

Add four **TLV3201AIDBVR** comparators using the existing power/bypass convention. Derive two shared references around the buffered bias:

- `REF_2V5 -> 620kΩ0.1% -> CAPS_SAFE_HI -> 10kΩ0.1% -> REF_1V25`.
- `REF_1V25 -> 10kΩ0.1% -> CAPS_SAFE_LO -> 620kΩ0.1% -> AUX_0V`.

Use Vishay TNPW0805620KBEEA and TNPW060310K0BEEA (0.1%,25ppm/K;620k uses0805 because0603 range ends332kΩ;10k uses0603). Nominal thresholds are1.26984127V and1.23015873V, corresponding to±15.8929V. Referencing the buffered bias substantially cancels reference-divider/buffer offset; two independent ladders from2.5V to ground do not have this property. The prior exploratory97.1k/100k and97.6k/100k proposals are superseded.

For each GUARD use upper comparator noninverting input=`CAPS_SAFE_HI`, inverting input=GUARD; lower noninverting=GUARD, inverting=`CAPS_SAFE_LO`. TLV3201 DBV pins are1OUT,2GND,3IN+,4IN−,5VCC. Require **both high for each channel**, and both `VBUS_DIAG_N` and `VCATCH_DIAG_N` high. Define `CAPS_DISCHARGED_HW` as AND of all six. This symmetric window rejects negative/reversed voltage as well as positive voltage outside the interval; one-sided “below threshold” is insufficient. Retain existing hardware supply/STOP/diagnostic health. A disconnected HV divider, shorted AFE output or failed reference can still falsify the voltage channel; this window does not claim independent redundant voltage sensing or sensor fault coverage beyond the stated diagnostics.

## Conditional error budget

`discharge-window.rs` evaluates131072 endpoint corners using the actual linear difference network, shared reference dependency, AMC common-mode range and signed offsets. It asserts the largest accepted physical voltage remains within±30V and zero remains inside the window. The following budget is **conditional**, not a blanket manufacturer guarantee:

| Term | Budget and source/condition |
|---|---|
|Board ambient for this reference|−40…85°C: exact LM4040A25I is an industrial85°C part, not a125°C part.|
|Every relevant TNPW resistor|0.1% initial plus25ppm/K×65K=0.2625% per resistor. Independent extreme signs; do not assume matched drift.|
|LM4040 reference|2.5V±28mV:±19mV full industrial-temperature bound at100µA plus1mV and8mV maximum current-change allowances. Actual shunt current must stay within specified80µA…15mA.|
|AMC3330 gain|2×(1±0.9425%):0.2% initial plus45ppm/K×165K, conservatively using the full datasheet box-drift span.|
|AMC3330 input offset|±0.96mV:0.3mV initial plus4µV/K×165K full box span.|
|AMC output common mode|1.39…1.49V. Divider gain and diff-stage resistor mismatch are evaluated explicitly.|
|REF buffer input error|±2.35mV allocation:2mV temperature offset bound at5V plus150µV supply-shift,150µV common-mode shift and50µV additional allowance. Supply/common-mode translation must be verified at the actual3.3V circuit.|
|Difference-stage input error|±2.85mV allocation:2mV temperature offset bound plus150µV supply-shift,200µV common-mode shift and500µV combined extra input-bias/leakage/finite-gain allowance. Multiplied by actual noise gain, not signal gain.|
|TLV3201 threshold error|±6.65mV allocation:4mV full-temperature offset plus400µV supply shift,200µV common-mode shift,50µV input-bias/source-impedance allowance and **2mV installed hysteresis allowance**.|

[AMC3330 RevB pp8–9](https://www.ti.com/lit/ds/symlink/amc3330.pdf) supplies gain/offset/common-mode terms and explicitly defines box drift. [TLV9061 RevN p13](https://www.ti.com/lit/ds/symlink/tlv9061.pdf) gives2mV full-temperature offset at5V,80µV/V maximum PSRR and80dB minimum lower-common-mode CMRR at the specified supply; input bias is typical only. [TLV3201 RevC pp5–6](https://www.ti.com/lit/ds/symlink/tlv3201.pdf) gives4mV full-temperature offset,65dB PSRR,56dB CMRR at2.7V and5nA full-temperature bias;1.2mV hysteresis is **typical only**, so2mV is an installed acceptance allocation. [LM4040 RevQ p9](https://www.ti.com/lit/ds/symlink/lm4040.pdf) supplies industrial85°C reference limits. [Vishay TNPW](https://www.vishay.com/docs/28758/tnpw_e3.pdf) owns the resistor tolerance/TCR ordering fields.

The candidate corner result is approximately **−26.79…+26.75V**, with approximately6.6mV minimum zero-input acceptance margin. The executable log is authoritative for its exact numbers. There is no nominal±5V guarantee. Verify both rising and falling thresholds at actual supply, temperature and loading for each installed channel; require outside±30V never grants hardware discharge. Record bias/leakage and hysteresis against the explicit allocations. If they fail, change the circuit/components; do not enlarge the30V safety predicate. The30V predicate is a source-admission design condition, not a declaration that stored energy is safe to touch.

DC endpoint bounds do not qualify settling/recovery after saturation. Source-off mechanical selftest must also wait for a fresh settled window and valid sensor diagnostics; actual residual capacitor voltage is still measured during commissioning. Sensor disconnection/common-reference faults require existing diagnostics and staged checks; no field-safety certification is inferred.

## Coil permission and admission timer

Parent-confirmed MCU allocation: **PC15 physical pin5=ADMIT; PB8 physical pin62=existing PROOF_WINDOW**. They are separate pins.

Each actual KPA/PB driver command equals requested command AND existing physical hard health AND (`SOURCE_OFF_PHYSICAL` OR (`ATTEMPT` AND `TOTAL_WINDOW` AND NOT `RUN_PERMIT`)). Source-off physical permission uses raw K1/K2/KB NC mirrors, their continuously high excitations, all three actual source/bypass driver commands low, and `CAPS_DISCHARGED_HW`. Bind actual existing `PGWD_RESET_N`, `PG5_N`, `POD_STOP` and diagnostic net polarities correctly; a name ending `_N` is not permission to AND the wrong level. No MCU CAPS_SAFE/PRESTART echo may substitute.

Physical START must arm a one-attempt hardware token before mechanical selftest. On a rising `START_QUALIFIED`, load TOKEN only if ADMIT is low and physical source-off/hard health are valid. Use `U_ATTEMPT.CLK=ADMIT`, `U_ATTEMPT.D=ATTEMPT OR (TOKEN AND SOURCE_OFF_PHYSICAL AND hard health)`; avoid combinationally gating the clock. The Q self-feedback is essential: a later ADMIT edge must retain ATTEMPT high after TOKEN is consumed, not clock it low and allow a restart. Its accepted Q=ATTEMPT starts UT_START/UT_TOTAL and asynchronously clears TOKEN. **Do not clear TOKEN directly from ADMIT level**, which races the data setup at that same clock. An invalid early ADMIT cannot energize the source; subsequent accepted admission still consumes only the physical START's one token.

Expiry, normal end or abort must latch existing hardware LATCH false and clear ATTEMPT/TOKEN until a fresh manual RESET/START sequence; otherwise a malicious or stuck MCU can retrigger the source timer. START with ADMIT already high must not arm. A fresh START cannot bypass a latched fault. Actual gate/flip-flop setup, hold, asynchronous-clear and reset-source polarity must be checked in native integration. Before requesting any main-source command, the target must observe actual ATTEMPT/TOTAL_WINDOW valid so the prestart coil-permission term can hand over without chatter.

## Repeated proof pulse

The old one-proof-per-attempt DFF cannot remain in the trigger path. Preserve existing `PROOF_REQUEST = CMD_KT AND PRECHARGE_DONE AND ATTEMPT AND LATCH_OK` and feed it directly into the nonretriggerable LTC6993-1 trigger; preserve independent global source timeout. `PC_REARM` must observe physical PB8 PROOF_WINDOW low for≥2ms and wait beyond the final board timer maximum, rounded up, from the previous trigger before raising the second request. Command-low alone does not reset that timer.

Firmware intentionally requests two proof epochs, but qualify the proof-load hardware for the **entire500ms source-present bound**, because erroneous repeated requests can produce more than two pulses. This is a required load-envelope check, not an imported resistor rating or permission to extend the global timer. Replace the existing hardware budget bypass `TOTAL_WINDOW OR BYPASS_PROVEN` with `TOTAL_WINDOW OR SUP_RUN_OK_LOCAL`, so the first proof cannot disable the global deadline during ISOLATE/REARM/REPROVE. Native tests must demonstrate that repeated ADMIT and PROOF_REQ cannot restart or lengthen the global window.

The exact native timer is **LTC6993HS6-1#TRMPBF**. [ADI RevF pp1,14](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc6993-6993-1-6993-2-6993-3-6993-4.pdf) distinguishes nonretriggerable-1/-3 from retriggerable-2/-4. Earlier inherited wording calling-2 nonretriggerable was incorrect and is superseded; no timer part swap is requested.

This DC screen describes initial prototype component tolerances. It does not include an established service-life aging, contamination or humidity budget; the installed leakage allocation and periodic threshold checks cannot be represented as completed lifetime qualification.
