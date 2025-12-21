# TPS3823 - Processor Supervisory Circuit with Watchdog

**Description:** The TPS3823 is a supervisory circuit that provides circuit initialization and timing supervision, primarily for DSP and processor-based systems. It includes a watchdog timer with a 1.6s timeout.

**Key Specifications:**
- Supply Voltage: 1.1V to 5.5V
- Reset Threshold: 3.08V (for -33 variant)
- Watchdog Timeout: 1.6s
- Reset Pulse Width: 200ms
- Package: SOT-23-5
- Output Type: Push-Pull, Active-LOW

**Pinout (SOT-23-5):**
1. GND - Ground
2. RESET_N - Reset output (active low)
3. MR_N - Manual reset input (active low)
4. WDI - Watchdog input
5. VDD - Supply voltage

**Application in Temper:**
Used as an external hardware watchdog to detect MCU lockup. If the ESP32 fails to toggle the WDI pin for 1.6 seconds, the TPS3823 asserts RESET_N, which triggers the safety interlock latch to disable the power stage.

**Reference:**
- Manufacturer: Texas Instruments
- MPN: TPS3823-33DBVR
- Datasheet: [TPS3823 Datasheet](https://www.ti.com/lit/ds/symlink/tps3823.pdf)
