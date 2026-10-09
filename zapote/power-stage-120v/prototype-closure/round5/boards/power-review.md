# Power, returns and clock — candidate, no powered release

The implemented regulator ECO replaces the unheatsunk LD1117 with **RECOM R-78B5.0-1.0**, fed directly by AUX_24V, followed by **TPS7A4700RGWR** precision3.3V postregulation. REG3_5V is separate from the existing external POD_5V rail. The existing external R-78HB5.0-0.5/W now feeds only the 5V preload, supply supervisor and gate buffer. Its500mA output no longer carries the six isolated amplifier supplies. The footprint has physically changed from SOT-223 to the manufacturer SIP3 geometry; this is not a pin-compatible substitution. `power-eco.json` lists every intentional source pin-net change. Round4 and native19 remain frozen.

## Current and heat accounting

`power_budget.rs` reads the actual source pin table and writes `power-budget.json`. It counts115 LVC devices, all central resistor loads conservatively at3.6V and−1% resistance (including series and5V-only resistors), and six remote supplies. It separates published maxima from mode allocations rather than labeling the aggregate a guaranteed maximum.

| Load | Bound or allocation, mA | Basis |
|---|---:|---|
| Six AMC3330 | 246 | TI maximum41mA each, no external HLDO load |
| ADS131M08 | 8.6 +2.4 reserve | TI7.7mA analog +0.9mA digital, SPI idle; active-SPI reserve remains to qualify |
| STM32G071 | 7.7 +32.3 reserve | ST Table25,64MHz Flash,130°C, peripherals disabled; reserve covers enabled peripherals provisionally |
| Four TLV9061 / sixteen TLV3201 | 3.2 /1.040 | Maximum800µA /65µA each |
| Five ISO1211 |5.000|Maximum1mA each on the3.3V side |
| Nine ISO7710 | 50.4 | Conservative5.6mA per populated AUX side,100Mbps output-side maximum |
|115 LVC devices | 1.150 +20 reserve |10µA DC each plus allocated switching/leakage load |
| Three LTC6993 |0.600 +2.4 reserve|200µA idle bound plus active-mode allocation |
| Rail supervisor |0.100 reserve|Design allocation, not a verified manufacturer maximum |
| Central resistor overbound |149.342|Recomputed from source after191k proof ECO |
| Six diagnostic pullups |2.184|3.6V/9.9kΩ each |

The source-derived3.3V steady allocation is**532.416mA**. TPS7A4700 ground current is6.1mA typical at1A, not a published maximum at the actual load; allocate10mA provisionally, giving542.416mA before the buck preload; including its worst allocated151.644mA gives694.060mA buck steady current. The exact machine receipt keeps this reserve distinct from guaranteed values.

The external POD_5V preload R1 is82Ω1%, CRCW251282R0FKEG1W2512. An allocated±7% resistance range plus0.1Ω drift gives76.16–87.84Ω: at4.5V it draws at least51.23mA, satisfying the converter's50mA load-regulation condition; at5.5V its allocated dissipation is0.397W. The5% drift term is a conservative engineering allowance beyond the1%/1000h standard rating; it is not a lifetime guarantee. [Vishay CRCW Rev14-Apr-2026, ratings/ordering](https://www.vishay.com/docs/20035/dcrcwe3.pdf). Reserve100mA total for that rail, including buffers and supervisor; switching peaks remain unqualified. Four10k pulldowns now bias the KB/KT/KPA/KPB AHCT buffer inputs low when3.3V is absent; K1/K2 already have command pulldowns.

The independent REG3_5V buck has R17939Ω1%, Vishay PR03000203909FAC003W, copper leads, placed at(244,180) with25.4mm pitch away from the analog front end. Including1% initial tolerance,250ppm/K across100K, and5%+0.1Ω endurance allowance gives35.585–42.415Ω. Across4.60375–5.39625V this guarantees108.541mA minimum load and screens151.644mA/0.818W maximum. The3W P70 rating and60K/W published thermal screen give about109°C at60°C ambient; enclosure/lead/copper temperature still needs measurement. The3.3V300Ω0.1% preload draws at least10.69mA at3.2175V. [Vishay PR03 primary drawing and ratings](https://www.vishay.com/docs/28729/pr010203.pdf).

## Implemented precision postregulation

U109 TPS7A4700RGWR uses ANY-OUT pins8,11,12 grounded:1.4+1.6+0.2+0.1=3.3V. Unused selectors float. Pins1/20OUT and3SENSE join POD_3V3; pins15/16IN and13EN join REG3_5V. TI RevG gives**±2.5% overall accuracy** over−40…125°C,0…1A andVIN≥4.3V:3.2175–3.3825V. The maximum1A dropout is450mV. These stated DC limits fit AMC3330's3.0–3.6V interval.

The selected5V buck input range6.5–32V contains the allocated20.4–26.4V auxiliary supply. For provisional0–60°C ambient, conservatively stack±3% accuracy,±0.4% line,±0.6% load,±0.015%/K×35K, full20mVpp ripple in one direction and±150mV specified50%↔100% load transient: **REG3_5V=4.60375–5.39625V**. The lower result remains303.75mV above the4.3V condition for the LDO's overall accuracy. This removes the known direct3.3V-buck corner mismatch; it does not guarantee the LDO's dynamic output excursion, which has typical curves rather than a complete maximum transient specification.

C148/C149 provide2×22µF input and C150–C152 provide3×22µF output, Murata GRM32ER71E226KE15L25V X7R1210. Applying TI's50% nominal-capacitance design derating and−10% tolerance yields19.8µF input and29.7µF output, above the10µF stability recommendation and20µF accuracy characterization. Confirm the supplier DC-bias/temperature curves and delivered part revision against this allowance; it is a design derating, not a replacement for a part guarantee. C1531µF sets noise reduction/soft start. All capacitors have short local ground stitches.

Total direct3.3V output capacitance, six remote cards included, is140.040µF at+20%. A1ms linear rise to3.6V would add504.144mA, giving1036.560mA output-side sensitivity, exceeding the1A rating. This sensitivity is explicitly a failed1ms assumption, not a guaranteed start-up waveform. The buck additionally charges its44µF nominal local input bank; simultaneously assuming1ms ramps can exceed1A, so **the earlier single-stage startup screen is not a startup acceptance**. CNR controls turn-on; TI's startup equation is typical, not a guaranteed minimum ramp. Both current-limited startup/recovery and WD_RESET_N-safe brownout behavior must be checked. Buck rated capacitance470µF exceeds even the combined nominal downstream capacitance, but the data-sheet startup conditions still apply.

Nominal LDO loss at0.5A is(5−3.3)×0.5=0.85W. At5.39625V input,3.2175V output and0.532406A, output-path loss is1.160W; adding the10mA ground-current allocation gives approximately1.214W. At60°C ambient, staying below125°C requires installed junction-to-ambient≤53.5K/W. Native geometry implements a37×40mm AUX_0V inner heat-spreading region (1480mm²), the full back ground plane and nine0.3mm thermal vias under the3.15mm exposed pad. TI's32.5K/W JEDEC metric would imply39.5°C rise at1.214W, but is **not an extracted thermal model of this board**. Enclosure airflow, copper temperature and junction estimate remain physical holds.

The5V buck's published efficiency at the relevant operating point must be distinguished from maximum loss; its full-load upper-input selection value and thermal impedance are screens only. It remains derated above71°C, maximum case100°C. The added LDO does not permit exceeding either device's operating temperature.

Existing WD_RESET_N supervises the output undervoltage path. The LDO has no PG output and no independent output-overvoltage window has been added. Its internal UVLO threshold is typical; it is not credited as the system permit threshold. Static accuracy is now compatible; dynamic startup/load steps, fault overshoot, reverse-current behavior and independent inhibition remain circuit/physical qualification items.

## Implemented routing and sequencing

U1 has0.8mm24V routing, a local50V1µF input capacitor and local return stitching. POD_3V3 is a filled front copper region and AUX_0V a filled back region. The six contactor source/GS returns use COIL_RET, a separate inner copper region and2mm back spine. A single physical2mm copper net tie N1 connects it at the incoming supply return. These are actual saved copper, checked by native DRC. Copper width and star placement do not substitute for extracted inductance, temperature-rise and switching-immunity measurements.

R15110k biases CTRL_HEARTBEAT_OK low when the receiver is inactive. R15233Ω connects STM32 PA8/MCO to ADC_CLKIN; target HSI16/2 supplies nominal8MHz, OSR1024 gives3906.25samples/s. J7 pin3 is **passive monitor only**; no independent oscillator is fitted or allowed. The MCU and ADC share the same3.3V supply, removing the previously independent clock power-order assumption.

External SWD and J7 instruments must sense without sourcing power into the board. No reverse-current blocker is implemented. CTRL/AUX power-order tests, all gate-off behavior through brownout, sensor startup/settling, and regulator reverse-current paths remain explicit checks. Remote CT burden pairs and TVS stay on the CT board when the cable is unplugged. Five ISO1211/TPL7407L receivers now wet the contacts from AUX_24V. Each562Ω sense resistor plus4.7kΩ0.75W parallel burden follows the frozen receiver ECO. All five excitation signals remain high whenever source voltage is admitted; only source-off commissioning uses the six-slot electrical scan.

For the candidate five5.4W contactor coils, nominal total coil load is27W/1.125A at24V before KT, control supplies and other loads. Five mirror receivers add at most42.12mA when all are energized; all five remain excited while source is present. This is not a qualified HDR-60-24 worst-case budget: coil cold resistance/inrush, supply derating and actual permissible simultaneous states must bound it.

## Proof timing

R110/source R_UT_PROOFSET is191kΩ0.1% TNPW0603191KBEEA. U60 remains LTC6993HS6-1 with DIVCODE5/NDIV32768. Nominal pulse=32768×191k/50k µs=125.173760ms. Manufacturer full-temperature pulse error±3% plus resistor0.1% and25ppm/K over100K combine to3.3605%; an allocated±5% screen gives118.915072–131.432448ms. This covers the110ms firmware proof deadline with8.915ms minimum allocation margin. UT_TOTAL remains446.458ms allocated maximum. There is no independent50ms main/bypass hardware one-shot to increase; the total source-admission sequence must still fit the unchanged global limit.

Sources: [TPS7A4700 RevG](https://www.ti.com/lit/ds/symlink/tps7a47.pdf), [Murata primary application BOM confirming22µF25V±10%X7R](https://www.murata.com/products/productdata/8822188015646/MYMGM1R816ELA5RN.pdf), [RECOM1A](https://recom-power.com/pdf/Innoline/R-78B-1.0.pdf), [RECOM wired5V](https://recom-power.com/pdf/Innoline/R-78HB-0.5_W.pdf), [AMC3330](https://www.ti.com/lit/ds/symlink/amc3330.pdf), [STM32G071](https://www.st.com.cn/resource/en/datasheet/stm32g071gb.pdf), [ADS131M08](https://www.ti.com/lit/ds/symlink/ads131m08.pdf), [TLV9061](https://www.ti.com/lit/ds/symlink/tlv9061.pdf), [TLV3201](https://www.ti.com/lit/ds/symlink/tlv3201.pdf), [ISO7710](https://www.ti.com/lit/ds/symlink/iso7710.pdf), [LTC6993 RevF](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc6993-6993-1-6993-2-6993-3-6993-4.pdf), [TNPW](https://www.vishay.com/docs/28758/tnpw_e3.pdf), [LC1D18BD](https://iportal.se.com/Contents/docs/SQD-LC1D18BD.PDF).

## Discrete admission and isolation ECO

PC15 ADMIT clocks U_ATTEMPT directly. A physical START edge arms the repurposed U_PROOF_ONCE token only with ADMIT low, physical source-off safety and hard health. Accepted ATTEMPT consumes the token; ATTEMPT feeds its own D hold term so repeated ADMIT cannot clear/restart the timer. Both source timers start at ATTEMPT rising, after mechanical tests. STOP_DONE or hard-latch loss clears attempt and token; firmware must keep STOP_DONE low throughout self-test and admission. Source driver permission also requires the actual global window or final hardware RUN.

UT_PROOF now receives the complete qualified PROOF_REQUEST directly; LTC6993-1 remains nonretriggerable. Firmware must observe PB8 low for2ms after the131433µs allocated maximum before requesting a second pulse. PB13 only rises after the second continuous50ms loaded proof, before KT falls. Hardware captures only while PROOF_CAPTURE_VALID and released KPA/KPB mirrors, static excitation and both low commands are valid; loss of isolation clears the proof latch. The global budget escapes only on retained RUN_ARMED AND live RUNTIME_HEALTHY. U_RUN_ARM clocks on fully qualified actual SUP_RUN_OK_LOCAL; U_RUN3 now requires all runtime health including controller interlock. It clears on attempt end or isolation loss. First proof, PB13 alone and raw MCU_RUN cannot bypass the startup deadline.

Four TLV3201 comparators implement the signed bus/catch discharge window using shared reference thresholds. SOURCE_OFF_PHYSICAL requires all four window outputs, both diagnostics, the three source contactor NC mirrors/excitations and all three actual commands low. The separate protection discharge-window ECO documents the conditional error budget; hysteresis and leakage allocations still need qualification. `interlock_audit.rs` evaluates the actual emitted gate pin table and includes negative controls. Boolean agreement does not prove asynchronous setup/hold/recovery, propagation hazards or immunity.

The two added IRL540 drivers retain the selected LC1D18BD integral suppression device. No extra plain flyback diode is fitted. Maximum drain excursion, avalanche energy and release timing require measurement with the actual contactor and harness.

VPRE is now8×249kΩ over2.49kΩ, nominal801:1, matching bus/catch. This preserves linear measurement of the open-contactor/source-opposed stored-voltage condition. The remote board remains60×35mm; calibration must use801, not the former248.761194. Existing TNPW0.1% values above332kΩ have been moved to the manufacturer-supported0805/1206 packages without changing resistance.

All six SN74LVC1G74DCUR devices now use the physical DCU pinout in TI SCES794G p4: CLK1, D2, /Q3, GND4, Q5, /CLR6, /PRE7, VCC8. The inherited round4 map incorrectly exchanged1/3/6; round5 corrects this explicitly and the source audit checks every physical function. At3.3V over−40…125°C, TI p7 requires1.3ns data setup,1.2ns data hold,1.2ns clear/preset recovery and2.7ns minimum clock/clear pulse. Minimum CLK→Q is2.2ns under the specified test load; this exceeds the1.2ns hold requirement before any external token-clear feedback can respond. That test-condition calculation does not establish installed trace/load timing. ADMIT must follow settled health/token data, and clear release must satisfy recovery; actual clock edges, ringing, asynchronous transitions and power sequencing still require instrumented qualification.


## Retained RUN session

A reviewed correction retains a session only after a fully qualified physical RUN edge. The budget escape requires that latch AND live runtime health, allowing zero demand without restarting either timer. The original runtime fault chain remains active. Isolation loss immediately clears RUN/PERMIT and the retained session; inside the initial window source may remain until firmware fault or deadline. After expiry isolation loss removes source through the budget fault. See `budget-session-proposal.md` and the pin-driven regression tests. Hardware does not independently count two proofs or enforce50ms loaded dwell; these remain target-firmware obligations.
