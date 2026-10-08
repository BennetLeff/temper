#ifndef TEMPER_R5_FAST_SPI_H
#define TEMPER_R5_FAST_SPI_H
#include "fullbridge_adapter.h"
bool r5_fast_init(void);
bool r5_fast_sample(bridge_feedback_t *out);
#endif
