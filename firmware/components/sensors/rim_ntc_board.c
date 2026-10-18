/**
 * @file rim_ntc_board.c
 * @brief Board binding of the rim NTC driver: hal_adc on ESP32-S3 ADC1_CH8
 *        (GPIO9, zapote/controller RIM_SENSE through the TLV9061 buffer).
 *
 * The HAL's ESP32 port (hal_adc_esp32.c) owns the single ADC1 one-shot unit
 * and the curve-fitting calibration, so this file does not open a second
 * unit. CR-7 switches the attenuation by node voltage; each switch
 * reconfigures the channel (hal_adc->init) and rebuilds its calibration
 * (hal_adc->calibrate). The driver's 30 mV hysteresis keeps switches rare.
 *
 * Attenuation mapping (ESP-IDF v5 names): ATTEN0 = ADC_ATTEN_DB_0,
 * ATTEN2 = ADC_ATTEN_DB_6, ATTEN3 = ADC_ATTEN_DB_12 (HAL_ADC_ATTEN_11dB, the
 * deprecated alias of DB_12).
 *
 * v3v3: the MCP3202 CH1 reading against the LM4040A25 (CR-7, rail_adc.c;
 * DECISIONS.md D-RAIL). rtd_service.c takes it on the shared bus every 100 ms;
 * read_v3v3_mv returns it while it is MEASURED and fresh. Otherwise (no
 * reading, SPI error, out of the widened contract, stale) it reports "not
 * available" and the driver uses 3.300 V (rail_nominal), the as-built case
 * that costs up to 4.37 K over 100-250 degC (rim-ntc.json).
 *
 * Note: the legacy components/temper_hal/include/temper_pins.h still names GPIO9
 * PIN_RTD_DRDY. On zapote/controller DRDY is on TCA9555 P07 and GPIO9 is the
 * rim (sensor-r3 CHANGE-REQUEST.md section 1, "Unchanged").
 */

#include <stddef.h>

#include "hal_adc.h"
#include "rail_adc.h"
#include "rim_ntc.h"

#define RIM_NTC_ADC_CHANNEL ((hal_adc_channel_t)8)   /* ADC1_CH8 = GPIO9 */

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

static bool board_read_node_mv(void *ctx, rim_atten_t atten, float *mv)
{
    (void)ctx;
    if (hal_adc == NULL || mv == NULL) {
        return false;
    }
    if (!s_configured || atten != s_atten) {
        const hal_adc_config_t cfg = {
            .channel = RIM_NTC_ADC_CHANNEL,
            .atten = map_atten(atten),
            .width = HAL_ADC_WIDTH_12BIT,
        };
        s_configured = false;
        if (hal_adc->init(&cfg) != HAL_OK) {
            return false;
        }
        /* No calibration scheme: read_voltage falls back to a linear guess,
         * which is not good enough for a temperature. Refuse to read. */
        if (hal_adc->calibrate != NULL && hal_adc->calibrate(RIM_NTC_ADC_CHANNEL) != HAL_OK) {
            return false;
        }
        s_configured = true;
        s_atten = atten;
    }
    return hal_adc->read_voltage(RIM_NTC_ADC_CHANNEL, mv) == HAL_OK;
}

static bool board_read_v3v3_mv(void *ctx, float *mv)
{
    (void)ctx;
    return rail_adc_board_v3v3_mv(mv);
}

static const rim_ntc_hal_t s_board_hal = {
    .read_node_mv = board_read_node_mv,
    .read_v3v3_mv = board_read_v3v3_mv,
    .ctx = NULL,
};

const rim_ntc_hal_t *rim_ntc_board_hal(void)
{
    return &s_board_hal;
}
