#ifndef TEMPER_LINE_ZC_H
#define TEMPER_LINE_ZC_H
#include <stdbool.h>
#include <stdint.h>
/* LINE_ZC (native-21 J4.16) pulse -> line zero-crossing prediction.
 * The detector output is HIGH near the line zero (opto LED off), so each zero
 * gives a rising then a falling edge; the pulse centre minus a bench-calibrated
 * offset estimates the zero. The centre is only known at the falling edge
 * (~1 ms late), so after LINE_ZC_LOCK_PULSES consecutive qualified pulses the
 * estimator predicts the next zero from the measured half-period; that
 * predicted instant is what the burst scheduler receives (from_line_zc=true).
 * Any implausible width/period or a missing pulse drops lock. */
#define LINE_ZC_LOCK_PULSES 4
typedef struct {
    uint32_t min_width_us, max_width_us;    /* qualified pulse width */
    uint32_t min_half_us, max_half_us;      /* qualified centre spacing */
    int32_t cal_offset_us;                  /* bench: centre - true zero */
} line_zc_config_t;
typedef struct {
    line_zc_config_t cfg;
    uint64_t rise_us, last_centre_us, next_us;
    uint32_t half_us;
    uint8_t good;
    bool high, have_rise, have_centre, locked;
} line_zc_t;
void line_zc_init(line_zc_t *, const line_zc_config_t *);
/* Edge from a GPIO capture: timestamp and new level. */
void line_zc_edge(line_zc_t *, uint64_t t_us, bool level);
/* Returns true once per predicted zero when now_us has reached it; *zero_us is
 * the predicted crossing time. Drops lock if no pulse arrived for 1.5 half-cycles. */
bool line_zc_poll(line_zc_t *, uint64_t now_us, uint64_t *zero_us);
#endif
