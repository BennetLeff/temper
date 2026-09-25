/* Production hooks backed by the existing cooker board's ADC and MAX31865.
 * These do not imply that the separate Rev38 source-to-PFC board or the
 * cooker's remaining power/UI interfaces have been qualified. */
#if !defined(ESP_PLATFORM) && !defined(COOKER_BOARD_IO_TESTING)
#error "Cooker board I/O is only compiled for the ESP32 target"
#endif

#include "hal.h"
#include "hal_adc.h"
#include "temper_pins.h"
#include "rtd_service.h"
#include "ntc_guard.h"

#ifdef ESP_PLATFORM
#include "esp_adc/adc_oneshot.h"
#include "esp_log.h"
#else
#define ADC_CHANNEL_0 0
#define ADC_CHANNEL_1 1
#define ADC_CHANNEL_2 2
#define ESP_LOGE(tag, ...) ((void)(tag))
#endif

#include <math.h>
#include <stdbool.h>
#include <stdint.h>

static const char *TAG = "cooker_board_io";

/* elec/src/modules.ato::ThermalComparator: 3.3 V -> 10k -> sense ->
 * NTCALUG01A104GA (100k at 25 C, B25/85=4190 K) -> GND. This is a
 * nominal temperature estimate; the independent analog comparator owns
 * the 85 C trip. An implausible or unavailable conversion is NAN so the
 * state machine's over-temperature interlock can cut power. */
#define NTC_SUPPLY_MV 3300.0f
#define NTC_FIXED_OHM 10000.0f
#define NTC_R25_OHM 100000.0f
#define NTC_BETA_K 4190.0f
#define NTC_T25_K 298.15f

static bool s_adc_ready;

void peripherals_init(void)
{
    if (s_adc_ready) return;
    if (!hal_adc) {
        ESP_LOGE(TAG, "ADC HAL unavailable");
        return;
    }

    const hal_adc_config_t channels[] = {
        {ADC_CHANNEL_CURRENT, HAL_ADC_ATTEN_11dB, HAL_ADC_WIDTH_12BIT},
        {ADC_CHANNEL_VOLTAGE, HAL_ADC_ATTEN_11dB, HAL_ADC_WIDTH_12BIT},
        {ADC_CHANNEL_NTC, HAL_ADC_ATTEN_11dB, HAL_ADC_WIDTH_12BIT},
    };
    for (unsigned i = 0; i < sizeof(channels) / sizeof(channels[0]); ++i) {
        if (hal_adc->init(&channels[i]) != HAL_OK) {
            ESP_LOGE(TAG, "ADC channel %ld init failed", (long)channels[i].channel);
            return;
        }
    }
    s_adc_ready = true;
}

bool test_adc_calibration(void)
{
    if (!s_adc_ready || !hal_adc) return false;

    const hal_adc_channel_t channels[] = {
        ADC_CHANNEL_CURRENT, ADC_CHANNEL_VOLTAGE, ADC_CHANNEL_NTC,
    };
    for (unsigned i = 0; i < sizeof(channels) / sizeof(channels[0]); ++i) {
        float voltage_mv = NAN;
        if (hal_adc->calibrate(channels[i]) != HAL_OK ||
            hal_adc->read_voltage(channels[i], &voltage_mv) != HAL_OK ||
            !isfinite(voltage_mv) || voltage_mv < 0.0f ||
            voltage_mv > NTC_SUPPLY_MV) {
            ESP_LOGE(TAG, "ADC channel %ld calibration/read failed", (long)channels[i]);
            return false;
        }
    }
    return true;
}

float read_heatsink_temperature(void)
{
    float voltage_mv = NAN;
    if (!s_adc_ready || !hal_adc ||
        hal_adc->read_voltage(ADC_CHANNEL_NTC, &voltage_mv) != HAL_OK ||
        !isfinite(voltage_mv) || voltage_mv <= 0.0f ||
        voltage_mv >= NTC_SUPPLY_MV) return NAN;

    const float resistance_ohm = NTC_FIXED_OHM * voltage_mv /
                                 (NTC_SUPPLY_MV - voltage_mv);
    const float reciprocal_kelvin = 1.0f / NTC_T25_K +
                                    logf(resistance_ohm / NTC_R25_OHM) /
                                        NTC_BETA_K;
    if (!isfinite(reciprocal_kelvin) || reciprocal_kelvin <= 0.0f) return NAN;
    const float temperature_c = 1.0f / reciprocal_kelvin - 273.15f;
    if (!isfinite(temperature_c) || temperature_c < NTC_TEMP_MIN_C ||
        temperature_c > NTC_TEMP_MAX_C) return NAN;
    return temperature_c;
}

bool test_rtd_sensor(void)
{
    const rtd_sample_status_t status = rtd_service_sample_status();
    return status.ready && status.generation != 0u &&
           status.age_ms <= RTD_MAX_CONTROL_SAMPLE_AGE_MS &&
           isfinite(rtd_service_pan_temperature_c());
}
