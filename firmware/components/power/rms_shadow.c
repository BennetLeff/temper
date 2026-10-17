#include "rms_shadow.h"
#include "n21_signal.h"
#include <math.h>

#define HALF_S (0.5 / 60.0)

float rms_shadow_lock_metric(float f_hz, uint32_t fs_hz)
{
    if (!isfinite(f_hz) || f_hz <= 0 || fs_hz == 0) return 1.0f;
    static const struct { double k, w; } term[3] = {{2, 1.0}, {4, 0.3}, {6, 0.1}};
    const double fs = (double)fs_hz, tp = RMS_SHADOW_PATTERN_LEN / fs;
    const unsigned slots[2] = {RMS_SHADOW_CT_SLOT_A, RMS_SHADOW_CT_SLOT_B};
    double re[3] = {0}, im[3] = {0};
    double wsum = 0;
    unsigned n = 0;
    /* The stream is continuous: patterns that began before the window still put samples in it. */
    for (int p = 0; p < (int)(HALF_S / tp) + 3; p++)
        for (unsigned q = 0; q < 2; q++) {
            double t = -tp + tp * p + slots[q] / fs;
            if (t < 0 || t >= HALF_S) continue;
            /* The energy under the line envelope: a reading at t counts sin^2(pi t / half). */
            double w = sin(3.141592653589793 * t / HALF_S);
            w *= w;
            for (unsigned i = 0; i < 3; i++) {
                double a = 6.283185307179586 * term[i].k * f_hz * t;
                re[i] += w * cos(a);
                im[i] += w * sin(a);
            }
            wsum += w;
            n++;
        }
    if (n == 0 || !(wsum > 0)) return 1.0f;
    double m = 0;
    for (unsigned i = 0; i < 3; i++) m += term[i].w * hypot(re[i], im[i]) / wsum;
    return (float)m;
}

uint32_t rms_shadow_select_fs(float f_hz, float *metric_out)
{
    uint32_t best = RMS_SHADOW_FS_NOMINAL_HZ;
    float bm = INFINITY;
    for (uint32_t m = 0; m < RMS_SHADOW_FS_COUNT; m++) {
        uint32_t fs = RMS_SHADOW_FS_NOMINAL_HZ - RMS_SHADOW_FS_STEP_HZ * m;
        float v = rms_shadow_lock_metric(f_hz, fs);
        if (v < bm) { bm = v; best = fs; }
    }
    if (metric_out) *metric_out = bm;
    return best;
}

uint32_t rms_shadow_hold_fs(float f_hz, uint32_t cur_fs_hz)
{
    uint32_t lo = RMS_SHADOW_FS_NOMINAL_HZ - RMS_SHADOW_FS_STEP_HZ * (RMS_SHADOW_FS_COUNT - 1);
    if (cur_fs_hz >= lo && cur_fs_hz <= RMS_SHADOW_FS_NOMINAL_HZ &&
        rms_shadow_lock_metric(f_hz, cur_fs_hz) <= RMS_SHADOW_LOCK_HOLD)
        return cur_fs_hz;
    return rms_shadow_select_fs(f_hz, NULL);
}

void rms_shadow_reset(rms_shadow_t *s)
{
    s->sumsq = 0;
    s->n = 0;
}

void rms_shadow_add_mv(rms_shadow_t *s, float mv, float zero_mv)
{
    if (!isfinite(mv)) return;
    float zero = zero_mv == 0.0f ? N21_CT_MON_BIAS_V * 1e3f : zero_mv;
    double a = ((double)mv - zero) * 1e-3 / N21_CT_MON_V_PER_A;
    s->sumsq += a * a;
    s->n++;
}

void rms_shadow_add_sum(rms_shadow_t *s, double sumsq_a2, uint32_t n)
{
    if (!(sumsq_a2 >= 0) || !isfinite(sumsq_a2)) return;
    s->sumsq += sumsq_a2;
    s->n += n;
}

bool rms_shadow_close(rms_shadow_t *s, float *rms_a)
{
    bool ok = s->n >= RMS_SHADOW_MIN_SAMPLES;
    *rms_a = ok ? (float)sqrt(s->sumsq / s->n) : NAN;
    rms_shadow_reset(s);
    return ok;
}
