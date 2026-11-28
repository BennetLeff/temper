/**
 * @file rtd_convert.c
 * @brief MAX31865 code -> resistance -> temperature (see header).
 */

#include "rtd_convert.h"

#include <math.h>
#include <stddef.h>

void rtd_convert_default_params(rtd_convert_params_t *p)
{
    if (p == NULL) {
        return;
    }
    p->r_ref_ohm = 430.0f;
    p->r0_ohm = 100.0f;
    p->loading_correction = false;
    p->loading_k1 = 7.86e-4f;
    p->loading_k0_ohm = -0.0331f;
    p->self_heating_k = 0.061f;
    p->gain_cal = 1.0f; /* uncalibrated: byte-identical to the conversion before CR-2 gain cal */
}

uint16_t rtd_convert_split(uint8_t msb, uint8_t lsb, bool *fault_flag)
{
    if (fault_flag != NULL) {
        *fault_flag = (lsb & 0x01u) != 0u;
    }
    return (uint16_t)((((uint16_t)msb << 8) | lsb) >> 1);
}

float rtd_convert_code_to_ohm(const rtd_convert_params_t *p, uint16_t code)
{
    const double r_meas = (double)code / 32768.0 * (double)p->r_ref_ohm * (double)p->gain_cal;
    if (!p->loading_correction) {
        return (float)r_meas;
    }
    return (float)(r_meas - ((double)p->loading_k1 * r_meas + (double)p->loading_k0_ohm));
}

float rtd_convert_ohm_to_c(float r_ohm, float r0_ohm)
{
    if (!(r_ohm > 0.0f) || !(r0_ohm > 0.0f)) {
        return NAN;
    }
    const double a = RTD_CVD_A;
    const double b = RTD_CVD_B;
    const double c = RTD_CVD_C;
    const double ratio = (double)r_ohm / (double)r0_ohm;
    /* T >= 0: R = R0 (1 + A T + B T^2), closed form. */
    const double disc = a * a - 4.0 * b * (1.0 - ratio);
    if (disc < 0.0) {
        return NAN;
    }
    double t = (-a + sqrt(disc)) / (2.0 * b);
    if (ratio >= 1.0) {
        return (float)t;
    }
    /* T < 0: R = R0 (1 + A T + B T^2 + C (T - 100) T^3). Newton from the
     * quadratic root; converges in a few steps over -200..0 degC. */
    for (int i = 0; i < 8; i++) {
        const double f = 1.0 + a * t + b * t * t + c * (t - 100.0) * t * t * t - ratio;
        const double df = a + 2.0 * b * t + c * (4.0 * t * t * t - 300.0 * t * t);
        if (df == 0.0) {
            break;
        }
        const double step = f / df;
        t -= step;
        if (fabs(step) < 1e-7) {
            break;
        }
    }
    return (float)t;
}

float rtd_convert_code_to_c(const rtd_convert_params_t *p, uint16_t code)
{
    return rtd_convert_ohm_to_c(rtd_convert_code_to_ohm(p, code), p->r0_ohm) - p->self_heating_k;
}

rtd_gain_cal_status_t rtd_convert_gain_cal(const rtd_convert_params_t *p, float code_mean, float r_cal_ohm,
                                           float *gain_out)
{
    if (p == NULL || gain_out == NULL || !isfinite(code_mean) || !isfinite(r_cal_ohm) || !(r_cal_ohm > 0.0f) ||
        !isfinite(p->r_ref_ohm) || !(p->r_ref_ohm > 0.0f)) {
        return RTD_GAIN_CAL_BAD_INPUT;
    }
    /* A short, an open or a rail is not a calibration (also rejects code_mean <= 0). */
    if (code_mean <= (float)RTD_C1_FAIL_LOW_CODE || code_mean >= (float)RTD_C1_FAIL_HIGH_CODE) {
        return RTD_GAIN_CAL_BAD_CODE;
    }
    double r_expected = (double)r_cal_ohm;
    if (p->loading_correction) {
        const double k1 = (double)p->loading_k1;
        if (!isfinite(k1) || !isfinite((double)p->loading_k0_ohm) || !(k1 < 1.0)) {
            return RTD_GAIN_CAL_BAD_INPUT;
        }
        r_expected = (r_expected + (double)p->loading_k0_ohm) / (1.0 - k1); /* inverse of the CR-7 correction */
    }
    const double r_uncal = (double)code_mean / 32768.0 * (double)p->r_ref_ohm;
    const double g = r_expected / r_uncal;
    if (!isfinite(g) || fabs(g - 1.0) > (double)RTD_GAIN_CAL_MAX_DEV) {
        return RTD_GAIN_CAL_OUT_OF_BOUND;
    }
    *gain_out = (float)g;
    return RTD_GAIN_CAL_OK;
}

rtd_sensor_fail_t rtd_convert_classify_failure(uint16_t code, uint8_t fault_status)
{
    if (code >= RTD_C1_FAIL_HIGH_CODE || (fault_status & RTD_FAULT_INPUT_BITS) != 0u) {
        return RTD_SENSOR_FAIL_OPEN;
    }
    if (code <= RTD_C1_FAIL_LOW_CODE) {
        return RTD_SENSOR_FAIL_SHORT;
    }
    return RTD_SENSOR_OK;
}
