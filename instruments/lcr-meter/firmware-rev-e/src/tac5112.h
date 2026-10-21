#pragma once
/* TAC5112 configuration for the Rev E front end (docs/rev-e-front-end.md). No Pico SDK
   dependency: test/test_host.c runs the sequence against a model of the register file.
   Register numbers and fields: SLASF24A section 8.1.1, book 0 page 0. */
#include <stdbool.h>
#include <stdint.h>

#define TAC_PAGE_CFG 0x00u
#define TAC_SW_RESET 0x01u
#define TAC_DEV_MISC_CFG 0x02u
#define TAC_INTF_CFG1 0x10u
#define TAC_PASI_CFG0 0x1Au
#define TAC_PASI_TX_CH1_CFG 0x1Eu
#define TAC_PASI_TX_CH2_CFG 0x1Fu
#define TAC_PASI_RX_CH1_CFG 0x28u
#define TAC_PASI_RX_CH2_CFG 0x29u
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

/* DEV_MISC_CFG: SLEEP_EXIT_VREF_EN | SLEEP_ENZ; AREG regulator (AVDD 3.3 V); 3.5 ms VREF
   quick charge for the 1 uF VREF capacitor. */
#define TAC_WAKE 0x09u
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
/* CLK_DET_STS0[7:2] = 10: the 167.58-197.76 kHz sample-rate bin that holds 187.5 kHz. */
#define TAC_RATE_BIN 10u

typedef struct {
    void *context;
    bool (*write)(void *context, uint8_t reg, uint8_t value);
    bool (*read)(void *context, uint8_t reg, uint8_t *value);
    void (*sleep_ms)(void *context, uint32_t ms);
} tac5112_io;

typedef enum {
    TAC_OK = 0,
    TAC_ERR_BUS,     /* no I2C acknowledge */
    TAC_ERR_POWER,   /* DEV_STS0 does not show both ADC channels and DAC channel 1 up */
    TAC_ERR_MODE,    /* DEV_STS1 mode is not "active with a channel on" */
    TAC_ERR_CLOCK,   /* detected sample rate is not the 187.5 kHz bin */
} tac5112_status;

/* Software reset, wake, configure and power up. BCLK and FSYNC must already run. */
tac5112_status tac5112_start(const tac5112_io *io);
/* Status of a running device: power, mode and detected rate. */
tac5112_status tac5112_check(const tac5112_io *io, uint8_t power_expected);
/* Write PWR_CFG and wait for the channels to settle (50 ms). */
tac5112_status tac5112_power(const tac5112_io *io, uint8_t power);
const char *tac5112_status_name(tac5112_status status);
