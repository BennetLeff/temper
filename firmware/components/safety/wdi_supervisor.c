/**
 * @file wdi_supervisor.c
 * @brief TPS3823 WDI heartbeat gated on control-loop progress (zapote C42)
 *
 * See wdi_supervisor.h. No HAL and no RTOS calls: main.c's supervisor task
 * owns the clock and the WDI pin (safety.c watchdog_hardware_write_wdi()).
 */

#include "wdi_supervisor.h"

#include <stddef.h>

bool wdi_sup_init(wdi_sup_t *s, const wdi_sup_params_t *p)
{
    if (s == NULL) {
        return false;
    }
    s->state = WDI_SUP_ARMING;
    s->reason = WDI_STOP_NONE;
    s->started = false;
    s->level = false;
    s->last_step_ms = 0u;
    s->last_loop_seq = 0u;
    s->rtd_seen = false;
    s->rtd_seq = 0u;
    s->rtd_seen_ms = 0u;
    s->edges = 0u;
    if (p == NULL || p->heartbeat_ms == 0u || p->heartbeat_ms > WDI_HEARTBEAT_MAX_MS ||
        p->min_loop_advance == 0u || p->max_rtd_age_ms == 0u) {
        /* Zero parameters: wdi_sup_step() refuses, so WDI never toggles. */
        s->p.heartbeat_ms = 0u;
        s->p.min_loop_advance = 0u;
        s->p.max_rtd_age_ms = 0u;
        return false;
    }
    s->p = *p;
    return true;
}

bool wdi_sup_step(wdi_sup_t *s, uint32_t now_ms, uint32_t loop_seq, bool rtd_valid,
                  uint32_t rtd_seq, bool *level_out)
{
    if (s == NULL || level_out == NULL || s->p.heartbeat_ms == 0u) {
        return false;
    }
    if (s->state == WDI_SUP_STOPPED) {
        return false;
    }

    /* RTD age, on the supervisor's own clock. */
    if (rtd_valid && (!s->rtd_seen || rtd_seq != s->rtd_seq)) {
        s->rtd_seen = true;
        s->rtd_seq = rtd_seq;
        s->rtd_seen_ms = now_ms;
    }

    if (!s->started) {
        /* First step: baselines only. One step later the loop must have
         * advanced. */
        s->started = true;
        s->last_step_ms = now_ms;
        s->last_loop_seq = loop_seq;
        return false;
    }

    const uint32_t step_ms = now_ms - s->last_step_ms;
    const uint32_t advance = loop_seq - s->last_loop_seq;
    s->last_step_ms = now_ms;
    s->last_loop_seq = loop_seq;

    wdi_stop_reason_t fail = WDI_STOP_NONE;
    if (step_ms > s->p.heartbeat_ms) {
        fail = WDI_STOP_SUPERVISOR_LATE;
    } else if (advance < s->p.min_loop_advance) {
        fail = WDI_STOP_LOOP_STALLED;
    } else if (!s->rtd_seen || (now_ms - s->rtd_seen_ms) > s->p.max_rtd_age_ms) {
        fail = WDI_STOP_RTD_STALE;
    }

    if (fail != WDI_STOP_NONE) {
        if (s->state == WDI_SUP_RUNNING) {
            s->state = WDI_SUP_STOPPED;
            s->reason = fail;
        }
        return false;   /* ARMING: keep waiting; STOPPED: never again */
    }

    s->state = WDI_SUP_RUNNING;
    s->level = !s->level;
    s->edges++;
    *level_out = s->level;
    return true;
}

wdi_sup_state_t wdi_sup_state(const wdi_sup_t *s)
{
    return s != NULL ? s->state : WDI_SUP_STOPPED;
}

wdi_stop_reason_t wdi_sup_stop_reason(const wdi_sup_t *s)
{
    return s != NULL ? s->reason : WDI_STOP_NONE;
}

/* ---- progress hand-off --------------------------------------------------- */

static volatile uint32_t s_loop_seq;
static volatile uint32_t s_rtd_valid;
static volatile uint32_t s_rtd_seq;

void wdi_progress_publish(bool rtd_valid, uint32_t rtd_seq)
{
    s_rtd_seq = rtd_seq;
    s_rtd_valid = rtd_valid ? 1u : 0u;
    s_loop_seq = s_loop_seq + 1u;
}

void wdi_progress_read(uint32_t *loop_seq, bool *rtd_valid, uint32_t *rtd_seq)
{
    if (loop_seq != NULL) {
        *loop_seq = s_loop_seq;
    }
    if (rtd_valid != NULL) {
        *rtd_valid = (s_rtd_valid != 0u);
    }
    if (rtd_seq != NULL) {
        *rtd_seq = s_rtd_seq;
    }
}
