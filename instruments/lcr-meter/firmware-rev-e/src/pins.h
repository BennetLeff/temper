#pragma once
/* Rev E wiring contract (docs/rev-e-front-end.md). The Rev E schematic must follow it. */
#define HARDWARE_REVISION "E-codec"
#define PIN_I2S_DOUT 2u    /* TAC5112 pin 4 DOUT -> RP2040 (ADC data) */
#define PIN_I2S_DIN 3u     /* RP2040 -> TAC5112 pin 5 DIN (DAC data) */
#define PIN_I2S_BCLK 4u    /* RP2040 -> TAC5112 pin 2 BCLK; side-set base */
#define PIN_I2S_FSYNC 5u   /* RP2040 -> TAC5112 pin 3 FSYNC; side-set base + 1 */
#define PIN_I2C_SDA 8u     /* I2C0 SDA -> TAC5112 pin 8, 4.7 kOhm pull-up to 3V3 */
#define PIN_I2C_SCL 9u     /* I2C0 SCL -> TAC5112 pin 7, 4.7 kOhm pull-up to 3V3 */
#define PIN_USB_VBUS 13u   /* VBUS divided by two */
#define PIN_RNG_RESET 14u  /* AO3400A gate: the three RESET coils in parallel */
#define PIN_RNG_SET_LO 15u /* AO3400A gate: K1 SET coil, 100 Ohm range (RG100/RF100) */
#define PIN_RNG_SET_MED 16u /* AO3400A gate: K2 SET coil, 5 kOhm range */
#define PIN_RNG_SET_HI 17u /* AO3400A gate: K3 SET coil, 100 kOhm range */
#define PIN_LED 25u
#define PIN_MON12 26u      /* ADC0: +12 V via 100k / 10k */
#define PIN_MON_N12 27u    /* ADC1: -12 V via 150k from -12 V / 10k to 3V3 */
#define PIN_UART_TX 28u    /* Optional UART0 header */
#define PIN_UART_RX 29u
#define RAIL_SAMPLES 256u
#define CODEC_I2C_ADDRESS 0x50u /* TAC5112 ADDR pin shorted to ground (Table 7-72) */
#define SYSTEM_CLOCK_HZ 120000000u
#define BCLK_CYCLES 10u        /* system clocks per BCLK: 12 MHz */
#define FRAME_BCLKS 64u        /* two 32-bit TDM slots: FSYNC = 187.5 kHz */
