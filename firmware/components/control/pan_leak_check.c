/**
 * @file pan_leak_check.c
 * @brief Element-parallel Pt100 leakage check (see header).
 */

#include "pan_leak_check.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "contact_check.h"

void plc_default_params(plc_params_t *p)
{
    if (p == NULL) {
        return;
    }
    p->dt_s = 0.1f;
    p->cycles = 2u;
    p->gap_s = 120.0f;
    p->rim_fall_k = 5.0f;
    p->pt_rise_k = 2.0f;
}

bool plc_init(plc_t *c, const plc_params_t *p)
{
    if (c == NULL || p == NULL || !(p->dt_s > 0.0f) || p->cycles < 1u || !(p->gap_s > 0.0f) ||
        !(p->rim_fall_k >= 0.0f) || !(p->pt_rise_k >= 0.0f)) {
        return false;
    }
    memset(c, 0, sizeof(*c));
    c->p = *p;
    return true;
}

static void restart(plc_t *c)
{
    c->pending = false;
    c->probing = false;
    c->count = 0u;
}

bool plc_step(plc_t *c, bool suspect, int cc_event, float t_pt100_c, float t_rim_c)
{
    const plc_params_t *p = &c->p;
    c->t_s += p->dt_s;
    if (c->latched) {
        return true;
    }
    if (cc_event == (int)CC_EVT_LOST || cc_event == (int)CC_EVT_RESTORED) {
        restart(c);   /* contact really was in doubt: not a leak signature */
        c->d1_busy = cc_event == (int)CC_EVT_LOST;   /* LOST retries until RESTORED */
        return false;
    }
    if (suspect && !c->d1_busy) {
        if (!isfinite(t_pt100_c) || !isfinite(t_rim_c)) {
            restart(c);
            return false;
        }
        c->pending = true;
        c->sus_t_s = c->t_s;
        c->sus_pt_c = t_pt100_c;
        c->sus_rim_c = t_rim_c;
    }
    /* Only a probe that starts at or after the suspect answers it. A probe
     * already running (the contact-shift window's, D-CSW, or D1's own
     * trigger) did not test the cross-check's doubt: its verdict does not
     * count, and a suspect raised during it is not armed. */
    if (cc_event == (int)CC_EVT_SUSPECT) {
        c->d1_busy = true;
        c->probing = c->pending;
        c->pending = false;
    }
    if (cc_event == (int)CC_EVT_PROBE_PASSED) {
        c->d1_busy = false;
    }
    if (cc_event == (int)CC_EVT_PROBE_PASSED && c->probing) {
        c->probing = false;
        const bool chained = c->count > 0u && c->sus_t_s - c->last_t_s <= p->gap_s &&
                             c->sus_rim_c - c->last_rim_c >= -p->rim_fall_k &&
                             c->sus_pt_c - c->last_pt_c <= p->pt_rise_k;
        c->count = chained ? (uint8_t)(c->count + 1u) : 1u;
        c->last_t_s = c->sus_t_s;
        c->last_pt_c = c->sus_pt_c;
        c->last_rim_c = c->sus_rim_c;
        if (c->count >= p->cycles) {
            c->latched = true;
        }
    }
    return c->latched;
}
