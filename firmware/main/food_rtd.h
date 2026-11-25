/**
 * @file food_rtd.h
 * @brief C51 food-probe RTD on the target (food_rtd_esp32.c). Monitor task only.
 */
#ifndef FOOD_RTD_H
#define FOOD_RTD_H

#include "rtd_food.h"

/* Every monitor tick (100 ms): one short RTD-bus hold at most. */
void food_rtd_tick(void);
/* State; *t_c is a temperature only when RTD_FOOD_OK. Not used by any control or safety path. */
rtd_food_state_t food_rtd_read(float *t_c);

#endif
