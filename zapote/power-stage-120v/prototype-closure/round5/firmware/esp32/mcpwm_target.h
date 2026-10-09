#ifndef TEMPER_R5_MCPWM_TARGET_H
#define TEMPER_R5_MCPWM_TARGET_H
#include "fullbridge_adapter.h"
/* Live common-TEZ phase transactions, inclusive endpoints. Physical commissioning
 * remains false; pads stay disconnected and no call can raise PWM_REQUEST. */
bool r5_pwm_init(bridge_backend_t *backend, bool commissioned);
/* One boot-only logic-waveform connection while REQUEST is low. Caller must
 * first verify physical hardware inhibition. Does not grant heating permission. */
bool r5_pwm_prepare_capture(bool physical_inhibit_verified);
/* Actual register diagnostics; no physical capture or fabricated edge arrays. */
bool r5_pwm_requested(void);
bool r5_pwm_readback(bridge_feedback_t *);
#endif
