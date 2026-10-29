#pragma once
/* Rev E wiring contract (docs/rev-e-front-end.md), as routed on the Rev E board (cad/design.json U1).
   Rev F adds the HB/FLT debug LEDs on GPIO 23/22 (both unused on Rev E, so one image runs on both). */
#define HARDWARE_REVISION "E-codec"
#define PIN_I2S_DIN 2u     /* RP2040 -> TAC5112 pin 5 DIN (DAC data) */
#define PIN_I2S_DOUT 3u    /* TAC5112 pin 4 DOUT -> RP2040 (ADC data) */
#define PIN_I2S_BCLK 4u    /* RP2040 -> TAC5112 pin 2 BCLK; side-set base */
#define PIN_I2S_FSYNC 5u   /* RP2040 -> TAC5112 pin 3 FSYNC; side-set base + 1 */
#define PIN_I2C_SDA 8u     /* I2C0 SDA -> TAC5112 pin 8, 4.7 kOhm pull-up to 3V3 */
#define PIN_I2C_SCL 9u     /* I2C0 SCL -> TAC5112 pin 7, 4.7 kOhm pull-up to 3V3 */
#define PIN_RNG_SET_HI 6u  /* AO3400A gate: K3 SET coil, 100 kOhm range */
#define PIN_RNG_SET_LO 7u  /* AO3400A gate: K1 SET coil, 100 Ohm range (RG100/RF100) */
#define PIN_RNG_RESET 10u  /* AO3400A gate: the four RESET coils (K1-K4) in parallel */
#define PIN_RNG_SET_MED 11u /* AO3400A gate: K2 SET coil, 5 kOhm range */
#define PIN_RNG_SET_REF 14u /* AO3400A Q6 gate (R108 100 Ohm, R109 100 kOhm pull-down): K4 SET coil, 1 kOhm 0.1 % reference across HCUR-LCUR */
#define PIN_USB_VBUS 13u   /* VBUS divided by two */
#define PIN_LED 25u        /* STATUS: front-panel orange LED (Rev F D4, R12 390 Ohm), lit during a capture */
#define PIN_LED_FAULT 22u  /* Rev F debug LED D20 (FLT): codec/self-test failure or the last reply was an ERR */
#define PIN_LED_HEARTBEAT 23u /* Rev F debug LED D19 (HB): blinks at 1 Hz while the main loop is idle */
#define PIN_MON12 26u      /* ADC0: +12 V via 100k / 10k */
#define PIN_MON_N12 27u    /* ADC1: -12 V via 150k from -12 V / 10k to 3V3 */
#define PIN_UART_TX 28u    /* Optional UART0 header */
#define PIN_UART_RX 29u
#define RAIL_SAMPLES 256u
#define CODEC_I2C_ADDRESS 0x50u /* TAC5112 ADDR pin shorted to ground (Table 7-72) */

/* Sample-rate build (README "Sample rate"). The default build comes first: the host's
   contract test reads the first definition of each name. */
#ifndef LCR_FS_375K
#define LCR_FS_375K 0
#endif
#if !LCR_FS_375K
#define SYSTEM_CLOCK_HZ 120000000u
#define BCLK_CYCLES 10u        /* system clocks per BCLK: 12 MHz */
#define FRAME_BCLKS 64u        /* two 32-bit TDM slots: FSYNC = 187.5 kHz */
#else
#define SYSTEM_CLOCK_HZ 108000000u /* within the RP2040's 133 MHz rating, default VREG */
#define BCLK_CYCLES 6u         /* system clocks per BCLK: 18 MHz, 27.8 ns high and low */
#define FRAME_BCLKS 48u        /* two 24-bit TDM slots: FSYNC = 375 kHz */
#endif
