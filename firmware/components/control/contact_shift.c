/**
 * @file contact_shift.c
 * @brief sensor-r3 C1 contact-shift window (see header). Mirrors
 *        output/temper-sensor-r3/robustness/shift_kf.py step for step.
 */

#include "contact_shift.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

void csw_default_params(csw_params_t *p)
{
    if (p == NULL) {
        return;
    }
    p->enable = true;
    p->up_enable = true;
    p->dt_s = 0.1f;
    p->p_max_w = 1800.0f;
    p->n_recent = 15u;
    p->n_before = 30u;
    p->dv_trig_k_per_s = 0.6f;
    p->p_recent_s = 8.0f;
    p->dp_frac = 0.10f;
    p->start_holdoff_s = 30.0f;
    p->holdoff_s = 20.0f;
    p->trig_lag_s = 2.5f;
    p->v_ref_s = 5.0f;
    p->p0_t_k = 0.1f;
    p->p0_v_k_per_s = 0.03f;
    p->q_t = 1e-4f;
    p->q_v = 1e-4f;
    p->p0_lng = 1.0f;
    p->q_lng = 0.002f;
    p->h_floor_w_per_m2k = 150.0f;
    p->win_min_s = 4.0f;
    p->win_min_hold_s = 8.0f;
    p->win_max_s = 12.0f;
    p->settle_s = 2.0f;
    p->settle_dlng = 0.04f;
    p->min_drop = 0.25f;
    p->max_sd_lng = 0.2f;
    p->accept_bias_sd = 1.0f;
}

static uint16_t steps(float s, float dt)
{
    return (uint16_t)lroundf(s / dt);
}

bool csw_init(csw_t *c, const csw_params_t *p, const pte_params_t *k)
{
    if (c == NULL || p == NULL || k == NULL || !(p->dt_s > 0.0f) || !(k->contact_area_m2 > 0.0f) ||
        !(k->h_nom_w_per_m2k > 0.0f) || !(p->h_floor_w_per_m2k > 0.0f) || p->n_recent < 3u || p->n_before < 3u) {
        return false;
    }
    memset(c, 0, sizeof(*c));
    c->p = *p;
    c->k = *k;
    c->nlag = steps(p->trig_lag_s, p->dt_s);
    c->npw = steps(p->p_recent_s, p->dt_s);
    c->nref = steps(p->v_ref_s, p->dt_s);
    c->nblk = steps(1.0f, p->dt_s);
    uint16_t nk = (uint16_t)(p->n_recent + p->n_before);
    if (2u * c->npw > nk) {
        nk = (uint16_t)(2u * c->npw);
    }
    if ((uint16_t)(c->nlag + 1u + c->nref) > nk) {
        nk = (uint16_t)(c->nlag + 1u + c->nref);
    }
    c->nkeep = nk;
    if (c->nkeep > CSW_HIST || c->nlag + 1u > CSW_SNAP ||
        c->nlag + 1u + steps(p->win_max_s, p->dt_s) + 1u > CSW_WIN || c->nblk == 0u || c->npw % c->nblk != 0u) {
        return false;
    }
    c->g_nom = (double)k->h_nom_w_per_m2k * (double)k->contact_area_m2;
    c->g = c->g_nom;
    return true;
}

/* ---- the cartridge map in double (as pte_init composes it) ------------------- */
static void substep(const pte_params_t *k, double gc, double h, double x[PTE_NX], double u)
{
    const double tp = x[0], v = x[1], tcap = x[2], tel = x[3];
    const double dcap = (gc * (tp - tcap) - (double)k->g_leak_w_per_k * (tcap - u)
                         - (double)k->g_bond_w_per_k * (tcap - tel)) / (double)k->c_cap_j_per_k;
    const double dele = (double)k->g_bond_w_per_k * (tcap - tel) / (double)k->c_el_j_per_k;
    x[0] = tp + h * v;
    x[1] = v;
    x[2] = tcap + h * dcap;
    x[3] = tel + h * dele;
}

/* x' = F x + g u for contact gc, applied directly: out = map(x, u). */
static void map_apply(const pte_params_t *k, double gc, const double x[PTE_NX], double u, double out[PTE_NX])
{
    const double h = (double)k->dt_s / (double)k->substeps;
    for (int i = 0; i < PTE_NX; i++) {
        out[i] = x[i];
    }
    for (uint8_t s = 0; s < k->substeps; s++) {
        substep(k, gc, h, out, u);
    }
}

static void map_matrix(const pte_params_t *k, double gc, double F[PTE_NX][PTE_NX])
{
    for (int j = 0; j < PTE_NX; j++) {
        double e[PTE_NX] = {0.0, 0.0, 0.0, 0.0};
        double o[PTE_NX];
        e[j] = 1.0;
        map_apply(k, gc, e, 0.0, o);
        for (int i = 0; i < PTE_NX; i++) {
            F[i][j] = o[i];
        }
    }
}

/* ---- history helpers (index 0 = oldest kept) ---------------------------------- */
static void push(float *a, uint16_t count, uint16_t cap, float v)
{
    if (count < cap) {
        a[count] = v;
    } else {
        memmove(a, a + 1, (size_t)(cap - 1u) * sizeof(float));
        a[cap - 1u] = v;
    }
}

/* Least-squares slope (per s) of a[i0 .. i0+n-1] sampled dt apart. */
static double slope(const float *a, uint16_t i0, uint16_t n, double dt)
{
    double tm = 0.0, ym = 0.0;
    for (uint16_t i = 0; i < n; i++) {
        tm += (double)i * dt;
        ym += (double)a[i0 + i];
    }
    tm /= (double)n;
    ym /= (double)n;
    double sxy = 0.0, sxx = 0.0;
    for (uint16_t i = 0; i < n; i++) {
        const double dx = (double)i * dt - tm;
        sxy += dx * ((double)a[i0 + i] - ym);
        sxx += dx * dx;
    }
    return sxx > 0.0 ? sxy / sxx : 0.0;
}

/* +1 down window, -1 up window, 0 none (shift_kf.ShiftKF.triggered). */
static int triggered(const csw_t *c)
{
    const csw_params_t *p = &c->p;
    if (c->count < c->nkeep) {
        return 0;
    }
    const uint16_t n1 = p->n_recent, n2 = p->n_before;
    const uint16_t base = (uint16_t)(c->count - n1 - n2);
    const double dt = (double)p->dt_s;
    const double dv = slope(c->y, (uint16_t)(base + n2), n1, dt) - slope(c->y, base, n2, dt);
    const uint16_t p0 = (uint16_t)(c->count - 2u * c->npw);
    double pb = 0.0;
    for (uint16_t i = 0; i < c->npw; i++) {
        pb += (double)c->pw[p0 + i];
    }
    pb /= (double)c->npw;
    double bmin = 1e30, bmax = -1e30;
    for (uint16_t b = 0; b < c->npw / c->nblk; b++) {
        double m = 0.0;
        for (uint16_t i = 0; i < c->nblk; i++) {
            m += (double)c->pw[p0 + c->npw + b * c->nblk + i];
        }
        m /= (double)c->nblk;
        bmin = m < bmin ? m : bmin;
        bmax = m > bmax ? m : bmax;
    }
    const double lim = (double)p->dp_frac * (double)p->p_max_w;
    if (dv < -(double)p->dv_trig_k_per_s && bmin - pb >= -lim) {
        return 1;
    }
    if (p->up_enable && dv > (double)p->dv_trig_k_per_s && bmax - pb <= lim && c->g < 0.95 * c->g_nom) {
        return -1;
    }
    return 0;
}

/* ---- the window EKF ----------------------------------------------------------- */
static void win_advance(csw_t *c, float y, float ts)
{
    const pte_params_t *k = &c->k;
    const double eps = 1e-4;
    const double g = exp(c->z[4]);
    double F[PTE_NX][PTE_NX];
    double fx[PTE_NX], f2[PTE_NX];
    const double x[PTE_NX] = {c->z[0], c->z[1], c->z[2], c->z[3]};
    map_matrix(k, g, F);
    map_apply(k, g, x, (double)ts, fx);
    map_apply(k, g * exp(eps), x, (double)ts, f2);

    double J[5][5] = {{0.0}};
    for (int i = 0; i < PTE_NX; i++) {
        for (int j = 0; j < PTE_NX; j++) {
            J[i][j] = F[i][j];
        }
        J[i][4] = (f2[i] - fx[i]) / eps;
    }
    J[4][4] = 1.0;
    const double dt = (double)c->p.dt_s;
    const double q[5] = {(double)c->p.q_t * dt, (double)c->p.q_v * dt, (double)k->q_per_s[2] * dt,
                         (double)k->q_per_s[3] * dt, (double)c->p.q_lng * dt};
    double zp[5] = {fx[0], fx[1], fx[2], fx[3], c->z[4]};
    double JP[5][5], Pp[5][5];
    for (int i = 0; i < 5; i++) {
        for (int j = 0; j < 5; j++) {
            double a = 0.0;
            for (int m = 0; m < 5; m++) {
                a += J[i][m] * c->Pz[m][j];
            }
            JP[i][j] = a;
        }
    }
    for (int i = 0; i < 5; i++) {
        for (int j = 0; j < 5; j++) {
            double a = 0.0;
            for (int m = 0; m < 5; m++) {
                a += JP[i][m] * J[j][m];
            }
            Pp[i][j] = a;
        }
        Pp[i][i] += q[i];
    }
    const double r = (double)k->sigma_k * (double)k->sigma_k;
    const double S = Pp[3][3] + r;
    double K[5], row[5];
    for (int i = 0; i < 5; i++) {
        K[i] = Pp[i][3] / S;
        row[i] = Pp[3][i];
    }
    const double innov = (double)y - zp[3];
    for (int i = 0; i < 5; i++) {
        c->z[i] = zp[i] + K[i] * innov;
    }
    for (int i = 0; i < 5; i++) {
        for (int j = 0; j < 5; j++) {
            c->Pz[i][j] = Pp[i][j] - K[i] * row[j];
        }
    }
    for (int i = 0; i < 5; i++) {
        for (int j = i + 1; j < 5; j++) {
            const double a = 0.5 * (c->Pz[i][j] + c->Pz[j][i]);
            c->Pz[i][j] = a;
            c->Pz[j][i] = a;
        }
    }
    if (c->z[4] < c->lo) {
        c->z[4] = c->lo;
    }
    if (c->z[4] > c->hi) {
        c->z[4] = c->hi;
    }
    c->lng_log[c->n] = c->z[4];
    c->n++;
}

static void win_open(csw_t *c, int dir, bool steady)
{
    const csw_params_t *p = &c->p;
    const uint16_t n = c->snap_count;              /* samples since the snapshot, incl. this one */
    const uint16_t ref0 = (uint16_t)(c->count - n - c->nref);
    c->win = true;
    c->dir = (int8_t)dir;
    c->steady = steady;
    c->z[0] = (double)c->snap_x[0][0];
    c->z[1] = slope(c->y, ref0, c->nref, (double)p->dt_s);
    c->z[2] = (double)c->snap_x[0][2];
    c->z[3] = (double)c->snap_x[0][3];
    c->z[4] = log(c->g);
    memset(c->Pz, 0, sizeof(c->Pz));
    for (int i = 2; i < 4; i++) {
        for (int j = 2; j < 4; j++) {
            c->Pz[i][j] = (double)c->snap_P[0][i][j];
        }
    }
    c->Pz[0][0] = (double)p->p0_t_k * (double)p->p0_t_k;
    c->Pz[1][1] = (double)p->p0_v_k_per_s * (double)p->p0_v_k_per_s;
    c->Pz[4][4] = (double)p->p0_lng * (double)p->p0_lng;
    double pr = 0.0;
    for (uint16_t i = 0; i < c->nref; i++) {
        pr += (double)c->pw[ref0 + i];
    }
    c->p_ref = (float)(pr / (double)c->nref);
    const double lg = log(c->g);
    if (dir > 0) {
        c->lo = log((double)p->h_floor_w_per_m2k * (double)c->k.contact_area_m2);
        c->hi = lg;
    } else {
        c->lo = lg;
        c->hi = log(c->g_nom);
    }
    c->g_before = c->g;
    c->n = 0u;
    c->n_replay = n;
    for (uint16_t i = 0; i < n; i++) {
        const uint16_t h = (uint16_t)(c->count - n + i);
        win_advance(c, c->y[h], c->ts[h]);
    }
    c->windows++;
}

static csw_event_t win_close(csw_t *c, pte_t *est, csw_event_t kind)
{
    if (kind == CSW_EVT_ACCEPT) {
        double lng = c->z[4] - (double)c->p.accept_bias_sd * sqrt(c->Pz[4][4] > 0.0 ? c->Pz[4][4] : 0.0);
        const double floor_lng = (c->dir > 0) ? c->lo : log(c->g_before);
        if (lng < floor_lng) {
            lng = floor_lng;
        }
        c->g = exp(lng);
        (void)pte_set_contact(est, (float)(c->g / (double)c->k.contact_area_m2));
        for (int i = 0; i < PTE_NX; i++) {
            est->x[i] = (float)c->z[i];
            for (int j = 0; j < PTE_NX; j++) {
                est->P[i][j] = (float)c->Pz[i][j];
            }
        }
        c->accepts++;
    } else if (kind == CSW_EVT_ESCALATE) {
        c->escalations++;
    }
    /* REVERT / ESCALATE: the estimator ran on with the old contact; keep it. */
    c->win = false;
    c->holdoff_until = c->t + steps(c->p.holdoff_s, c->p.dt_s);
    return kind;
}

static csw_event_t win_step(csw_t *c, pte_t *est, float y, float ts, bool allow)
{
    const csw_params_t *p = &c->p;
    win_advance(c, y, ts);
    if (!allow) {
        return win_close(c, est, CSW_EVT_REVERT);
    }
    const double lng = c->z[4];
    if (c->dir > 0 && lng <= c->lo + 1e-6) {
        return win_close(c, est, CSW_EVT_ESCALATE);
    }
    const double dur = (double)(c->n - c->n_replay) * (double)p->dt_s;
    const uint16_t ns = steps(p->settle_s, p->dt_s);
    const bool moved = (c->dir > 0) ? (lng < c->hi - 1e-6) : (lng > c->lo + 1e-6);
    const bool settled = moved && c->n > ns && fabs(lng - c->lng_log[c->n - 1u - ns]) < (double)p->settle_dlng;
    const bool at_nominal = c->dir < 0 && lng >= c->hi - 1e-6;
    const bool big = fabs(lng - log(c->g_before)) >= -log(1.0 - (double)p->min_drop) || at_nominal;
    const bool good = settled && big && (sqrt(c->Pz[4][4]) <= (double)p->max_sd_lng || at_nominal);
    const double win_min = c->steady ? (double)p->win_min_hold_s : (double)p->win_min_s;
    if (dur >= win_min && good) {
        return win_close(c, est, CSW_EVT_ACCEPT);
    }
    if (dur >= (double)p->win_max_s || c->n >= CSW_WIN - 1u) {
        return win_close(c, est, CSW_EVT_REVERT);
    }
    return CSW_EVT_NONE;
}

void csw_step(csw_t *c, pte_t *est, float y_c, float t_sink_c, float p_applied_w, bool allow, bool steady,
              csw_output_t *out)
{
    const csw_params_t *p = &c->p;
    c->t++;
    /* snapshot of the estimator before this step */
    if (c->snap_count < c->nlag + 1u) {
        memcpy(c->snap_x[c->snap_count], est->x, sizeof(est->x));
        memcpy(c->snap_P[c->snap_count], est->P, sizeof(est->P));
        c->snap_count++;
    } else {
        memmove(c->snap_x[0], c->snap_x[1], (size_t)c->nlag * sizeof(c->snap_x[0]));
        memmove(c->snap_P[0], c->snap_P[1], (size_t)c->nlag * sizeof(c->snap_P[0]));
        memcpy(c->snap_x[c->nlag], est->x, sizeof(est->x));
        memcpy(c->snap_P[c->nlag], est->P, sizeof(est->P));
    }
    push(c->y, c->count, c->nkeep, y_c);
    push(c->ts, c->count, c->nkeep, t_sink_c);
    push(c->pw, c->count, c->nkeep, p_applied_w);
    if (c->count < c->nkeep) {
        c->count++;
    }

    float t_hat = pte_step(est, y_c, t_sink_c);
    csw_event_t ev = CSW_EVT_NONE;
    if (c->win) {
        ev = win_step(c, est, y_c, t_sink_c, allow);
        t_hat = c->win ? (float)c->z[0] : est->x[0];
    }
    if (!c->win && ev == CSW_EVT_NONE && p->enable && allow && c->t > c->holdoff_until &&
        c->t >= (uint32_t)steps(p->start_holdoff_s, p->dt_s)) {
        const int d = triggered(c);
        if (d != 0) {
            win_open(c, d, steady);
            ev = (d > 0) ? CSW_EVT_OPEN_DOWN : CSW_EVT_OPEN_UP;
            t_hat = (float)c->z[0];
        }
    }
    out->t_hat_c = t_hat;
    out->event = ev;
    out->window_open = c->win;
    out->h_model_w_per_m2k = csw_h_model(c);
}

void csw_reset_window(csw_t *c)
{
    if (c->win) {
        c->win = false;
        c->holdoff_until = c->t + steps(c->p.holdoff_s, c->p.dt_s);
    }
}

void csw_reset_contact(csw_t *c, pte_t *est)
{
    if (c->win) {
        (void)win_close(c, est, CSW_EVT_REVERT);
    }
    c->g = c->g_nom;
    (void)pte_set_contact(est, (float)(c->g_nom / (double)c->k.contact_area_m2));
}
