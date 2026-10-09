#ifndef R5_SENSOR_FRONTEND_H
#define R5_SENSOR_FRONTEND_H
#include "acquisition.h"
#include "measurement.h"
#include "qualification.h"
typedef struct {
    r5_calibration_t channel[8];
    r5_ntc_config_t ntc[2];
    r5_measurement_t measurement;
    double physical[8];
    bool configured,valid,cold;
} r5_sensor_frontend_t;
/* Call after all eight independent zero/injection/check calibrations and actual
 * installed NTC coefficients are supplied. No target factory gains invented. */
bool r5_sensors_configure(r5_sensor_frontend_t *);
bool r5_sensors_sample(r5_sensor_frontend_t *,const ads_sample_t *,bool proof,bool contacts);
bool r5_sensors_ntc(r5_sensor_frontend_t *,const uint16_t code[2]);
#endif
