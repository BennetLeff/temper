/**
 * @file pan_sensor_guard.c
 * @brief Pan-sensor faults and plausibility (see header).
 */

#include "pan_sensor_guard.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

void psg_default_params(psg_params_t *p)
{
    if (p == NULL) {
        return;
    }
    p->dt_s = 0.1f;
    p->t_min_c = -20.0f;
    p->t_max_c = 320.0f;
    p->rate_max_k_per_s = 30.0f;
    p->slew_max_s = 3.0f;
    p->stale_limit = 3u;
    p->xcheck_margin_k = 25.0f;  /* PCB D5: rim NTC is +-10.2 K at 250 C */
    p->xcheck_hold_s = 30.0f;
    p->xcheck_max_rise_k = 2.0f;
}

bool psg_init(psg_t *g, const psg_params_t *p)
{
    if (g == NULL || p == NULL || !(p->dt_s > 0.0f) || !(p->t_max_c > p->t_min_c) ||
        !(p->rate_max_k_per_s > 0.0f) || p->stale_limit == 0u) {
        return false;
    }
    memset(g, 0, sizeof(*g));
    g->p = *p;
    return true;
}

void psg_clear(psg_t *g)
{
    const psg_params_t p = g->p;
    (void)psg_init(g, &p);
}

psg_verdict_t psg_decode_max31865(uint8_t fault_status, bool spi_ok, psg_diag_t *diag)
{
    psg_diag_t d = PSG_DIAG_NONE;
    psg_verdict_t v = PSG_OK;
    if (!spi_ok) {
        d = PSG_DIAG_SPI_READ;
        v = PSG_FAULT_OPEN;
    } else if (fault_status & PSG_MAX31865_RTD_LOW) {
        /* Same priority as state_machine_report_rtd_device_fault(): short wins. */
        d = PSG_DIAG_REG_RTD_LOW;
        v = PSG_FAULT_SHORT;
    } else if (fault_status & PSG_MAX31865_RTD_HIGH) {
        d = PSG_DIAG_REG_RTD_HIGH;
        v = PSG_FAULT_OPEN;
    } else if (fault_status & PSG_MAX31865_REFIN_HIGH) {
        d = PSG_DIAG_REG_REFIN_HIGH;
        v = PSG_FAULT_OPEN;
    } else if (fault_status & PSG_MAX31865_REFIN_LOW) {
        d = PSG_DIAG_REG_REFIN_LOW;
        v = PSG_FAULT_OPEN;
    } else if (fault_status & PSG_MAX31865_RTDIN_LOW) {
        d = PSG_DIAG_REG_RTDIN_LOW;
        v = PSG_FAULT_OPEN;
    } else if (fault_status & PSG_MAX31865_OVUV) {
        d = PSG_DIAG_REG_OVUV;
        v = PSG_FAULT_OPEN;
    }
    if (diag != NULL) {
        *diag = d;
    }
    return v;
}

static void latch(psg_t *g, psg_verdict_t v, psg_diag_t d)
{
    if (g->latched == PSG_OK && v != PSG_OK) {
        g->latched = v;
        g->latched_diag = d;
    }
}

void psg_step(psg_t *g, const psg_input_t *in, psg_output_t *out)
{
    const psg_params_t *p = &g->p;
    psg_diag_t d = PSG_DIAG_NONE;
    bool valid = true;

    out->suspect = false;

    /* 1. Register 07h and SPI. */
    const psg_verdict_t reg = psg_decode_max31865(in->fault_status, in->spi_ok, &d);
    if (reg != PSG_OK) {
        latch(g, reg, d);
        valid = false;
    }

    /* 2. Stale DRDY. */
    if (in->fresh) {
        g->stale_count = 0u;
    } else {
        valid = false;
        if (g->stale_count < 0xFFFFu) {
            g->stale_count++;
        }
        if (g->stale_count > p->stale_limit) {
            latch(g, PSG_FAULT_OPEN, PSG_DIAG_STALE_DRDY);
        }
    }

    if (valid) {
        const float t = in->t_pt100_c;
        /* 3. Range. */
        if (!isfinite(t)) {
            latch(g, PSG_FAULT_OPEN, PSG_DIAG_NOT_FINITE);
            valid = false;
        } else if (t > p->t_max_c) {
            latch(g, PSG_FAULT_OPEN, PSG_DIAG_RANGE_HIGH);
            valid = false;
        } else if (t < p->t_min_c) {
            latch(g, PSG_FAULT_SHORT, PSG_DIAG_RANGE_LOW);
            valid = false;
        }
    }

    if (valid) {
        const float t = in->t_pt100_c;
        /* 4. Rate. */
        if (g->have_prev) {
            const float step = t - g->prev_t;
            const float lim = p->rate_max_k_per_s * p->dt_s;
            if (g->have_prev_step && fabsf(step) > lim && fabsf(g->prev_step) > lim &&
                ((step > 0.0f) != (g->prev_step > 0.0f))) {
                latch(g, PSG_FAULT_OPEN, PSG_DIAG_RATE_SPIKE);
            }
            if (fabsf(step) > lim) {
                const int8_t sg = step > 0.0f ? 1 : -1;
                g->slew_count = (sg == g->slew_sign) ? g->slew_count + 1u : 1u;
                g->slew_sign = sg;
                if ((float)g->slew_count * p->dt_s > p->slew_max_s) {
                    latch(g, PSG_FAULT_OPEN, PSG_DIAG_RATE_SLEW);
                }
            } else {
                g->slew_count = 0u;
                g->slew_sign = 0;
            }
            g->prev_step = step;
            g->have_prev_step = true;
        }
        g->prev_t = t;
        g->have_prev = true;

        /* 5. Cross-check against the rim NTC (outside the cap). */
        if (in->heating && isfinite(in->t_rim_c) && t < in->t_rim_c - p->xcheck_margin_k) {
            if (g->xcheck_count == 0u || t - g->xcheck_start_t > p->xcheck_max_rise_k) {
                /* (re)start: a reading that follows the heating is not suspect */
                g->xcheck_count = 0u;
                g->xcheck_start_t = t;
            }
            if (t < g->xcheck_start_t) {
                g->xcheck_start_t = t;   /* rise is measured from the lowest reading */
            }
            g->xcheck_count++;
            if ((float)g->xcheck_count * p->dt_s >= p->xcheck_hold_s) {
                out->suspect = true;
                g->xcheck_count = 0u;
            }
        } else {
            g->xcheck_count = 0u;
        }
    }

    out->verdict = g->latched;
    out->diag = g->latched_diag;
    out->sample_valid = valid && g->latched == PSG_OK;
}

void psg_report(psg_verdict_t v, psg_fault_sink_t sink, void *context)
{
    if (sink == NULL || v == PSG_OK) {
        return;
    }
    sink(v == PSG_FAULT_SHORT, v == PSG_FAULT_OPEN, context);
}
