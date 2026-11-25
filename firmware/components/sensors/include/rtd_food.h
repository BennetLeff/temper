/**
 * @file rtd_food.h
 * @brief C51 food-probe RTD (J9, U50 MAX31865, 4-wire Pt1000): conversion and unplug classification.
 *
 * Pure functions, host-tested against the controller's controller_calcs.py rtd_food() / rtd_food_unplug()
 * (branch controller-c51; DECISIONS C51 "Food probe", "Food-probe unplug").
 *
 * Loading: a 1 M pull-up from BIAS feeds the top of the RTD but not Rref, so code x Rref over-reads
 * (1.1 K at 0 C, 2.6 K at 300 C). With node equations at the RTD top, VBIAS cancels and
 *     R = q / (1/Rref + 1/Rpu),   q = code / 2^15.
 * The 1 % pull-up tolerance leaves 0.03 K. Rref 4.30 k 0.1 % 25 ppm: up to 0.37 K + 0.55 K over 60 K, the
 * first removable by an ice-point offset (ice_offset_k, subtracted).
 *
 * Unplug: a full unplug opens FORCE+, the reference current stops and the code means nothing; the
 * fault cycle's D5 (REFIN- > 0.85 VBIAS) says so within 0.9 ms. One open sense lead drifts out of the
 * code window (72-124 ms). Self-heating at 0.37 mA is 0.14 mW and is not corrected.
 */
#ifndef RTD_FOOD_H
#define RTD_FOOD_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float r_ref_ohm;     /* 4300, R130 RT0805BRD074K3L */
    float r0_ohm;        /* 1000, Pt1000 */
    float r_pullup_ohm;  /* 1e6, R_bias_p (sense+ to BIAS) */
    float ice_offset_k;  /* measured reading at 0 C, subtracted; 0 until calibrated */
} rtd_food_params_t;

typedef enum {
    RTD_FOOD_OK = 0,
    RTD_FOOD_UNPLUGGED,   /* D5: FORCE+ open (probe out) */
    RTD_FOOD_OPEN_LEAD,   /* code outside the window: one sense lead open, or a short */
    RTD_FOOD_INPUT_FAULT, /* D4..D2: the input circuit, not the temperature */
} rtd_food_state_t;

/* Window as code ratios: about -36 C and 380 C (rtd_food_unplug's proposal). */
#define RTD_FOOD_WINDOW_LOW_RATIO  0.20
#define RTD_FOOD_WINDOW_HIGH_RATIO 0.55
#define RTD_FOOD_WINDOW_LOW_CODE   6554u  /* round(0.20 x 32768) */
#define RTD_FOOD_WINDOW_HIGH_CODE  18022u /* round(0.55 x 32768) */
/* Threshold registers (03h/05h) hold the code in bits 15..1, as the RTD data register. */
#define RTD_FOOD_HIGH_THRESHOLD_WORD ((uint16_t)(RTD_FOOD_WINDOW_HIGH_CODE << 1))
#define RTD_FOOD_LOW_THRESHOLD_WORD  ((uint16_t)(RTD_FOOD_WINDOW_LOW_CODE << 1))

void rtd_food_default_params(rtd_food_params_t *p);
float rtd_food_ratio_to_ohm(const rtd_food_params_t *p, double ratio);
float rtd_food_ohm_to_c(const rtd_food_params_t *p, float r_ohm);
rtd_food_state_t rtd_food_classify(uint16_t code, uint8_t fault_status);
/* Classify, and convert only an OK reading (*t_c = NAN otherwise). */
rtd_food_state_t rtd_food_read(const rtd_food_params_t *p, uint16_t code, uint8_t fault_status, float *t_c);

#ifdef __cplusplus
}
#endif

#endif
