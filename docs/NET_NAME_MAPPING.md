# Net Name Mapping Convention

**Standard:** UPPER_SNAKE_CASE for all global nets and critical signals.

---

## 1. Power Rails

| Atopile Signal | KiCad Net Name | Rationale |
|----------------|---------------|-----------|
| top.gnd | GND | Standard ground |
| top.dc_bus_plus | +340V_BUS | High voltage bus |
| top.dc_bus_minus| DC_BUS_RTN | Bus return |
| top.vcc_15v | +15V | Gate drive supply |
| top.vcc_3v3 | +3V3 | MCU supply |

---

## 2. Gate Drive Signals

| Atopile Signal | KiCad Net Name | Rationale |
|----------------|---------------|-----------|
| hb.pwm_h | PWM_HS | High-side PWM |
| hb.pwm_l | PWM_LS | Low-side PWM |
| hb.gate_hs.driver.OUTA | GATE_HS | HS Gate output |
| hb.gate_ls.rg_on.p2 | GATE_LS | LS Gate output |
| hb.switch_node | SW_NODE | Half-bridge midpoint |

---

## 3. Safety Signals

| Atopile Signal | KiCad Net Name | Rationale |
|----------------|---------------|-----------|
| safety.shutdown_n | SHUTDOWN_N | Global enable (Active LOW) |
| safety.fault_status | FAULT | Combined fault indicator |
| safety.ocp_fault | OCP_FAULT | Overcurrent fault |
| safety.ovp_fault | OVP_FAULT | Overvoltage fault |
| safety.wdt_reset_n | WDT_RESET_N | Watchdog reset signal |

---

## 4. Sensing Signals

| Atopile Signal | KiCad Net Name | Rationale |
|----------------|---------------|-----------|
| ct_sense.i_sense | I_SENSE | Current sense analog signal |
| mcu.adc_v_bus | V_BUS_SENSE | Bus voltage sense analog |
| rtd_pan.spi_clk | RTD_SCK | RTD SPI Clock |
| rtd_pan.spi_mosi | RTD_SDI | RTD SPI Data In |
| rtd_pan.spi_miso | RTD_SDO | RTD SPI Data Out |
| rtd_pan.spi_cs | RTD_CS_N | RTD SPI Chip Select |
| rtd_pan.drdy | RTD_DRDY | RTD Data Ready |

---

## 5. Control Signals

| Atopile Signal | KiCad Net Name | Rationale |
|----------------|---------------|-----------|
| mcu.wdt_kick | WDT_KICK | Watchdog heartbeat |
| mcu.relay_ctrl | RELAY_CTRL | Soft-start bypass control |
| mcu.zcd_in | ZCD | Zero-crossing detection |
