/**
 * @file plant_gain.c
 * @brief Online a = eta / C_total identification (see header).
 */

#include "plant_gain.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

void pg_default_params(pg_params_t *p)
{
    if (p == NULL) {
        return;
    }
    p->dt_s = 0.1f;
    p->block_samples = 10u;
    p->window_blocks = 20u;
    p->a0_k_per_j = 1.8e-3f;      /* lightest modelled pan: least power per K/s */
    p->a_min_k_per_j = 5e-5f;
    p->a_max_k_per_j = 5e-3f;
    p->prior_rel_sd = 3.0f;
    p->lag_s = 0.0f;
    p->k_loss_w_per_k = 0.0f;
    p->t_amb_c = 25.0f;
    p->rise_min_k = 10.0f;
    p->valid_rise_k = 20.0f;
    p->valid_energy_j = 30e3f;
    p->forget_first = 1.0f;
    p->forget_later = 0.99f;
    p->update_later_ramps = true;
}

static void clear_window(pg_t *g)
{
    g->head = 0u;
    g->count = 0u;
}

bool pg_init(pg_t *g, const pg_params_t *p)
{
    if (g == NULL || p == NULL) {
        return false;
    }
    if (!(p->dt_s > 0.0f) || p->block_samples == 0u || p->window_blocks == 0u ||
        p->window_blocks + 1u > PG_MAX_BLOCKS || !(p->a0_k_per_j > 0.0f) ||
        !(p->a_min_k_per_j > 0.0f) || !(p->a_max_k_per_j > p->a_min_k_per_j) ||
        !(p->forget_first > 0.0f && p->forget_first <= 1.0f) ||
        !(p->forget_later > 0.0f && p->forget_later <= 1.0f) || !(p->lag_s >= 0.0f)) {
        return false;
    }
    memset(g, 0, sizeof(*g));
    g->p = *p;
    g->theta = p->a0_k_per_j;
    {
        const float sd = p->prior_rel_sd * p->a0_k_per_j;
        g->pcov = sd * sd;
    }
    g->forget = p->forget_first;
    g->phase_first = true;
    return true;
}

void pg_begin_phase(pg_t *g, bool first)
{
    g->phase_first = first;
    g->phase_has_start = false;
    g->forget = first ? g->p.forget_first : g->p.forget_later;
    g->t_acc = 0.0f;
    g->n_acc = 0u;
    g->gate_acc = true;
    g->src_block_set = false;
    clear_window(g);
}

float pg_gain(const pg_t *g)
{
    float a = g->valid ? g->theta : g->p.a0_k_per_j;
    if (a < g->p.a_min_k_per_j) {
        a = g->p.a_min_k_per_j;
    }
    if (a > g->p.a_max_k_per_j) {
        a = g->p.a_max_k_per_j;
    }
    return a;
}

static void rls_update(pg_t *g, float phi, float y)
{
    const float lam = g->forget;
    const float pp = g->pcov;
    const float den = lam + phi * pp * phi;
    if (!(den > 0.0f)) {
        return;
    }
    const float k = pp * phi / den;
    g->theta += k * (y - phi * g->theta);
    g->pcov = (pp - k * phi * pp) / lam;
    g->updates++;
}

void pg_update(pg_t *g, float t_hat_c, float power_w, pg_power_source_t src, bool gate)
{
    const pg_params_t *p = &g->p;
    const double dt = (double)p->dt_s;

    if (!isfinite(t_hat_c) || !isfinite(power_w)) {
        gate = false;
        power_w = 0.0f;
        t_hat_c = (g->n_acc > 0u) ? g->t_acc / (float)g->n_acc : p->t_amb_c;
    }
    if (power_w < 0.0f) {
        power_w = 0.0f;
    }

    g->e_j += (double)power_w * dt;
    if (p->lag_s > 0.0f) {
        g->e_lag_j += dt / (double)p->lag_s * (g->e_j - g->e_lag_j);
    } else {
        g->e_lag_j = g->e_j;
    }
    g->s_ks += ((double)t_hat_c - (double)p->t_amb_c) * dt;

    if (g->n_acc == 0u) {
        g->gate_acc = true;
        g->src_block = src;
        g->src_block_set = true;
    }
    g->t_acc += t_hat_c;
    g->n_acc++;
    g->gate_acc = g->gate_acc && gate;
    if (g->src_block_set && src != g->src_block) {
        /* Mixed provenance inside a block: the block is not usable. */
        g->gate_acc = false;
    }
    if (g->n_acc < p->block_samples) {
        return;
    }

    /* Close a 1 s block. */
    const float tb = g->t_acc / (float)g->n_acc;
    const bool block_gate = g->gate_acc;
    const pg_power_source_t bsrc = g->src_block;
    g->t_acc = 0.0f;
    g->n_acc = 0u;

    if (!g->phase_has_start) {
        g->phase_t_start = tb;
        g->phase_has_start = true;
    }
    g->phase_rise_k = tb - g->phase_t_start;

    if (g->count > 0u && bsrc != g->src_window) {
        /* Never mix power provenances inside one regression window. */
        clear_window(g);
    }
    g->src_window = bsrc;

    pg_block_t *b = &g->ring[g->head];
    b->t = tb;
    b->e_lag = (float)g->e_lag_j;
    b->s = (float)g->s_ks;
    b->gated = block_gate && (g->phase_rise_k >= p->rise_min_k) &&
               (g->phase_first || p->update_later_ramps);
    g->head = (uint16_t)((g->head + 1u) % PG_MAX_BLOCKS);
    if (g->count < p->window_blocks + 1u) {
        g->count++;
    }
    if (g->count < p->window_blocks + 1u) {
        return;
    }

    /* Window: oldest of the last window_blocks+1 blocks to the newest. */
    bool all_gated = true;
    for (uint16_t i = 0u; i <= p->window_blocks; i++) {
        const uint16_t idx = (uint16_t)((g->head + PG_MAX_BLOCKS - 1u - i) % PG_MAX_BLOCKS);
        all_gated = all_gated && g->ring[idx].gated;
    }
    if (!all_gated) {
        return;
    }
    const pg_block_t *old = &g->ring[(g->head + PG_MAX_BLOCKS - 1u - p->window_blocks) % PG_MAX_BLOCKS];
    const pg_block_t *now = &g->ring[(g->head + PG_MAX_BLOCKS - 1u) % PG_MAX_BLOCKS];
    const float de = now->e_lag - old->e_lag;
    const float ds = now->s - old->s;
    const float phi = de - p->k_loss_w_per_k * ds;
    const float y = now->t - old->t;
    if (!(phi > 0.0f)) {
        return;
    }
    rls_update(g, phi, y);
    g->regressed_energy_j += de;
    g->src_mask |= (uint8_t)(1u << bsrc);
    if (!g->valid && g->phase_rise_k >= p->valid_rise_k && g->regressed_energy_j >= p->valid_energy_j) {
        g->valid = true;
    }
}
