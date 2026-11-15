#include "jackguard.h"

int32_t jackguard_mv(uint32_t sum, uint32_t samples) {
    /* pin (mV) = mean code / 4096 * 3300; V_jack = pin * 13.5 - 3300 * 6.25. */
    int64_t scale = (int64_t)samples * JG_ADC_CODES;
    int64_t numerator = (int64_t)sum * JG_ADC_REF_MV * JG_RTOP_G_PPM - scale * JG_ADC_REF_MV * JG_RTOP_RBIAS_PPM;
    return (int32_t)(numerator / (scale * 1000000));
}

static int32_t magnitude(int32_t v) { return v < 0 ? -v : v; }

static void enter(jackguard *g, jackguard_state s, uint32_t now_ms) {
    g->state = s;
    g->since_ms = now_ms;
    g->streak = 0;
    g->quiet_ms = now_ms;
}

void jackguard_init(jackguard *g, uint32_t now_ms) {
    enter(g, JG_OPEN, now_ms);
    g->last_hc_mv = g->last_lc_mv = 0;
    g->lc_zero_mv = 0;
    g->zero_sum = 0;
    g->zero_n = 0;
}

static int32_t zero_of(const jackguard *g) {
    if (g->zero_n == 0u) return 0;
    int64_t mean = g->zero_sum / (int64_t)g->zero_n;
    return mean > JG_ZERO_MAX_MV ? JG_ZERO_MAX_MV : mean < -JG_ZERO_MAX_MV ? -JG_ZERO_MAX_MV : (int32_t)mean;
}

bool jackguard_poll(jackguard *g, bool rails_ok, int32_t hc_mv, int32_t lc_mv, uint32_t now_ms) {
    g->last_hc_mv = hc_mv;
    g->last_lc_mv = lc_mv;
    bool quiet = jackguard_quiet(hc_mv, lc_mv);
    switch (g->state) {
    case JG_CLOSING:
    case JG_CLOSED:
        /* LCUR's own trip waits for CLOSED: its sense still falls from the open-jack float while CLOSING */
        if (!rails_ok || magnitude(hc_mv) > JG_TRIP_MV || magnitude(lc_mv) > JG_TRIP_MV ||
            (g->state == JG_CLOSED && magnitude(lc_mv - g->lc_zero_mv) > JG_TRIP_LC_MV)) {
            enter(g, JG_TRIPPED, now_ms);
            return false;
        }
        if (g->state == JG_CLOSING) {
            uint32_t closed_for = now_ms - g->since_ms;
            if (closed_for >= JG_ZERO_FROM_MS) {
                g->zero_sum += lc_mv;
                ++g->zero_n;
            }
            if (closed_for >= JG_SETTLE_MS) {
                g->lc_zero_mv = zero_of(g);
                g->state = JG_CLOSED;
            }
        }
        return true;
    case JG_TRIPPED:
        if (!quiet || !rails_ok) g->quiet_ms = now_ms;
        if (now_ms - g->quiet_ms < JG_REARM_MS) return false;
        enter(g, JG_OPEN, now_ms);
        /* re-armed: this reading counts as the first OPEN poll */
        /* fall through */
    case JG_OPEN:
    default:
        g->streak = (quiet && rails_ok) ? g->streak + 1u : 0u;
        if (g->streak >= JG_STABLE_POLLS) {
            enter(g, JG_CLOSING, now_ms);
            g->zero_sum = 0;      /* each close measures its own zero */
            g->zero_n = 0;
            return true;
        }
        return false;
    }
}

void jackguard_trip(jackguard *g, uint32_t now_ms) { enter(g, JG_TRIPPED, now_ms); }

const char *jackguard_state_name(jackguard_state s) {
    switch (s) {
    case JG_OPEN: return "open";
    case JG_CLOSING: return "closing";
    case JG_CLOSED: return "closed";
    case JG_TRIPPED: return "tripped";
    }
    return "unknown";
}
