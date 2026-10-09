#ifndef TEMPER_R5_FAST_SPI_H
#define TEMPER_R5_FAST_SPI_H
#include "fullbridge_adapter.h"
bool r5_fast_init(void);
/* One-time boot only. Caller must establish request-low hardware inhibit and
 * stable zero-phase logic outputs first. No automatic fault/replay reset. */
bool r5_fast_release_reset(bool clock_and_zero_phase_qualified);
bool r5_fast_sample(bridge_feedback_t *out);
#endif
