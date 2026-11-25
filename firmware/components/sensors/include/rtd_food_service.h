/**
 * @file rtd_food_service.h
 * @brief C51 food-probe RTD service: U50 (MAX31865, Pt1000) on the shared RTD SPI bus.
 *
 * U50's CS# is TCA9555 P06 (R136 10 k pull-up), not a GPIO. While it is low, U50 hears every transfer on
 * the bus, including the pan converter's (U30) and the RMS ADC's (U15, sampled every 625 us; a gap over
 * 1500 us drops that half-cycle). So each U50 transfer is one short hold, always in this order:
 *     bus_lock -> select (P06 output, latch 0) -> one transfer -> deselect (P06 input) -> bus_unlock
 * Deselect is attempted on every path, retried once inside the hold; if both fail the service releases
 * the bus, reports RTD_FOOD_LINK_STUCK and never takes the bus again (the board's 1 k series resistors
 * keep U30 and U15 readable through a stuck select; DECISIONS C51 "Food probe").
 *
 * At most one hold per tick and no waiting inside one: the manual fault cycle's 5.5 ms steps span ticks.
 * The caller ticks it every 100 ms (monitor task). Readings at 5 Hz; a fault cycle (D5 = unplugged) runs
 * at start and, at most once a second, while a reading is not OK. A reading counts only while U50's
 * configuration reads back "converting", so a reset part's stale data register is never a temperature.
 */
#ifndef RTD_FOOD_SERVICE_H
#define RTD_FOOD_SERVICE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "rtd_food.h"

#ifdef __cplusplus
extern "C" {
#endif

#define RTD_FOOD_STEP_US           5500u    /* manual fault cycle step wait, as the pan (rtd_service.h) */
#define RTD_FOOD_RESTART_US        12500u
#define RTD_FOOD_READ_PERIOD_US    200000u  /* 5 Hz */
#define RTD_FOOD_CYCLE_INTERVAL_US 1000000u /* fault cycles while not OK, at most this often */
#define RTD_FOOD_STEP2_POLLS       5u       /* cycle still busy after this many polls: input fault */

typedef struct {
    bool (*bus_lock)(void *ctx);   /* take the SPI bus (blocks for other devices' transactions only) */
    void (*bus_unlock)(void *ctx);
    bool (*select)(void *ctx, bool selected); /* P06: true = drive low, false = release to the pull-up */
    bool (*xfer)(void *ctx, const uint8_t *tx, uint8_t *rx, size_t n);
    void *ctx;
} rtd_food_link_t;

typedef enum {
    RTD_FOOD_PH_START = 0, /* next tick: BIAS_CLEAR, the cycle begins */
    RTD_FOOD_PH_BIAS,
    RTD_FOOD_PH_STEP1,
    RTD_FOOD_PH_STEP2,
    RTD_FOOD_PH_STATUS,
    RTD_FOOD_PH_RESTART,
    RTD_FOOD_PH_CONVERTING,
    RTD_FOOD_PH_STUCK,
} rtd_food_phase_t;

typedef struct {
    rtd_food_link_t link;
    rtd_food_params_t params;
    rtd_food_phase_t phase;
    uint64_t t0_us, last_read_us, last_cycle_us;
    bool cycled;           /* a cycle has started at least once */
    bool want_cycle;
    unsigned polls;
    uint8_t fault_status;  /* 07h from the last completed cycle */
    rtd_food_state_t state;
    float t_c;
    uint32_t link_errors;
} rtd_food_service_t;

void rtd_food_service_init(rtd_food_service_t *s, const rtd_food_link_t *link, const rtd_food_params_t *p);
void rtd_food_service_tick(rtd_food_service_t *s, uint64_t now_us);
/* Current state; *t_c is the temperature only when the state is RTD_FOOD_OK, else NAN. */
rtd_food_state_t rtd_food_service_state(const rtd_food_service_t *s, float *t_c);

#ifdef __cplusplus
}
#endif

#endif
