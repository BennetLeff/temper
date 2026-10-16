/**
 * @file pan_cold_soak.c
 * @brief Cold-soak Pt100 leakage check (see header; DECISIONS.md D-SOAK).
 */

#include "pan_cold_soak.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

void pcs_default_params(pcs_params_t *p)
{
    if (p == NULL) {
        return;
    }
    p->threshold_k = PCS_THRESHOLD_K;
    p->soak_n_s = PCS_SOAK_N_S;
    p->window_s = PCS_WINDOW_S;
    p->bucket_s = 60.0f;
    p->hs_flat_k = PCS_HS_FLAT_K;
    p->pt_flat_k = PCS_PT_FLAT_K;
    p->hs_max_c = PCS_HS_MAX_C;
}

static unsigned window_buckets(const pcs_params_t *p)
{
    return (unsigned)ceilf(p->window_s / p->bucket_s) + 1u;
}

bool pcs_init(pcs_t *s, const pcs_params_t *p, uint32_t now_ms)
{
    if (s == NULL || p == NULL || !(p->threshold_k > 0.0f) || !(p->bucket_s >= 1.0f) ||
        !(p->window_s >= p->bucket_s) || !(p->soak_n_s >= p->window_s) || !(p->hs_flat_k > 0.0f) ||
        !(p->pt_flat_k > 0.0f) || !isfinite(p->hs_max_c) || window_buckets(p) > PCS_BUCKET_MAX) {
        return false;
    }
    memset(s, 0, sizeof(*s));
    s->p = *p;
    s->bucket_ms = (uint32_t)lroundf(p->bucket_s * 1000.0f);
    s->last_active_ms = now_ms;   /* power-up: the last cook's time is unknown */
    return true;
}

/* A uint32 difference above this means the clock went backwards. */
#define PCS_BACKWARDS 0x80000000u

void pcs_note(pcs_t *s, uint32_t now_ms, bool coil_active, float pt_c, bool hs_valid, float hs_c)
{
    const uint32_t since = (uint32_t)(now_ms - s->last_active_ms);
    if (coil_active || since >= PCS_BACKWARDS) {
        s->last_active_ms = now_ms;
        s->count = 0u;
        return;
    }
    /* Keep the coil-off time from wrapping (49.7 days): once far past the
     * soak, hold it at twice the soak. */
    const uint32_t cap_ms = 2u * (uint32_t)lroundf(s->p.soak_n_s * 1000.0f);
    if (since > cap_ms) {
        s->last_active_ms = now_ms - cap_ms;
    }
    if (s->count != 0u && (uint32_t)(now_ms - s->b[s->head].t0_ms) >= PCS_BACKWARDS) {
        s->count = 0u;
    }
    if (s->count == 0u || (uint32_t)(now_ms - s->b[s->head].t0_ms) >= s->bucket_ms) {
        s->head = (s->head + 1u) % PCS_BUCKET_MAX;
        s->count = s->count < PCS_BUCKET_MAX ? s->count + 1u : PCS_BUCKET_MAX;
        pcs_bucket_t *nb = &s->b[s->head];
        nb->t0_ms = now_ms;
        nb->pt_min = INFINITY;
        nb->pt_max = -INFINITY;
        nb->hs_min = INFINITY;
        nb->hs_max = -INFINITY;
        nb->pt_ok = true;
        nb->hs_ok = true;
    }
    pcs_bucket_t *b = &s->b[s->head];
    if (isfinite(pt_c)) {
        b->pt_min = pt_c < b->pt_min ? pt_c : b->pt_min;
        b->pt_max = pt_c > b->pt_max ? pt_c : b->pt_max;
    } else {
        b->pt_ok = false;
    }
    if (hs_valid && isfinite(hs_c)) {
        b->hs_min = hs_c < b->hs_min ? hs_c : b->hs_min;
        b->hs_max = hs_c > b->hs_max ? hs_c : b->hs_max;
    } else {
        b->hs_ok = false;
    }
}

pcs_result_t pcs_evaluate(const pcs_t *s, uint32_t now_ms, float pt_c, bool hs_valid, float hs_c,
                          bool rim_saturated)
{
    pcs_result_t r = {.verdict = PCS_NONE, .off_s = NAN, .gap_k = NAN, .hs_c = hs_c, .pt_c = pt_c};
    const pcs_params_t *p = &s->p;
    const uint32_t since = (uint32_t)(now_ms - s->last_active_ms);
    r.off_s = since >= PCS_BACKWARDS ? 0.0f : (float)since / 1000.0f;
    if (r.off_s < p->soak_n_s) {
        r.verdict = PCS_SKIP_NOT_SOAKED;
        return r;
    }
    const unsigned need = window_buckets(p);
    const uint32_t window_ms = (uint32_t)lroundf(p->window_s * 1000.0f);
    const pcs_bucket_t *oldest = &s->b[(s->head + PCS_BUCKET_MAX - (need - 1u)) % PCS_BUCKET_MAX];
    const uint32_t span = (uint32_t)(now_ms - oldest->t0_ms);
    if (s->count < need || span < window_ms || span >= PCS_BACKWARDS) {
        r.verdict = PCS_SKIP_HISTORY;
        return r;
    }
    float pt_lo = INFINITY, pt_hi = -INFINITY, hs_lo = INFINITY, hs_hi = -INFINITY;
    bool pt_ok = isfinite(pt_c);
    bool hs_ok = hs_valid && isfinite(hs_c);
    for (unsigned k = 0u; k < need; k++) {
        const pcs_bucket_t *b = &s->b[(s->head + PCS_BUCKET_MAX - k) % PCS_BUCKET_MAX];
        pt_ok = pt_ok && b->pt_ok;
        hs_ok = hs_ok && b->hs_ok;
        pt_lo = b->pt_min < pt_lo ? b->pt_min : pt_lo;
        pt_hi = b->pt_max > pt_hi ? b->pt_max : pt_hi;
        hs_lo = b->hs_min < hs_lo ? b->hs_min : hs_lo;
        hs_hi = b->hs_max > hs_hi ? b->hs_max : hs_hi;
    }
    if (!pt_ok) {
        r.verdict = PCS_SKIP_PT_INVALID;
        return r;
    }
    if (!hs_ok) {
        r.verdict = PCS_SKIP_HS_INVALID;
        return r;
    }
    if (hs_c > p->hs_max_c || hs_hi > p->hs_max_c) {
        r.verdict = PCS_SKIP_HS_WARM;
        return r;
    }
    if (hs_hi - hs_lo > p->hs_flat_k) {
        r.verdict = PCS_SKIP_HS_DRIFT;
        return r;
    }
    if (pt_hi - pt_lo > p->pt_flat_k) {
        r.verdict = PCS_SKIP_PT_DRIFT;
        return r;
    }
    if (!rim_saturated) {
        r.verdict = PCS_SKIP_RIM_WARM;
        return r;
    }
    r.gap_k = hs_lo - pt_hi;
    r.verdict = (r.gap_k > p->threshold_k && hs_c - pt_c > p->threshold_k) ? PCS_LEAK : PCS_PASS;
    return r;
}

bool pcs_agrees(const pcs_t *s, float pt_c, bool hs_valid, float hs_c)
{
    return hs_valid && isfinite(hs_c) && isfinite(pt_c) && hs_c - pt_c <= s->p.threshold_k;
}

const char *pcs_verdict_name(pcs_verdict_t v)
{
    switch (v) {
    case PCS_NONE: return "none";
    case PCS_PASS: return "pass";
    case PCS_LEAK: return "leak";
    case PCS_SKIP_NOT_SOAKED: return "skip: not soaked";
    case PCS_SKIP_HISTORY: return "skip: history";
    case PCS_SKIP_HS_INVALID: return "skip: heatsink not valid";
    case PCS_SKIP_HS_WARM: return "skip: heatsink warm";
    case PCS_SKIP_HS_DRIFT: return "skip: heatsink drifting";
    case PCS_SKIP_PT_INVALID: return "skip: no Pt100 reading";
    case PCS_SKIP_PT_DRIFT: return "skip: Pt100 drifting";
    case PCS_SKIP_RIM_WARM: return "skip: rim warm";
    default: return "?";
    }
}
