#include "rails.h"

int32_t rails_p12_mv(uint32_t sum, uint32_t samples) {
    /* mean code / 4096 * 3300 mV is the pin; the divider 100k / 10k multiplies by 11. */
    return (int32_t)((int64_t)sum * RAIL_ADC_REF_MV * 11 / ((int64_t)samples * RAIL_ADC_CODES));
}

int32_t rails_n12_mv(uint32_t sum, uint32_t samples) {
    /* pin = (3V3 * 150k + V * 10k) / 160k, so V = (pin * 160 - 3V3 * 150) / 10. */
    int64_t scale = (int64_t)samples * RAIL_ADC_CODES;
    int64_t numerator = (int64_t)sum * RAIL_ADC_REF_MV * 160 - scale * RAIL_ADC_REF_MV * 150;
    return (int32_t)(numerator / (scale * 10));
}

bool rails_in_window(int32_t p12_mv, int32_t n12_mv) {
    return p12_mv >= RAIL_P12_MIN_MV && p12_mv <= RAIL_P12_MAX_MV && n12_mv >= RAIL_N12_MIN_MV &&
           n12_mv <= RAIL_N12_MAX_MV;
}

rails_decision rails_poll(bool in_window, uint32_t elapsed_ms, unsigned *streak) {
    *streak = in_window ? *streak + 1u : 0u;
    if (*streak >= RAIL_STABLE_POLLS) return RAILS_UP;
    return elapsed_ms >= RAIL_TIMEOUT_MS ? RAILS_TIMEOUT : RAILS_WAIT;
}
