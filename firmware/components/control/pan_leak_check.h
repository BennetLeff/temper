/**
 * @file pan_leak_check.h
 * @brief Element-parallel Pt100 leakage: latch when the rim cross-check keeps
 *        finding a reading that sits below the rim on intact contact.
 *
 * A leakage path in parallel with the Pt100 element (moisture or a conductive
 * film across the element or its leads inside the cartridge) reads low: the
 * loop then holds the reading, not the pan, at the setpoint and the pan runs
 * hot. The MAX31865 sees an ordinary in-range resistance (pcb/DECISIONS.md
 * D6: electrically invisible). The only firmware-visible sign is the rim
 * cross-check (pan_sensor_guard.c D-XCHK): the reading sits more than
 * xcheck_margin_k below the rim NTC for xcheck_hold_s while not rising, the
 * loop requests a D1 probe, and the probe finds contact intact
 * (CC_EVT_PROBE_PASSED). One such cycle is what a food drop or a hot glass
 * can also produce, and D-B5 forbids latching on it. A leak repeats it: the
 * cross-check fires again 30 s after the probe's hold-off, with the rim not
 * falling and the reading not rising (a benign disturbance resolves: the
 * reading recovers or the rim cools).
 *
 * Rule (output/temper-sensor-r3/firmware/DECISIONS.md D-LEAK): a "leak cycle"
 * is a cross-check suspect, a D1 probe that starts at or after it
 * (CC_EVT_SUSPECT), and that probe's PROBE_PASSED. A probe already running
 * when the cross-check fires (the contact-shift window's or D1's own) does
 * not count: it did not answer the cross-check. `cycles` consecutive
 * leak cycles, each suspect within gap_s of the previous one, with the rim
 * reading not more than rim_fall_k lower and the Pt100 reading not more than
 * pt_rise_k higher at each suspect than at the previous one, latch. A
 * D1 LOST or RESTORED event, or a suspect without a usable rim reading,
 * restarts the count.
 *
 * Limits (D-LEAK, leak-checks.json): the cross-check needs the reading
 * margin_k (25 K) below a rim that itself reads the glass, 12-46 K below the
 * pan, with up to +-10 K NTC tolerance. A leak that takes the pan only a few
 * tens of kelvin over the setpoint never fires it, and one that fires it
 * does so only once the pan is well past the setpoint: this rule bounds the
 * time a leaking probe can hold a pan too hot, it does not stop the pan
 * first exceeding 300 degC. Production must keep the leakage out (the
 * cartridge seal and insulation requirements in D-LEAK).
 */

#ifndef PAN_LEAK_CHECK_H
#define PAN_LEAK_CHECK_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float dt_s;        /**< 0.1 (control period)                                 */
    uint8_t cycles;    /**< 2: consecutive leak cycles that latch                */
    float gap_s;       /**< 120: max time between the suspects of two cycles     */
    float rim_fall_k;  /**< 5: the rim may read at most this much lower          */
    float pt_rise_k;   /**< 2: the Pt100 may read at most this much higher       */
} plc_params_t;

typedef struct {
    plc_params_t p;
    float t_s;            /**< time since plc_init                              */
    bool pending;         /**< a suspect waits for its probe to start           */
    bool probing;         /**< the probe that answers the suspect is running    */
    bool d1_busy;         /**< a D1 probe (any source) or LOST is in progress   */
    float sus_t_s, sus_pt_c, sus_rim_c;
    uint8_t count;        /**< consecutive leak cycles                          */
    float last_t_s, last_pt_c, last_rim_c;
    bool latched;
} plc_t;

void plc_default_params(plc_params_t *p);
bool plc_init(plc_t *c, const plc_params_t *p);

/**
 * One control period. suspect: ptl_output_t.xcheck_suspect; cc_event: the
 * contact_check event of this period (cc_event_t value); t_pt100_c the
 * reading the loop used; t_rim_c the rim NTC reading when VALID, else NAN.
 * Returns true once latched (sticky until plc_init).
 */
bool plc_step(plc_t *c, bool suspect, int cc_event, float t_pt100_c, float t_rim_c);

#ifdef __cplusplus
}
#endif

#endif /* PAN_LEAK_CHECK_H */
