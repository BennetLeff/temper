#include "jackguard.h"

int32_t jackguard_mv(uint32_t sum, uint32_t samples) {
    /* pin (mV) = mean code / 4096 * 3300; V_jack = pin * 10.016064 - 3300 * 5. */
    int64_t scale = (int64_t)samples * JG_ADC_CODES;
    int64_t numerator = (int64_t)sum * JG_ADC_REF_MV * JG_RTOP_G_PPM - scale * JG_ADC_REF_MV * JG_RTOP_RBIAS * 1000000;
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
}

bool jackguard_poll(jackguard *g, bool rails_ok, int32_t hc_mv, int32_t lc_mv, uint32_t now_ms) {
    g->last_hc_mv = hc_mv;
    g->last_lc_mv = lc_mv;
    int32_t worst = magnitude(hc_mv) > magnitude(lc_mv) ? magnitude(hc_mv) : magnitude(lc_mv);
    bool quiet = worst < JG_CLOSE_MV;
    switch (g->state) {
    case JG_CLOSING:
    case JG_CLOSED:
        if (!rails_ok || worst > JG_TRIP_MV) {
            enter(g, JG_TRIPPED, now_ms);
            return false;
        }
        if (g->state == JG_CLOSING && now_ms - g->since_ms >= JG_SETTLE_MS) g->state = JG_CLOSED;
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
