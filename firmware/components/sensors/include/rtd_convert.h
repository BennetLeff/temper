/**
 * @file rtd_convert.h
 * @brief MAX31865 RTD code -> resistance -> temperature for the sensor-r3 C1
 *        pan sensor (output/temper-sensor-r3/pcb/CHANGE-REQUEST.md CR-7).
 *
 * Pure functions, no hardware access, so the conversion is host-tested.
 *
 *   code     15-bit ratiometric ADC result (RTD MSB:LSB >> 1; LSB bit 0 is
 *            the fault flag and is NOT part of the code)
 *   R_meas   = code / 2^15 * R_ref
 *   R_true   = R_meas - (k1 * R_meas + k0)     (CR-7 loading correction of
 *            the CR-1 sense-line filter; applied only on a front end that has
 *            CR-1 fitted, see rtd_convert_params_t.loading_correction)
 *   T        = Callendar-Van Dusen inverse of R_true (IEC 60751 coefficients)
 *              minus the C1 Pt100 self-heating offset (CR-7: 0.061 K)
 *
 * The self-heating term is the MAX31865 bias current's ordinary, continuous
 * heating of the element. It is subtracted as a constant and is never used as
 * a contact signal (sensor-r3 PATENTS.md design rule P1).
 */

#ifndef RTD_CONVERT_H
#define RTD_CONVERT_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define RTD_CVD_A  3.9083e-3
#define RTD_CVD_B  (-5.775e-7)
#define RTD_CVD_C  (-4.183e-12)

typedef struct {
    float r_ref_ohm;          /**< 430 (CR-2: RESI PTFR0805B430RN9 (430 ohm, 0.1 %, 10 ppm/K; DECISIONS C52)) */
    float r0_ohm;             /**< 100, Pt100                                   */
    bool loading_correction;  /**< true only with the CR-1 filter fitted        */
    float loading_k1;         /**< 7.86e-4 (CR-7)                               */
    float loading_k0_ohm;     /**< -0.0331 (CR-7)                               */
    float self_heating_k;     /**< 0.061 (CR-7, C1 cartridge)                   */
    float gain_cal;           /**< 1.0 = uncalibrated (CR-2 gate 1b); see rtd_convert_gain_cal() */
} rtd_convert_params_t;

/** Defaults for the C1 cartridge on the controller as currently captured
 *  (no CR-1 filter: loading correction off). */
void rtd_convert_default_params(rtd_convert_params_t *p);

/** Split an RTD register pair: returns the 15-bit code, sets *fault_flag. */
uint16_t rtd_convert_split(uint8_t msb, uint8_t lsb, bool *fault_flag);

/** Code -> resistance (ohm): R_meas = code / 2^15 * r_ref_ohm * gain_cal, then the loading correction if
 *  enabled. gain_cal = 1.0f gives exactly the uncalibrated result (a multiply by 1.0 is exact). */
float rtd_convert_code_to_ohm(const rtd_convert_params_t *p, uint16_t code);

/** Callendar-Van Dusen inverse, -200..850 degC. Returns NAN for R <= 0. */
float rtd_convert_ohm_to_c(float r_ohm, float r0_ohm);

/** Code -> pan-sensor temperature (degC), self-heating removed. */
float rtd_convert_code_to_c(const rtd_convert_params_t *p, uint16_t code);

/* ---- CR-2 single-point gain calibration (controller DECISIONS C52/C53, CR-2 gate 1b) ------------------
 *
 * A known resistor near R(200 degC) (175.86 ohm) on the RTD input, 4-wire, gives one mean code. The factor
 * gain_cal = R_meas_expected / (code_mean / 2^15 * r_ref_ohm), where R_meas_expected is r_cal_ohm itself, or
 * with the loading correction on, the R_meas that the correction maps to r_cal_ohm:
 * (r_cal_ohm + k0) / (1 - k1). It cancels every multiplicative error of the reference: the R39 tolerance
 * (0.1 % = 0.54 K at 250 degC) and the 252.9 mOhm of routed copper inside the reference measurement.
 *
 * The code is a float mean of N conversions, not one 15-bit integer: one integer code at the calibration
 * point (~13400) quantises the factor to +/-0.5 LSB / 13400 = +/-37 ppm, which is up to 0.020 K at 250 degC
 * (R/(dR/dT) = 536 K there), twice the 0.01 K target. 0.01 K at 250 degC allows 0.25 LSB of error in the
 * calibration code. A mean of N codes gets below one LSB only if the conversions carry noise sigma of at
 * least ~0.5 LSB rms (dither), and then 3 sigma/sqrt(N) <= 0.25 LSB needs N >= (12 sigma)^2: N = 36 for
 * sigma = 0.5 LSB, 144 (2.4 s at 60 Hz continuous) for 1 LSB. The data sheet's 150 uV rms (typ., input
 * referred, over the Nyquist bandwidth) is ~3.5 LSB at this channel's ~1.42 V reference (2.0 V bias across
 * 430 + 176 ohm); if all of it reached the code, N would be ~1800 (30 s). The bench records the code sigma
 * of the run and picks N from it; with a noiseless code the residual is the integer one (<= 0.020 K at
 * 250 degC). A single code is a mean of N = 1.
 *
 * Physical bound, |gain_cal - 1| <= RTD_GAIN_CAL_MAX_DEV. Worst-case linear stack of what a correct
 * calibration can see (ppm of the factor):
 *    R39 tolerance, PTFR0805B430RN9 0.1 %                             1000
 *    R39 10 ppm/K at a calibration ambient within 25 +/- 20 degC       200
 *    copper in the reference, 252.9 mOhm / 430 ohm = +588, +30 %       765   (one-sided: makes the factor > 1)
 *    calibration resistor tolerance, budgeted at 0.1 %                1000
 *    MAX31865 full-scale error +/-1 LSB (typ., no max: 3x taken)        92   (3 LSB / 32768)
 *    MAX31865 INL +/-1 LSB (typ., no max: 3x taken) at code ~13400     224
 *    MAX31865 offset error +/-3 LSB (max) at code ~13400               224   (folds into the factor)
 *    code-mean quantisation, 0.5 LSB at code ~13400                     37
 *    total                                                            3542   = 0.35 %
 * RTD_GAIN_CAL_MAX_DEV = 0.5 % keeps a 1.4x margin over that stack, and still rejects what a wrong
 * calibration looks like: a resistor value entered for the wrong point, a 1 % part near its limit, a fixture that is
 * not 4-wire (a 1 ohm lead pair is 0.57 % at 176 ohm), a fault or a rail code. */
#define RTD_GAIN_CAL_MAX_DEV 0.005f

typedef enum {
    RTD_GAIN_CAL_OK = 0,
    RTD_GAIN_CAL_BAD_INPUT = 1,  /**< NULL, NaN/Inf, r_cal or r_ref not > 0                   */
    RTD_GAIN_CAL_BAD_CODE = 2,   /**< code mean at a fault or rail value (D-OPEN limits)      */
    RTD_GAIN_CAL_OUT_OF_BOUND = 3, /**< |factor - 1| > RTD_GAIN_CAL_MAX_DEV                   */
} rtd_gain_cal_status_t;

/** Computes and validates gain_cal from the mean 15-bit code of N conversions of a known resistor
 *  r_cal_ohm on the RTD input. Uses p's r_ref_ohm and loading terms (not p->gain_cal). Writes *gain_out
 *  only on RTD_GAIN_CAL_OK. Rejects a mean <= RTD_C1_FAIL_LOW_CODE or >= RTD_C1_FAIL_HIGH_CODE (a short,
 *  an open, a rail). Pure. */
rtd_gain_cal_status_t rtd_convert_gain_cal(const rtd_convert_params_t *p, float code_mean, float r_cal_ohm,
                                           float *gain_out);

/* ---- Sensor-failure classification of a C1 conversion --------------------
 *
 * A conversion that is evidently a sensor failure is not a temperature: it
 * goes to the recoverable FAULT_PROBE_OPEN / FAULT_PROBE_SHORT path, never to
 * the RUNAWAY latch (output/temper-sensor-r3/firmware/DECISIONS.md D-OPEN;
 * the codes are recomputed and gated by sensor_fail_codes.py).
 *
 *   OPEN   code >= RTD_C1_FAIL_HIGH_CODE: R >= R(850 degC) = 390.48 ohm, the
 *          top of the IEC 60751 range, 250 K above the C1 chip's 600 degC
 *          rating. An open element converts to full scale (32767, 988.7
 *          degC). The firmware's 300 degC latch fires on the way up, and a
 *          real pan cannot climb from 300 to 850 degC between two 50 Hz
 *          conversions (the fastest modelled fault heats it at 3.84 K/s), so
 *          only a broken sensor path produces a first reading up here.
 *          Also: register 07h with any of D5..D2 set (REFIN- high/low,
 *          RTDIN- low, over/under-voltage): the input circuit, not the
 *          temperature, failed.
 *   SHORT  code <= RTD_C1_FAIL_LOW_CODE: R <= R(-200 degC) = 18.52 ohm, below
 *          the IEC 60751 range (code 0 converts to NAN).
 *
 * Not a sensor failure: the RTD High / RTD Low threshold bits (D7/D6) alone.
 * The high-threshold bit is what a real over-temperature above 360 degC
 * (word 35544) also sets, so a plausible code with only that bit set is a
 * temperature and the 300 degC check latches RUNAWAY on it. */
#define RTD_C1_FAIL_HIGH_CODE 29757u
#define RTD_C1_FAIL_LOW_CODE  1411u
#define RTD_FAULT_INPUT_BITS  0x3Cu   /* 07h D5..D2 */

typedef enum {
    RTD_SENSOR_OK = 0,
    RTD_SENSOR_FAIL_OPEN = 1,
    RTD_SENSOR_FAIL_SHORT = 2,
} rtd_sensor_fail_t;

/** Classify one conversion (15-bit code, register 07h of that conversion). */
rtd_sensor_fail_t rtd_convert_classify_failure(uint16_t code, uint8_t fault_status);

#ifdef __cplusplus
}
#endif

#endif /* RTD_CONVERT_H */
