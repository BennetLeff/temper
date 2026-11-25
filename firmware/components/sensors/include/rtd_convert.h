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
    float r_ref_ohm;          /**< 430 (CR-2: RG2012V-431-W-T1, 0.05 %)          */
    float r0_ohm;             /**< 100, Pt100                                   */
    bool loading_correction;  /**< true only with the CR-1 filter fitted        */
    float loading_k1;         /**< 7.86e-4 (CR-7)                               */
    float loading_k0_ohm;     /**< -0.0331 (CR-7)                               */
    float self_heating_k;     /**< 0.061 (CR-7, C1 cartridge)                   */
} rtd_convert_params_t;

/** Defaults for the C1 cartridge on the controller as currently captured
 *  (no CR-1 filter: loading correction off). */
void rtd_convert_default_params(rtd_convert_params_t *p);

/** Split an RTD register pair: returns the 15-bit code, sets *fault_flag. */
uint16_t rtd_convert_split(uint8_t msb, uint8_t lsb, bool *fault_flag);

/** Code -> resistance (ohm), with the loading correction if enabled. */
float rtd_convert_code_to_ohm(const rtd_convert_params_t *p, uint16_t code);

/** Callendar-Van Dusen inverse, -200..850 degC. Returns NAN for R <= 0. */
float rtd_convert_ohm_to_c(float r_ohm, float r0_ohm);

/** Code -> pan-sensor temperature (degC), self-heating removed. */
float rtd_convert_code_to_c(const rtd_convert_params_t *p, uint16_t code);

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
