#include "hal_adc.h"
#include "rtd_service.h"

#include <assert.h>
#include <math.h>
#include <stdbool.h>

extern void peripherals_init(void);
extern bool test_adc_calibration(void);
extern float read_heatsink_temperature(void);
extern bool test_rtd_sensor(void);

static float s_adc_mv[3] = {1650.0f, 1650.0f, 3000.0f};
static bool s_calibration_ok = true;
static rtd_sample_status_t s_rtd = {.ready = true, .generation = 1u, .age_ms = 5u};
static float s_pan_c = 25.0f;

static hal_status_t adc_init(const hal_adc_config_t *config)
{
    assert(config->channel >= 0 && config->channel < 3);
    assert(config->width == HAL_ADC_WIDTH_12BIT);
    return HAL_OK;
}

static hal_status_t adc_calibrate(hal_adc_channel_t channel)
{
    assert(channel >= 0 && channel < 3);
    return s_calibration_ok ? HAL_OK : HAL_ERROR;
}

static hal_status_t adc_voltage(hal_adc_channel_t channel, float *millivolts)
{
    assert(channel >= 0 && channel < 3);
    *millivolts = s_adc_mv[channel];
    return HAL_OK;
}

static const hal_adc_ops_t s_adc_ops = {
    .init = adc_init,
    .calibrate = adc_calibrate,
    .read_voltage = adc_voltage,
};
const hal_adc_ops_t *hal_adc = &s_adc_ops;

rtd_sample_status_t rtd_service_sample_status(void) { return s_rtd; }
float rtd_service_pan_temperature_c(void) { return s_pan_c; }

int main(void)
{
    assert(!test_adc_calibration());
    assert(isnan(read_heatsink_temperature()));
    peripherals_init();
    assert(test_adc_calibration());
    assert(fabsf(read_heatsink_temperature() - 25.0f) < 0.2f);

    s_adc_mv[2] = 1607.0f;
    assert(fabsf(read_heatsink_temperature() - 85.0f) < 1.0f);
    s_adc_mv[2] = 0.0f;
    assert(isnan(read_heatsink_temperature()));
    s_adc_mv[2] = NAN;
    assert(isnan(read_heatsink_temperature()));
    s_adc_mv[2] = 100.0f;
    assert(isnan(read_heatsink_temperature()));
    s_adc_mv[2] = 3290.0f;
    assert(isnan(read_heatsink_temperature()));
    s_calibration_ok = false;
    assert(!test_adc_calibration());

    assert(test_rtd_sensor());
    s_rtd.age_ms = RTD_MAX_CONTROL_SAMPLE_AGE_MS + 1u;
    assert(!test_rtd_sensor());
    s_rtd.age_ms = 1u;
    s_pan_c = NAN;
    assert(!test_rtd_sensor());
    return 0;
}
