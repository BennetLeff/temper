#ifndef R5_QUALIFICATION_H
#define R5_QUALIFICATION_H
#include <stdbool.h>
#include <stdint.h>
/* All routines are allocation-free C11, shared verbatim by target and model. */
typedef struct { uint32_t edge_ms; unsigned edges; bool seen, level, fault; } r5_heartbeat_t;
bool r5_heartbeat_step(r5_heartbeat_t *, bool level, uint32_t now_ms);
typedef struct { float units_per_code, offset_code, residual_limit, error; bool valid; } r5_calibration_t;
bool r5_calibrate(r5_calibration_t *, int32_t zero, int32_t injected,
                   float reference, float reference_error, int32_t check_code,
                   float check_reference, float residual_limit);
bool r5_scale(const r5_calibration_t *, int32_t code, float *value, float *error);
typedef struct { float pullup_ohm, r25_ohm, beta_k, error_c; bool lag_qualified; } r5_ntc_config_t;
bool r5_ntc_temperature(const r5_ntc_config_t *, uint16_t code, float *celsius);
bool r5_ntc_cold(const r5_ntc_config_t *, uint16_t code, float *celsius);

#endif
