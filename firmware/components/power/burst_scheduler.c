#include "burst_scheduler.h"
#include <math.h>
#include <string.h>
double burst_min_period_s(double w, double v, double pf)
{
    if (!isfinite(w) || w <= 0 || !isfinite(v) || v <= 0 ||
        !isfinite(pf) || pf <= 0 || pf > 1) return NAN;
    double d = 100 * (w / (v * pf)) * (0.4 * pf + 0.25 * sqrt(1 - pf * pf)) / v;
    return fmax(2, 4.6 * pow(d / 0.65, 3.2));
}
bool burst_scheduler_init(burst_scheduler_t *s, const burst_config_t *c)
{
    if (!s) return false;
    memset(s, 0, sizeof *s);
    if (!c) return false;
    s->config = *c;
    if (!c->burst_enabled) { s->configured = true; return true; }
    double minimum = burst_min_period_s(c->measured_burst_w, c->line_rms_v, c->power_factor);
    double period = c->period_s == 0 ? BURST_DEFAULT_PERIOD_S : c->period_s;
    if (!isfinite(minimum) || !isfinite(period) || period <= 0) return false;
    double cycles = ceil(fmax(period, minimum) * 120);
    if (cycles > UINT32_MAX) return false;
    s->half_cycles = (uint32_t)cycles;
    s->configured = true;
    return true;
}
static bool fail(burst_scheduler_t *s)
{
    s->fault = true;
    s->on = false;
    return false;
}
bool burst_scheduler_step(burst_scheduler_t *s, uint64_t now,
                          const hal_bus_crossing_t *bus, double requested)
{
    if (!s || !s->configured || s->fault) return false;
    if (!isfinite(requested) || requested < 0) return fail(s);
    if (!s->config.burst_enabled) { s->on = requested > 0; return true; }
    if (!bus || !bus->valid || !bus->from_line_zc ||
        now < bus->sampled_us || now - bus->sampled_us > 150 ||
        (s->seen_sample && bus->sampled_us < s->last_sample_us)) return fail(s);
    if (s->seen_crossing && (now < s->last_crossing_us || now - s->last_crossing_us > 9000)) return fail(s);
    bool new_sample = !s->seen_sample || bus->sampled_us != s->last_sample_us;
    s->seen_sample = true;
    s->last_sample_us = bus->sampled_us;
    if (!bus->zero_crossing || !new_sample) return true;
    if (s->seen_crossing) {
        uint64_t elapsed = bus->sampled_us - s->last_crossing_us;
        /* Two timestamps each have the D-11 +/-250 us allocation. */
        if (elapsed < 7833 || elapsed > 8834) return fail(s);
        s->index = (s->index + 1) % s->half_cycles;
    }
    s->last_crossing_us = bus->sampled_us;
    s->seen_crossing = true;
    if (s->index == 0) {
        double fraction = fmin(1, requested / s->config.measured_burst_w);
        s->on_half_cycles = (uint32_t)floor(fraction * s->half_cycles);
    }
    /* A normal zero-power request stops at the next crossing. Re-enabling
     * waits for the next period boundary, preserving one contiguous burst. */
    if (requested == 0) s->on_half_cycles = 0;
    s->on = s->index < s->on_half_cycles;
    return true;
}
