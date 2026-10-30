#pragma once
/* TAC5112 configuration for the Rev E front end (docs/rev-e-front-end.md). No Pico SDK
   dependency: test/test_host.c runs the sequence against a model of the register file.
   Register numbers and fields: SLASF24A section 8.1.1, book 0 page 0. */
#include <stdbool.h>
#include <stdint.h>

#define TAC_PAGE_CFG 0x00u
#define TAC_SW_RESET 0x01u
#define TAC_DEV_MISC_CFG 0x02u
#define TAC_MISC_CFG1 0x05u
#define TAC_INTF_CFG1 0x10u
#define TAC_PASI_CFG0 0x1Au
#define TAC_PASI_TX_CH1_CFG 0x1Eu
#define TAC_PASI_TX_CH2_CFG 0x1Fu
#define TAC_PASI_RX_CH1_CFG 0x28u
#define TAC_PASI_RX_CH2_CFG 0x29u
#define TAC_CLK_CFG0 0x32u
#define TAC_CLK_ERR_STS0 0x3Cu
#define TAC_CLK_ERR_STS1 0x3Du
#define TAC_CLK_DET_STS0 0x3Eu
#define TAC_ADC_CH1_CFG0 0x50u
#define TAC_ADC_CH2_CFG0 0x55u
#define TAC_OUT1X_CFG1 0x65u
#define TAC_DSP_CFG0 0x72u
#define TAC_DSP_CFG1 0x73u
#define TAC_CH_EN 0x76u
#define TAC_PWR_CFG 0x78u
#define TAC_DEV_STS0 0x79u
#define TAC_DEV_STS1 0x7Au

/* DEV_MISC_CFG (SLASF24A Table 8-5, p99): SLEEP_EXIT_VREF_EN | SLEEP_ENZ; AREG regulator
   (AVDD 3.3 V); VREF_QCHG [5:4] = 1, a 10 ms VREF quick charge. The Rev F VREF capacitor C62 is
   2.2 uF (audit C-02), above the 1 uF the 3.5 ms default is set for (7.3.5, p44). */
#define TAC_WAKE 0x19u
#define TAC_WAKE_MS 20u /* after leaving sleep: >= 10 ms for channel registers (7.4.2), VREF 10 ms typical */
/* MISC_CFG1 (Table 8-8, p100) [7:6] INCAP_QCHG = 1: 12.5 ms input-capacitor quick charge. The
   default 2.5 ms is set for AC-coupling capacitors up to 1 uF (7.3.3, p42) and C74-C77 are 1 uF
   X7R +10 % (audit C-04). The other bits keep their reset value (read-modify-write). */
#define TAC_INCAP_QCHG_12_5MS 0x40u
#define TAC_INCAP_QCHG_MASK 0xC0u
/* After any ADC power-up the input coupling capacitors still settle through the 40 kOhm input
   with tau = 40 ms: 85 uV (1e-4 of 0.85 V) takes 6.8 tau = 0.27 s (audit C-04). Captures wait
   until this long after the last ADC power-up. */
#define TAC_ADC_SETTLE_MS 300u
/* CLK_CFG0 (Table 8-47, p121-122): PASI_SAMP_RATE [7:2] 0 = auto, else the fixed bin of
   Table 8-59; PASI_FS_RATE_NO_LIM [1] = 1 widens the auto tolerance from 1 % to 5 %. */
#define TAC_CLK_AUTO 0x00u
#define TAC_CLK_NO_LIM 0x02u
#define TAC_CLK_FIXED ((uint8_t)(TAC_RATE_BIN << 2))
/* CLK_ERR_STS0 (Table 8-57, p126-127): DSP_CLK_ERR [7], SRC_RATIO_ERR [4], DEM_RATE_ERR [3].
   CLK_ERR_STS1 (Table 8-58, p127): PASI_BCLK_FS_RATIO_ERR [7]. The PDM flag is unused. The
   "clock stopped" [1] and PASI_FS_ERR flags are not counted: BCLK and FSYNC run from boot,
   before the codec is configured, so those flags may be set by history rather than by the
   configuration. */
#define TAC_CLK_ERR0_MASK 0x98u
#define TAC_CLK_ERR1_MASK 0x80u
/* INTF_CFG1: DOUT = primary ASI DOUT, driven high and low (reset value drives a weak high). */
#define TAC_DOUT_ASI 0x51u
/* INTF_CFG1: DOUT echoes DIN (DOUT_SEL 14), for the SELFTEST loopback. */
#define TAC_DOUT_LOOPBACK 0xE1u
/* ADC_CHx_CFG0: differential, 40 kOhm, CM_TOL 01 (1 Vpp), 2 Vrms, wideband. */
#define TAC_ADC_CFG 0x25u
/* CH_EN: input channels 1 and 2, output channel 1. */
#define TAC_CHANNELS 0xC8u
#define TAC_POWER_ALL 0xC0u     /* PWR_CFG: ADC_PDZ | DAC_PDZ */
#define TAC_POWER_ADC 0x80u     /* PWR_CFG: ADC only (SELFTEST loopback, DAC silent) */
/* Per sample-rate build (pins.h LCR_FS_375K; README "Sample rate"):
   - PASI_CFG0: TDM, standard polarities, bus-error detection and auto resume on, word
     length 32 bits (0x30) or 24 bits (0x20) to match the 64- or 48-BCLK frame (Table 8-25).
   - DSP_CFG0/1 [7:6]: decimation / interpolation filter (Tables 8-102, 8-103). 187.5 kHz is
     in the 192 kHz class, where the linear-phase filters pass only 0.223 fs (ADC, Table 7-31)
     and 0.258 fs (DAC, Table 7-57) and the ADC stop band (>= 80 dB) starts at 0.391 fs =
     73 kHz; the low-latency filters pass 0.456 fs (ADC, Table 7-38) and 0.452 fs (DAC,
     Table 7-64). 375 kHz is in the 384 kHz class, which has only linear-phase specifications:
     0.227 fs ADC (Table 7-32) and 0.258 fs DAC (Table 7-58). Low-latency phase deviation is
     a fixed property of the filter, identical in both ADC channels, so it cancels in A/B.
     Bits [5:0] = 0x02: HPF = programmable IIR at its all-pass default, no biquads, no
     soft-stepping.
   - CLK_DET_STS0[7:2]: the detected sample-rate bin (Table 8-59): 10 = 167.58-197.76 kHz
     holds 187.5 kHz; 5 = 335.16-395.52 kHz holds 375 kHz. */
#ifndef LCR_FS_375K
#define LCR_FS_375K 0
#endif
#if !LCR_FS_375K
#define TAC_PASI_FORMAT 0x30u
#define TAC_DSP_FILTERS 0x42u /* low-latency */
#define TAC_RATE_BIN 10u
#else
#define TAC_PASI_FORMAT 0x20u
#define TAC_DSP_FILTERS 0x02u /* linear-phase */
#define TAC_RATE_BIN 5u
#endif

typedef struct {
    void *context;
    bool (*write)(void *context, uint8_t reg, uint8_t value);
    bool (*read)(void *context, uint8_t reg, uint8_t *value);
    void (*sleep_ms)(void *context, uint32_t ms);
} tac5112_io;

/* Which CLK_CFG0 setting the codec runs with (audit C-05). */
typedef enum {
    TAC_CLOCK_AUTO = 0, /* reset value: auto-detected, 1 % tolerance */
    TAC_CLOCK_NO_LIM,   /* fallback 1: PASI_FS_RATE_NO_LIM, auto with 5 % tolerance */
    TAC_CLOCK_FIXED,    /* fallback 2: semi-automatic, PASI_SAMP_RATE = the build's bin */
    TAC_CLOCK_ERROR,    /* no setting cleared the clock error flags; CLK_CFG0 is back to auto */
} tac5112_clock_mode;
typedef struct {
    tac5112_clock_mode mode;
    uint8_t err0, err1; /* CLK_ERR_STS0 / CLK_ERR_STS1 after the last attempt, masked */
} tac5112_clock;

typedef enum {
    TAC_OK = 0,
    TAC_ERR_BUS,     /* no I2C acknowledge */
    TAC_ERR_POWER,   /* DEV_STS0 does not show both ADC channels and DAC channel 1 up */
    TAC_ERR_MODE,    /* DEV_STS1 mode is not "active with a channel on" */
    TAC_ERR_CLOCK,   /* detected sample rate is not the build's bin (TAC_RATE_BIN) */
} tac5112_status;

/* Software reset, wake, configure and power up. BCLK and FSYNC must already run. If the clock
   status shows an error after power-up, the two CLK_CFG0 fallbacks are tried in turn (the
   channels are powered down around each write: it is a pre-power-up setting). */
tac5112_status tac5112_start(const tac5112_io *io);
/* Same, and reports which clock setting ended up in use (clock may be NULL). */
tac5112_status tac5112_start_report(const tac5112_io *io, tac5112_clock *clock);
/* The masked CLK_ERR_STS0 / CLK_ERR_STS1 flags that count as a clock configuration error. */
tac5112_status tac5112_clock_flags(const tac5112_io *io, uint8_t *err0, uint8_t *err1);
/* Milliseconds still to wait before data is usable, `since_ms` after the last ADC power-up. */
uint32_t tac5112_settle_remaining_ms(uint32_t since_ms);
const char *tac5112_clock_name(tac5112_clock_mode mode);
/* Status of a running device: power, mode and detected rate. */
tac5112_status tac5112_check(const tac5112_io *io, uint8_t power_expected);
/* Write PWR_CFG and wait for the channels to settle (50 ms). */
tac5112_status tac5112_power(const tac5112_io *io, uint8_t power);
const char *tac5112_status_name(tac5112_status status);
