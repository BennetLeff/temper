#ifndef TEMPER_R5_MCPWM_TARGET_H
#define TEMPER_R5_MCPWM_TARGET_H
#include "fullbridge_adapter.h"
bool r5_pwm_init(bridge_backend_t *backend);
/* Bench image never raises request. A separate released image must bind the
 * qualified capture + phase controller and implement live atomic updates. */
#endif
