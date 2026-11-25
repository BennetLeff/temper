/**
 * @file rtd_food.c
 * @brief C51 food-probe RTD conversion and classification (see rtd_food.h).
 */
#include "rtd_food.h"

#include <math.h>
#include <stddef.h>

#include "max31865.h"
#include "rtd_convert.h"

void rtd_food_default_params(rtd_food_params_t *p)
{
    if (!p) return;
    p->r_ref_ohm = 4300.0f;
    p->r0_ohm = 1000.0f;
    p->r_pullup_ohm = 1.0e6f;
    p->ice_offset_k = 0.0f;
}

float rtd_food_ratio_to_ohm(const rtd_food_params_t *p, double ratio)
{
    if (!p || !(p->r_ref_ohm > 0.0f) || !(p->r_pullup_ohm > 0.0f)) return NAN;
    return (float)(ratio / (1.0 / p->r_ref_ohm + 1.0 / p->r_pullup_ohm));
}

float rtd_food_ohm_to_c(const rtd_food_params_t *p, float r_ohm)
{
    if (!p) return NAN;
    return rtd_convert_ohm_to_c(r_ohm, p->r0_ohm) - p->ice_offset_k;
}

rtd_food_state_t rtd_food_classify(uint16_t code, uint8_t fault_status)
{
    if (fault_status & MAX31865_FAULT_REFIN_HIGH) return RTD_FOOD_UNPLUGGED;
    if (fault_status & (MAX31865_FAULT_REFIN_LOW | MAX31865_FAULT_RTDIN_LOW | 0x04u /* D2 over/under-voltage */))
        return RTD_FOOD_INPUT_FAULT;
    if (code < RTD_FOOD_WINDOW_LOW_CODE || code > RTD_FOOD_WINDOW_HIGH_CODE) return RTD_FOOD_OPEN_LEAD;
    return RTD_FOOD_OK;
}

rtd_food_state_t rtd_food_read(const rtd_food_params_t *p, uint16_t code, uint8_t fault_status, float *t_c)
{
    rtd_food_state_t s = rtd_food_classify(code, fault_status);
    if (t_c) *t_c = s == RTD_FOOD_OK ? rtd_food_ohm_to_c(p, rtd_food_ratio_to_ohm(p, code / 32768.0)) : NAN;
    return s;
}
