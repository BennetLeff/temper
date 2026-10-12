/* Half-cycle RMS estimator (n21_half_close -> input_limits_half_cycle).
 *
 * The acquisition slot is 625 us, so a half line cycle (7833-8834 us between LINE_ZC zeros) holds
 * 13 or 14 readings. The AD8436 reading is the 120 Hz envelope, A*sqrt2*|sin(pi t / L)|, whose true
 * half-cycle RMS is A. The test sweeps the slot phase and the half length and reports the scatter
 * of the estimate. Pre-fix (equal weights) the scatter is about -3 % .. +2.7 %; with time weighting
 * it must stay inside +/-0.5 %. Evidence: build-evidence/rms-estimator/README.md. */
#include "n21_signal.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>

#define TOL_PCT 0.5
static unsigned tests;

/* One half of length L us with the slot grid offset `off` us after the opening zero. Returns the
 * percent error of the closed half's tank RMS against the true A, or NAN if it did not close. */
static double scatter_one(double L, double off, double A, uint64_t t0)
{
    input_limits_cfg_t lim = input_limits_native21();
    n21_half_t h;
    n21_half_result_t r;
    n21_half_begin(&h, t0);
    for (double t = off; t < L - 1.0 && h.n < N21_HALF_MAX_SAMPLES; t += 625.0) {
        double x = fabs(sin(3.14159265358979 * t / L));
        input_sample_t s = {.bus_v = (float)(170.0 * x), .tank_rms_a = (float)(A * 1.41421356237 * x),
                            .cos_phi = 1.0f};  /* designated: builds against pre-fix headers too */
        n21_half_add(&h, t0 + (uint64_t)llround(t), &s);
    }
    if (!n21_half_close(&h, &lim, t0 + (uint64_t)llround(L), 1500, 0, &r)) return NAN;
    return (r.est.tank_rms_a / A - 1.0) * 100.0;
}

static void test_slot_phase_scatter(void)
{
    static const double lens[] = {7900.0, 8333.3, 8800.0};
    double lo = 1e9, hi = -1e9;
    for (unsigned k = 0; k < sizeof lens / sizeof lens[0]; k++)
        for (double off = 0.0; off < 625.0; off += 25.0)
            for (double A = 4.0; A <= 28.0; A += 12.0) {  /* 4, 16, 28 A: scale must not matter */
                double e = scatter_one(lens[k], off, A, 1000000u + (uint64_t)(off * 3));
                assert(isfinite(e));
                if (e < lo) lo = e;
                if (e > hi) hi = e;
            }
    printf("half-cycle RMS scatter vs slot phase and half length: %+.2f %% .. %+.2f %%\n", lo, hi);
    assert(lo >= -TOL_PCT && hi <= TOL_PCT);
    tests++;
}

/* The scatter must not depend on where the readings sit: shifting every reading by a fraction of
 * a slot moves the estimate by far less than the old 4 % span. */
static void test_slot_phase_invariance(void)
{
    double lo = 1e9, hi = -1e9;
    for (double off = 0.0; off < 625.0; off += 5.0) {
        double e = scatter_one(8333.3, off, 22.0, 2000000u);
        assert(isfinite(e));
        if (e < lo) lo = e;
        if (e > hi) hi = e;
    }
    printf("slot phase only (5 us steps, 8333.3 us half): span %.3f %%\n", hi - lo);
    assert(hi - lo <= 2 * TOL_PCT);
    tests++;
}

int main(void)
{
    test_slot_phase_scatter();
    test_slot_phase_invariance();
    printf("rms estimator: %u tests passed\n", tests);
    return 0;
}
