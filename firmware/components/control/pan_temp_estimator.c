/**
 * @file pan_temp_estimator.c
 * @brief sensor-r3 C1 fixed-contact Kalman filter (see header).
 */

#include "pan_temp_estimator.h"

#include <math.h>
#include <stddef.h>

void pte_default_params(pte_params_t *p)
{
    if (p == NULL) {
        return;
    }
    p->c_cap_j_per_k = 0.0404f;
    p->c_el_j_per_k = 0.008175f;
    p->g_bond_w_per_k = 0.0612f;
    p->g_leak_w_per_k = 0.0008f;
    p->contact_area_m2 = 45.4e-6f;
    p->h_nom_w_per_m2k = 1300.0f;
    p->dt_s = 0.1f;
    p->substeps = 5u;
    p->q_per_s[0] = 0.02f;
    p->q_per_s[1] = 0.05f;
    p->q_per_s[2] = 1e-4f;
    p->q_per_s[3] = 1e-4f;
    p->p0[0] = 1.0f;
    p->p0[1] = 0.25f;
    p->p0[2] = 1.0f;
    p->p0[3] = 1.0f;
    p->sigma_k = 0.2f;
}

/* One Euler substep of the cartridge model, in double, for the init-time map.
 * Mirrors estimator_study.sensor_deriv(): derivatives from the old values,
 * then every node advanced. u = sink temperature. */
static void substep(const pte_params_t *p, double gc, double h, double x[PTE_NX], double u)
{
    const double tp = x[0], v = x[1], tcap = x[2], tel = x[3];
    const double dcap = (gc * (tp - tcap) - (double)p->g_leak_w_per_k * (tcap - u)
                         - (double)p->g_bond_w_per_k * (tcap - tel)) / (double)p->c_cap_j_per_k;
    const double dele = (double)p->g_bond_w_per_k * (tcap - tel) / (double)p->c_el_j_per_k;
    x[0] = tp + h * v;
    x[1] = v;
    x[2] = tcap + h * dcap;
    x[3] = tel + h * dele;
}

static void period_map(const pte_params_t *p, double x[PTE_NX], double u)
{
    const double gc = (double)p->h_nom_w_per_m2k * (double)p->contact_area_m2;
    const double h = (double)p->dt_s / (double)p->substeps;
    for (uint8_t i = 0; i < p->substeps; i++) {
        substep(p, gc, h, x, u);
    }
}

/* The map is affine: x' = F x + g u. Columns of F from unit states with
 * u = 0; g from the zero state with u = 1. */
static void compose(pte_t *f)
{
    const pte_params_t *p = &f->p;
    for (int j = 0; j < PTE_NX; j++) {
        double e[PTE_NX] = {0.0, 0.0, 0.0, 0.0};
        e[j] = 1.0;
        period_map(p, e, 0.0);
        for (int i = 0; i < PTE_NX; i++) {
            f->F[i][j] = (float)e[i];
        }
    }
    {
        double z[PTE_NX] = {0.0, 0.0, 0.0, 0.0};
        period_map(p, z, 1.0);
        for (int i = 0; i < PTE_NX; i++) {
            f->g_sink[i] = (float)z[i];
        }
    }
}

bool pte_set_contact(pte_t *f, float h_w_per_m2k)
{
    if (f == NULL || !(h_w_per_m2k > 0.0f) || !isfinite(h_w_per_m2k)) {
        return false;
    }
    f->p.h_nom_w_per_m2k = h_w_per_m2k;
    compose(f);
    return true;
}

bool pte_init(pte_t *f, const pte_params_t *p, float t0_c)
{
    if (f == NULL || p == NULL) {
        return false;
    }
    if (!(p->c_cap_j_per_k > 0.0f) || !(p->c_el_j_per_k > 0.0f) || !(p->g_bond_w_per_k > 0.0f) ||
        !(p->g_leak_w_per_k >= 0.0f) || !(p->contact_area_m2 > 0.0f) || !(p->h_nom_w_per_m2k > 0.0f) ||
        !(p->dt_s > 0.0f) || p->substeps == 0u || !(p->sigma_k > 0.0f)) {
        return false;
    }
    f->p = *p;
    compose(f);

    f->x[0] = t0_c;
    f->x[1] = 0.0f;
    f->x[2] = t0_c;
    f->x[3] = t0_c;
    for (int i = 0; i < PTE_NX; i++) {
        for (int j = 0; j < PTE_NX; j++) {
            f->P[i][j] = (i == j) ? p->p0[i] : 0.0f;
        }
    }
    f->r = p->sigma_k * p->sigma_k;
    f->steps = 0u;
    return true;
}

float pte_predict(pte_t *f, float t_sink_c)
{
    float xn[PTE_NX];
    float FP[PTE_NX][PTE_NX];

    for (int i = 0; i < PTE_NX; i++) {
        float acc = f->g_sink[i] * t_sink_c;
        for (int j = 0; j < PTE_NX; j++) {
            acc += f->F[i][j] * f->x[j];
        }
        xn[i] = acc;
    }
    for (int i = 0; i < PTE_NX; i++) {
        for (int j = 0; j < PTE_NX; j++) {
            float acc = 0.0f;
            for (int k = 0; k < PTE_NX; k++) {
                acc += f->F[i][k] * f->P[k][j];
            }
            FP[i][j] = acc;
        }
    }
    for (int i = 0; i < PTE_NX; i++) {
        for (int j = 0; j < PTE_NX; j++) {
            float acc = 0.0f;
            for (int k = 0; k < PTE_NX; k++) {
                acc += FP[i][k] * f->F[j][k];
            }
            f->P[i][j] = acc;
        }
        f->P[i][i] += f->p.q_per_s[i] * f->p.dt_s;
    }
    for (int i = 0; i < PTE_NX; i++) {
        f->x[i] = xn[i];
    }
    f->steps++;
    return f->x[0];
}

float pte_step(pte_t *f, float y_pt100_c, float t_sink_c)
{
    const int m = 3; /* measured node: T_el */
    float k_gain[PTE_NX];
    float prow[PTE_NX];

    (void)pte_predict(f, t_sink_c);

    const float s = f->P[m][m] + f->r;
    const float innov = y_pt100_c - f->x[m];
    for (int i = 0; i < PTE_NX; i++) {
        k_gain[i] = f->P[i][m] / s;
        prow[i] = f->P[m][i];
    }
    for (int i = 0; i < PTE_NX; i++) {
        f->x[i] += k_gain[i] * innov;
        for (int j = 0; j < PTE_NX; j++) {
            f->P[i][j] -= k_gain[i] * prow[j];
        }
    }
    /* Keep P symmetric, as the reference does. */
    for (int i = 0; i < PTE_NX; i++) {
        for (int j = i + 1; j < PTE_NX; j++) {
            const float a = 0.5f * (f->P[i][j] + f->P[j][i]);
            f->P[i][j] = a;
            f->P[j][i] = a;
        }
    }
    return f->x[0];
}
