#ifndef R5_MEASUREMENT_H
#define R5_MEASUREMENT_H
#include <stdbool.h>
#include <stdint.h>
/* Channels exactly U_ADC: VLINE, VPRE, VOUT, VBUS, VCATCH, VTANK,
 * IPROOF, ILINE. Inputs are calibrated SI units with absolute uncertainty. */
typedef struct {
    bool seen,started,complete,proof_entire,contacts_entire,fault;
    uint32_t previous_us,serial,completed_us;
    double previous[8],integral[8],duration,rms[8],period;
    double peak[2],drop_at_peak[2],ratio_at_peak[2],error[8];
    unsigned good_pre;
    bool precharge_ok,proof_ok,source_ok,catch_discharged,catch_rose,catch_ok;
    double initial_catch,previous_catch;
} r5_measurement_t;
/* init rejects absent/nonfinite uncertainties. These are calibration inputs,
 * not fabricated target defaults. Add returns sample acceptance; complete marks
 * only the call publishing a full cycle. Runtime fault invalidates all outputs. */
bool r5_measurement_init(r5_measurement_t *, const double error[8]);
bool r5_measurement_add(r5_measurement_t *,uint32_t,const double[8],bool proof_energized,bool contacts_qualified);
bool r5_measurement_fresh(const r5_measurement_t *,uint32_t);
#endif
