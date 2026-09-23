# Rev38 HOT execution watchdog — partial join

`elec/src/hot_watchdog.ato` instantiates `TPS3431SDRBR` on HOT_LOGIC5. Its
WDI pin 6 joins the AVR64DA32 PD6 pin 16 and the receiver's local 10 kΩ
WDI pull-down. EN pin 3 and SET1 pin 5 are tied high; WDO pin 7 and ENOUT
pin 8 share `HOT_WATCHDOG_OK`, with a 10 kΩ pull-up to HOT_LOGIC5. That
node joins the HCS21 trip fan-in pin 12 and a 100 kΩ receiver-side
pull-down. The 1 nF C0G timing capacitor is on CWD pin 2. The HOT watchdog
has its own 100 nF supply bypass and its exposed pad is tied to HOT0.

The compiled standalone and joined netlists pass exact-pin checks. Mutations
that remove CWD, remove the WDO pull-up, disable EN, disconnect AVR WDI, or
disconnect WDO from the trip fan-in fail. The prior 10 kΩ receiver-side
pull-down was changed to 100 kΩ: with a 10 kΩ pull-up, two 10 kΩ resistors
would nominally divide 5 V to 2.5 V while the open-drain WDO is released.
The revised nominal divider gives `5 * 100/(10+100) = 4.545 V` before
leakage. This is a topology check, **not** an accepted logic-level bound at
the installed rail, temperature, resistor, leakage, and HCS input corners.

The [TI TPS3431 data sheet](https://www.ti.com/lit/ds/symlink/tps3431.pdf)
specifies WDO/ENOUT as open drain and permits their wired combination. It
specifies WDO low at up to 0.4 V with 3 mA sink at VDD=5 V, and an output
leakage maximum of 1 µA under its stated condition. WDO is undefined below
its POR threshold and can later return high after a watchdog reset pulse;
the independent HOT retained preparation-abort memory must capture a valid
low pulse before that recovery. Its actual minimum low width against HCS74
asynchronous preset and the latch's priority with simultaneous reset remain
unqualified. A healthy WDO level immediately after power-up does not prove
receiver firmware has executed or qualified a session.

The selected 1 nF part does not establish an accepted timeout. CWD effective
capacitance and leakage, TPS3431 corners, WDI last-edge timing, MCU reset
behavior, rail sequencing, and WDO-to-current-zero propagation remain open.
The receiver's PD6 output must be owned by its target firmware and cannot be
serviced by a free-running peripheral after execution loss. The existing
source watchdog separately supervises ESP execution; these timers do not
substitute for one another.
