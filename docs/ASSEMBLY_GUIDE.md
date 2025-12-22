# Assembly Guide: Temper Induction Cooker (RCA 12A3 Integration)

## 1. Safety Precautions
**WARNING: HIGH VOLTAGE AND HIGH CURRENT.**
- This device operates at mains voltages (120VAC) and internal DC voltages up to 340V.
- The induction coil generates intense magnetic fields. Keep sensitive electronics and pacemakers away.
- Ensure all capacitors are discharged before touching the board.
- Always use a GFCI-protected outlet and an isolation transformer during testing.

## 2. Tools Required
- Soldering station (capable of soldering large THT lugs)
- Hex key set (M3, M4)
- Phillips screwdriver
- Digital Multimeter (CAT III 600V rated)
- Oscilloscope with high-voltage differential probe
- 3D printer (for ducting)
- Thermal grease (Boron Nitride or Silicone based)

## 3. Step-by-Step Assembly

### Phase 1: Mechanical Preparation
1. **Chassis Cleaning**: Thoroughly clean the vintage RCA 12A3 chassis. Remove all original tube sockets and transformers.
2. **Rear Panel Modification**: Cut an 80mm circular opening in the rear panel for the exhaust fan. Drill 4 holes for the fan mounting screws.
3. **Top Panel Cutout**: If not already present, create a 200mm opening in the top panel for the glass-ceramic cooktop.
4. **Bottom Vents**: Ensure the bottom intake vents are unobstructed.

### Phase 2: Power Board Assembly (PCBA)
1. **SMD Components**: Solder all SMD components (MCU, Gate Drivers, Logic, Comparators) first. Use a reflow oven or hot plate if possible.
2. **IGBT Mounting**:
   - Apply a thin layer of thermal grease to the back of the IKW40N120H3 IGBTs.
   - Bolt them to the main aluminum heatsink using M3 screws and insulating pads (if required by your heatsink design).
   - Solder the IGBT leads to the PCB.
3. **THT Components**: Solder large electrolytic capacitors, the resonant tank caps, and the input fuse.
4. **Current Transformer**: Mount the CST1005 current transformer and route the primary wire through its center.

### Phase 3: Induction Coil and Sensor
1. **Coil Bracket**: Mount the induction coil to the G10 bracket as per `docs/COIL_BRACKET_DESIGN.md`.
2. **Pan Sensor**:
   - Assemble the spring-loaded mount as per `docs/SENSOR_MOUNT_DESIGN.md`.
   - Ensure the RTD element is securely potted in the aluminum button.
   - Wire the RTD to the MAX31865 interface on the main board.
3. **Glass Installation**:
   - Clean the glass-ceramic panel.
   - Apply high-temp silicone gasket to the chassis lip.
   - Press the glass into place and secure with Z-brackets from underneath.

### Phase 4: Final Integration
1. **Ducting**: Install the 3D printed duct between the 80mm fan and the IGBT heatsink.
2. **Main Board Mounting**: Secure the PCB into the chassis using M3 standoffs.
3. **Internal Wiring**:
   - Connect AC Mains (L, N, PE) to the input lugs.
   - Connect the induction coil leads to the resonant tank terminals.
   - Connect the fan PWM header.
   - Connect the front panel UI (encoder, display).

## 4. Initial Power-On Procedure (No Load)
1. **Visual Check**: Inspect all joints for shorts. Verify HV/LV isolation clearances.
2. **Logic Power**: Apply 15V to the auxiliary input (bypassing the main rectifier). Verify 3.3V at the MCU.
3. **Firmware Flash**: Flash the Temper firmware via USB-C.
4. **Gate Drive Check**: Use an oscilloscope to verify the PWM signals at the IGBT gates (ensure dead-time is present!).
5. **Fan Test**: Verify the fan spins up during the boot sequence.

## 5. Load Testing
1. **Low Voltage**: Use a 30V DC bench supply instead of mains to verify resonant frequency and ZVS.
2. **Mains Power**: Connect to 120VAC via a variac. Slowly ramp up voltage while monitoring tank current.
3. **Temperature Control**: Place a pan with water on the glass. Verify the pan sensor detects the rise and the PID loop stabilizes at the setpoint.
