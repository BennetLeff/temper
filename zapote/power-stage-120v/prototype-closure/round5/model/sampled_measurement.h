#ifndef R5_SAMPLED_MEASUREMENT_H
#define R5_SAMPLED_MEASUREMENT_H
/* Diagnostic ideal calibrated ADC estimator, NOT the commissioned target analog
   front end. Zero-crossing interpolation and trapezoidal square integration. */
#include <stdbool.h>
#include <stdint.h>
typedef struct {
    bool seen,started,complete,proof_entire; uint32_t previous_us,serial;
    double previous[8],integral[8],duration,rms[8],period;
    double crest_drop,crest_bus_ratio; unsigned crest_polarities,good_pre;
    bool precharge_ok,proof_ok;
} sampled_measurement_t;
bool sampled_measurement_add(sampled_measurement_t *,uint32_t,const double[8],bool,bool);
#endif
