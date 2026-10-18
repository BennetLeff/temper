/**
 * @file pan_supervisor.c
 * @brief C1 runaway supervision (see header).
 */

#include "pan_supervisor.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

void psup_default_params(psup_params_t *p)
{
    if (p == NULL) {
        return;
    }
    p->rate_block_ms = 1000u;
    p->rate_max_k_per_s = 15.0f;
    p->rate_blocks_required = 5u;
    p->dt_s = 0.1f;
    p->margin_k = 10.0f;
    p->settle_s = 0.3f;
    p->disobey_current_a = 0.5f;
    p->disobey_hold_s = 0.5f;
    p->disobey_excess_a = 2.5f;
    p->cmd_v_min = 100.0f;
    p->rise_hold_s = 20.0f;
    p->rise_window_s = 5.0f;
    p->rise_min_k = 2.0f;
}

bool psup_init(psup_t *s, const psup_params_t *p)
{
    if (s == NULL || p == NULL || p->rate_block_ms == 0u || p->rate_blocks_required == 0u ||
        !(p->dt_s > 0.0f) || !(p->rise_window_s >= 1.0f) || !(p->cmd_v_min > 0.0f) ||
        p->settle_s / p->dt_s > 8.0f ||
        (uint32_t)p->rise_window_s + 1u > PSUP_MAX_BLOCKS) {
        return false;
    }
    memset(s, 0, sizeof(*s));
    s->p = *p;
    return true;
}

void psup_rate_reset(psup_t *s)
{
    memset(&s->rate, 0, sizeof(s->rate));
}

void psup_r2_reset(psup_t *s)
{
    s->latched = PSUP_OK;
    s->zero_cmd_s = 0.0f;
    s->disobey_s = 0.0f;
    s->p_hist_n = 0u;
    s->blk_acc = 0.0f;
    s->blk_n = 0u;
    s->blk_head = 0u;
    s->blk_count = 0u;
}

bool psup_rate_sample(psup_t *s, float t_raw_c, uint32_t now_ms)
{
    psup_rate_t *r = &s->rate;
    if (!isfinite(t_raw_c)) {
        return false;   /* the absolute check owns non-finite readings */
    }
    if (!r->r1_have_block) {
        r->r1_have_block = true;
        r->r1_block_start_ms = now_ms;
        r->r1_sum = 0.0;
        r->r1_n = 0u;
    }
    r->r1_sum += (double)t_raw_c;
    r->r1_n++;
    const uint32_t age = now_ms - r->r1_block_start_ms;
    if (age < s->p.rate_block_ms) {
        return false;
    }
    const float mean = (float)(r->r1_sum / (double)r->r1_n);
    const float block_s = (float)age / 1000.0f;
    bool trip = false;
    if (r->r1_have_prev) {
        r->r1_last_rise = (mean - r->r1_prev_mean) / block_s;
        if (r->r1_last_rise > s->p.rate_max_k_per_s) {
            if (r->r1_count < 255u) {
                r->r1_count++;
            }
        } else {
            r->r1_count = 0u;
        }
        trip = r->r1_count >= s->p.rate_blocks_required;
    }
    r->r1_prev_mean = mean;
    r->r1_have_prev = true;
    r->r1_block_start_ms = now_ms;
    r->r1_sum = 0.0;
    r->r1_n = 0u;
    return trip;
}

void psup_step(psup_t *s, const psup_input_t *in, psup_output_t *out)
{
    const psup_params_t *p = &s->p;
    memset(out, 0, sizeof(*out));

    float t_hi = in->t_hat_c;
    if (isfinite(in->t_raw_c) && (!isfinite(t_hi) || in->t_raw_c > t_hi)) {
        t_hi = in->t_raw_c;
    }
    const bool over = isfinite(t_hi) && t_hi > in->setpoint_c + p->margin_k;
    out->force_zero = over;
    const float p_eff = over ? 0.0f : in->p_cmd_w;

    if (p_eff <= 0.0f) {
        s->zero_cmd_s += p->dt_s;
    } else {
        s->zero_cmd_s = 0.0f;
    }

    /* 2a: the power stage is not obeying. The expected current allows for the
     * largest command of the last settle_s (the stage follows a step down
     * within a period). */
    const uint8_t n_hist = (uint8_t)lroundf(p->settle_s / p->dt_s) + 1u;
    for (uint8_t i = (uint8_t)(n_hist - 1u); i > 0u; i--) {
        s->p_hist[i] = s->p_hist[i - 1u];
    }
    s->p_hist[0] = p_eff;
    if (s->p_hist_n < n_hist) {
        s->p_hist_n++;
    }
    float p_recent = 0.0f;
    for (uint8_t i = 0u; i < s->p_hist_n; i++) {
        p_recent = s->p_hist[i] > p_recent ? s->p_hist[i] : p_recent;
    }
    const bool zero_disobey = s->zero_cmd_s >= p->settle_s && in->bus_current_a > p->disobey_current_a;
    const bool excess = s->p_hist_n >= n_hist &&
                        in->bus_current_a > p_recent / p->cmd_v_min + p->disobey_excess_a;
    if (in->current_valid && (zero_disobey || excess)) {
        s->disobey_s += p->dt_s;
    } else {
        s->disobey_s = 0.0f;
    }
    if (s->latched == PSUP_OK && s->disobey_s >= p->disobey_hold_s) {
        s->latched = PSUP_LATCH_DISOBEY;
    }

    /* 2b: 1 s block means of the high reading, rise over the window. */
    if (isfinite(t_hi)) {
        s->blk_acc += t_hi;
        s->blk_n++;
    }
    const uint16_t per_block = (uint16_t)lroundf(1.0f / p->dt_s);
    if (s->blk_n >= per_block) {
        s->blk[s->blk_head] = s->blk_acc / (float)s->blk_n;
        s->blk_head = (uint16_t)((s->blk_head + 1u) % PSUP_MAX_BLOCKS);
        if (s->blk_count < PSUP_MAX_BLOCKS) {
            s->blk_count++;
        }
        s->blk_acc = 0.0f;
        s->blk_n = 0u;
    }
    const uint16_t w = (uint16_t)p->rise_window_s;
    if (s->blk_count > w) {
        const float now_b = s->blk[(s->blk_head + PSUP_MAX_BLOCKS - 1u) % PSUP_MAX_BLOCKS];
        const float old_b = s->blk[(s->blk_head + PSUP_MAX_BLOCKS - 1u - w) % PSUP_MAX_BLOCKS];
        out->rise_k = now_b - old_b;
        if (s->latched == PSUP_OK && over && s->zero_cmd_s >= p->rise_hold_s && out->rise_k >= p->rise_min_k) {
            s->latched = PSUP_LATCH_RISING;
        }
    }
    out->latch = s->latched;
}
