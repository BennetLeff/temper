/**
 * @file rtd_food_service.c
 * @brief C51 food-probe RTD service (see rtd_food_service.h for the bus discipline).
 */
#include "rtd_food_service.h"

#include <math.h>
#include <string.h>

#include "max31865.h"
#include "rtd_convert.h"

void rtd_food_service_init(rtd_food_service_t *s, const rtd_food_link_t *link, const rtd_food_params_t *p)
{
    memset(s, 0, sizeof *s);
    s->link = *link;
    if (p) s->params = *p; else rtd_food_default_params(&s->params);
    s->phase = RTD_FOOD_PH_START;
    s->state = RTD_FOOD_NO_READING;
    s->t_c = NAN;
}

/* One hold: lock, select, transfer, deselect (retried once), unlock. */
static bool txn(rtd_food_service_t *s, const uint8_t *tx, uint8_t *rx, size_t n)
{
    const rtd_food_link_t *l = &s->link;
    if (!l->bus_lock(l->ctx)) {
        s->link_errors++;
        return false;
    }
    bool ok = l->select(l->ctx, true);
    if (ok) ok = l->xfer(l->ctx, tx, rx, n);
    bool released = l->select(l->ctx, false) || l->select(l->ctx, false);
    l->bus_unlock(l->ctx);
    if (!released) {
        s->phase = RTD_FOOD_PH_STUCK;
        s->state = RTD_FOOD_LINK_STUCK;
        s->t_c = NAN;
        return false;
    }
    if (!ok) s->link_errors++;
    return ok;
}

static bool write_config(rtd_food_service_t *s, uint8_t v)
{
    uint8_t tx[2] = {(uint8_t)(0x80u | MAX31865_REG_CONFIG), v}, rx[2];
    return txn(s, tx, rx, sizeof tx);
}

static bool read_regs(rtd_food_service_t *s, uint8_t reg, uint8_t *out, size_t n)
{
    uint8_t tx[4] = {reg, 0, 0, 0}, rx[4] = {0};
    if (n > 3 || !txn(s, tx, rx, n + 1)) return false;
    memcpy(out, rx + 1, n);
    return true;
}

static void no_reading(rtd_food_service_t *s, rtd_food_state_t st)
{
    s->state = st;
    s->t_c = NAN;
}

/* A failed transfer: no reading, start the cycle again (unless the select is stuck). */
static void link_failed(rtd_food_service_t *s)
{
    if (s->phase == RTD_FOOD_PH_STUCK) return;
    no_reading(s, RTD_FOOD_NO_READING);
    s->phase = RTD_FOOD_PH_START;
}

static bool waited(const rtd_food_service_t *s, uint64_t now, uint32_t us)
{
    return now >= s->t0_us && now - s->t0_us >= us;
}

static void converting_tick(rtd_food_service_t *s, uint64_t now)
{
    if (s->want_cycle && now - s->last_cycle_us >= RTD_FOOD_CYCLE_INTERVAL_US) {
        s->phase = RTD_FOOD_PH_START;
        return; /* the cycle starts next tick: one hold per tick */
    }
    if (now - s->last_read_us < RTD_FOOD_READ_PERIOD_US) return;
    s->last_read_us = now;
    uint8_t r[3];
    if (!read_regs(s, MAX31865_REG_CONFIG, r, 3)) {
        link_failed(s);
        return;
    }
    if (r[0] != MAX31865_CONFIG_CONVERTING) { /* reset or corrupted part: its data register is stale */
        no_reading(s, RTD_FOOD_NO_READING);
        s->want_cycle = true;
        return;
    }
    bool flag = false;
    uint16_t code = rtd_convert_split(r[1], r[2], &flag);
    float t = NAN;
    rtd_food_state_t st = rtd_food_read(&s->params, code, s->fault_status, &t);
    s->state = st;
    s->t_c = st == RTD_FOOD_OK ? t : NAN;
    s->want_cycle = st != RTD_FOOD_OK || flag;
}

void rtd_food_service_tick(rtd_food_service_t *s, uint64_t now)
{
    uint8_t v = 0;
    switch (s->phase) {
    case RTD_FOOD_PH_STUCK:
        return;
    case RTD_FOOD_PH_START:
        if (s->cycled && now - s->last_cycle_us < RTD_FOOD_CYCLE_INTERVAL_US) return;
        if (!write_config(s, MAX31865_CONFIG_BIAS_CLEAR)) { /* bias on, conversions off, 07h cleared */
            link_failed(s);
            return;
        }
        s->cycled = true;
        s->last_cycle_us = now;
        s->t0_us = now;
        s->phase = RTD_FOOD_PH_BIAS;
        return;
    case RTD_FOOD_PH_BIAS:
    case RTD_FOOD_PH_STEP1:
        if (!waited(s, now, RTD_FOOD_STEP_US)) return;
        if (!write_config(s, s->phase == RTD_FOOD_PH_BIAS ? MAX31865_CONFIG_MANUAL_STEP1
                                                          : MAX31865_CONFIG_MANUAL_STEP2)) {
            link_failed(s); /* never step 2 without step 1: that would be the automatic cycle */
            return;
        }
        s->t0_us = now;
        s->polls = 0;
        s->phase = s->phase == RTD_FOOD_PH_BIAS ? RTD_FOOD_PH_STEP1 : RTD_FOOD_PH_STEP2;
        return;
    case RTD_FOOD_PH_STEP2:
        if (!read_regs(s, MAX31865_REG_CONFIG, &v, 1)) {
            link_failed(s);
            return;
        }
        if (v & MAX31865_CONFIG_FAULT_CYCLE_MASK) {
            if (++s->polls >= RTD_FOOD_STEP2_POLLS) {
                no_reading(s, RTD_FOOD_INPUT_FAULT);
                s->phase = RTD_FOOD_PH_START;
            }
            return;
        }
        s->phase = RTD_FOOD_PH_STATUS;
        return;
    case RTD_FOOD_PH_STATUS:
        if (!read_regs(s, MAX31865_REG_FAULT_STATUS, &v, 1)) {
            link_failed(s);
            return;
        }
        s->fault_status = v;
        s->t0_us = now;
        s->phase = RTD_FOOD_PH_RESTART;
        return;
    case RTD_FOOD_PH_RESTART:
        if (!waited(s, now, RTD_FOOD_RESTART_US)) return;
        if (!write_config(s, MAX31865_CONFIG_CONVERTING)) {
            link_failed(s);
            return;
        }
        s->want_cycle = false;
        s->last_read_us = now; /* first read one period later: conversions have settled */
        s->phase = RTD_FOOD_PH_CONVERTING;
        return;
    case RTD_FOOD_PH_CONVERTING:
    default:
        converting_tick(s, now);
        return;
    }
}

rtd_food_state_t rtd_food_service_state(const rtd_food_service_t *s, float *t_c)
{
    if (t_c) *t_c = s->state == RTD_FOOD_OK ? s->t_c : NAN;
    return s->state;
}
