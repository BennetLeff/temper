/**
 * @file hs_ntc_board.c
 * @brief Board binding of the heatsink NTC driver: hal_adc on ESP32-S3
 *        ADC1_CH5 (GPIO6, zapote/controller HS_ADC: mcu.IO6 ~ hs_adc, the
 *        TLV9062 U6B follower of HS_SENSE through 10 k / 100 nF, then the
 *        CR-8 divider 1.00 k / 5.90 k with 100 nF, zapote C45: the gain is
 *        HS_NTC_ADC_GAIN in hs_ntc.h, the driver's default).
 *
 * As rim_ntc_board.c: the HAL's ESP32 port (hal_adc_esp32.c) owns the one
 * ADC1 one-shot unit and keeps a configuration and a curve-fitting
 * calibration per channel, so this channel and the rim's ADC1_CH8 do not
 * disturb each other. An attenuation change re-initialises this channel and
 * rebuilds its calibration; the driver's 30 mV hysteresis keeps that rare.
 *
 * v3v3: the MCP3202 CH1 reading (rail_adc.c, DECISIONS.md D-RAIL), taken by
 * rtd_service.c on the RTD bus it shares with the MAX31865 (GPIO10-13, CS
 * GPIO42). While it is not MEASURED, read_v3v3_mv reports "not available" and
 * the driver assumes 3.300 V (rail_nominal); the cold-soak check then uses its
 * fallback threshold (D-SOAK).
 *
 * The legacy components/temper_hal/include/temper_pins.h names GPIO3 /
 * ADC1_CH2 ADC_CHANNEL_NTC; on zapote/controller GPIO3 is the blower tach.
 */

#include <stddef.h>

#include "hal_adc.h"
#include "rail_adc.h"
#include "hs_ntc.h"

#define HS_NTC_ADC_CHANNEL ((hal_adc_channel_t)5)   /* ADC1_CH5 = GPIO6 */

static bool s_configured;
static rim_atten_t s_atten;

static hal_adc_atten_t map_atten(rim_atten_t a)
{
    switch (a) {
    case RIM_ATTEN_0:
        return HAL_ADC_ATTEN_0dB;
    case RIM_ATTEN_2:
        return HAL_ADC_ATTEN_6dB;
    case RIM_ATTEN_3:
    default:
        return HAL_ADC_ATTEN_11dB;
    }
}

static bool board_read_pin_mv(void *ctx, rim_atten_t atten, float *mv)
{
    (void)ctx;
    if (hal_adc == NULL || mv == NULL) {
        return false;
    }
    if (!s_configured || atten != s_atten) {
        const hal_adc_config_t cfg = {
            .channel = HS_NTC_ADC_CHANNEL,
            .atten = map_atten(atten),
            .width = HAL_ADC_WIDTH_12BIT,
        };
        s_configured = false;
        if (hal_adc->init(&cfg) != HAL_OK) {
            return false;
        }
        /* Without calibration read_voltage falls back to a linear guess: refuse. */
        if (hal_adc->calibrate != NULL && hal_adc->calibrate(HS_NTC_ADC_CHANNEL) != HAL_OK) {
            return false;
        }
        s_configured = true;
        s_atten = atten;
    }
    return hal_adc->read_voltage(HS_NTC_ADC_CHANNEL, mv) == HAL_OK;
}

static bool board_read_v3v3_mv(void *ctx, float *mv)
{
    (void)ctx;
    return rail_adc_board_v3v3_mv(mv);
}

static const hs_ntc_hal_t s_board_hal = {
    .read_pin_mv = board_read_pin_mv,
    .read_v3v3_mv = board_read_v3v3_mv,
    .ctx = NULL,
};

const hs_ntc_hal_t *hs_ntc_board_hal(void)
{
    return &s_board_hal;
}
