#pragma once
/* Rev G jack guard: the four TLP172AM isolation switches between the BNC protection and the board
   (validation/rev-g-protection/README.md, "Drive and sense"). No Pico SDK dependency: test/test_host.c
   runs the decision against simulated readings. Built only for Rev G (LCR_REV_G); Rev E / F have no
   switches and no jack sense.

   The switches are normally open: the LEDs are driven from the switched 5 V through one AO3400A on
   PIN_ISO_DRIVE (100 kOhm gate pull-down), so they are open from power-up until this guard closes them,
   and open again within tOFF (0.5 ms max) of losing VBUS. The guard closes them only when the analog
   rails are up and both CUR jacks read uncharged (R105 / R106 on the jack side tie each POT jack to its
   CUR jack, so two senses cover all four), and opens them on a rail fault or when a jack is driven
   beyond what the source makes (a charged DUT touched while closed). */
#include <stdbool.h>
#include <stdint.h>

/* Sense divider per CUR jack (drive_budget.py; design.json R126-R131, C121 / C122): R_TOP 1.5 MOhm from the
   jack, R_BIAS 240 kOhm to 3V3, R_GND 240 kOhm to ground, 100 nF on the node (at the jack end of its run, not at the
   MCU pin: docs/rev-g-plan.md). pin = (V_jack / R_TOP + 3V3 / R_BIAS) / G,
   so V_jack = pin * R_TOP * G - 3V3 * R_TOP / R_BIAS with R_TOP * G = 1 + 6.25 + 6.25 = 13.5 and R_TOP / R_BIAS = 6.25. */
#define JG_ADC_REF_MV 3300
#define JG_ADC_CODES 4096
#define JG_RTOP_G_PPM 13500000       /* R_TOP * G, x 1e6 */
#define JG_RTOP_RBIAS_PPM 6250000    /* R_TOP / R_BIAS, x 1e6 */

/* Close only when no charged part can be on the jacks. With the switches open nothing ties a CUR jack to
   GND: the divider (1.65 V behind 1.62 MOhm) floats an open jack, and a floating DUT across the jacks, at
   +1.65 V (datasheet audit PROT-01, validation/datasheet-audit-rev-g100/). So a charged DUT shows as a
   difference between the two jacks, and the close test is that difference below CLOSE_DIFF with each jack
   inside CLOSE_LO..CLOSE_HI: a jack closes at 2.65 V at most, under the second-stage H3V3LD5B's 3.3 V
   standoff, so closing never makes it conduct.
   Trip while closed: HCUR beyond TRIP (the source is at most 1.7 V peak, and the sense filter passes 0.50 V
   of the lowest 46 Hz tone); LCUR, the TIA virtual ground, beyond TRIP_LC (a DC source of 1-3 V there
   overloads R43 and U7A without reaching TRIP: audit G-AFE-01). Both apply to |V|. */
#define JG_CLOSE_DIFF_MV 1000
#define JG_CLOSE_LO_MV (-1000)
#define JG_CLOSE_HI_MV 2650
#define JG_TRIP_MV 3000
#define JG_TRIP_LC_MV 500
#define JG_POLL_MS 5u
#define JG_STABLE_POLLS 7u        /* 35 ms inside the close test: the 11.1 ms sense filter settles from a clamped jack in 33 ms */
#define JG_SETTLE_MS 40u          /* TLP172AM tON 2 ms max, and the sense filter falling from the 2.65 V close limit to below
                                     TRIP_LC (19 ms at 11.1 ms), before a capture or the LCUR trip may use the jacks */
#define JG_REARM_MS 1000u         /* after a trip, continuous time inside the close test before closing again */

/* Jack volts (mV) from the sum of `samples` 12-bit conversions of its sense pin. */
int32_t jackguard_mv(uint32_t sum, uint32_t samples);

typedef enum {
    JG_OPEN = 0,  /* switches open, waiting for the rails and quiet jacks */
    JG_CLOSING,   /* driven on, inside JG_SETTLE_MS */
    JG_CLOSED,    /* closed and settled: captures may run */
    JG_TRIPPED,   /* opened by a jack beyond its trip (or a rail fault while closed); re-arms itself */
} jackguard_state;

typedef struct {
    jackguard_state state;
    unsigned streak;      /* consecutive polls inside the close test (jackguard_quiet) */
    uint32_t since_ms;    /* when the state was entered */
    uint32_t quiet_ms;    /* since when the jacks have been inside the close test (TRIPPED) */
    int32_t last_hc_mv, last_lc_mv;
} jackguard;

void jackguard_init(jackguard *g, uint32_t now_ms);
/* One poll: rails_ok from the rail monitors, both jack readings, the time. Returns whether the switches
   are to be driven on after this poll. */
bool jackguard_poll(jackguard *g, bool rails_ok, int32_t hc_mv, int32_t lc_mv, uint32_t now_ms);
/* A capture may use the jacks. */
static inline bool jackguard_ready(const jackguard *g) { return g->state == JG_CLOSED; }
/* Inside a capture the guard is not polled; the capture loop takes one conversion per jack every JG_POLL_MS
   and opens the switches when this is true (a source or charged part connected mid-capture). */
static inline bool jackguard_over(int32_t hc_mv, int32_t lc_mv) {
    return hc_mv > JG_TRIP_MV || hc_mv < -JG_TRIP_MV || lc_mv > JG_TRIP_LC_MV || lc_mv < -JG_TRIP_LC_MV;
}
/* The close test: no charged part on the jacks (CLOSE_DIFF) and neither jack beyond CLOSE_LO..CLOSE_HI. */
static inline bool jackguard_quiet(int32_t hc_mv, int32_t lc_mv) {
    int32_t d = hc_mv - lc_mv;
    return d < JG_CLOSE_DIFF_MV && d > -JG_CLOSE_DIFF_MV && hc_mv > JG_CLOSE_LO_MV && hc_mv < JG_CLOSE_HI_MV &&
           lc_mv > JG_CLOSE_LO_MV && lc_mv < JG_CLOSE_HI_MV;
}
/* A trip seen outside a poll (the capture loop): TRIPPED from now, re-armed as a polled trip is. */
void jackguard_trip(jackguard *g, uint32_t now_ms);
const char *jackguard_state_name(jackguard_state s);
