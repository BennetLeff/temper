#pragma once
/* Start gating on the +-12 V analog rails (Rev F datasheet audit L5, L6, S16). No Pico SDK
   dependency: test/test_host.c runs the decision against simulated readings.

   Rev F enables the TPS65131 converters from the LM3880 sequencer U17, not from the firmware: the
   boost enables 20-60 ms after USB attach, the inverter 8.5-11.5 ms later, and the +-12 V LDOs
   then soft-start over 9-14 ms (TPS7A49 / TPS7A30, 10 nF on NR/SS). The 3V3 rail, and so this
   firmware, is up before any of that. Until both monitors read inside their windows the DAC stays
   powered down (the codec is not started) and the range relays are not pulsed. */
#include <stdbool.h>
#include <stdint.h>

/* Healthy windows of the rails in millivolts: the host's gross-fault windows
   (host/src/lib.rs RAIL_P12_WINDOW_V and RAIL_N12_WINDOW_V), which are the "host_window_pos_abs_v"
   and "host_window_neg_abs_v" of validation/power-spurs/rail_monitor_window.json: the worst
   healthy reading of each rail (tolerance, TCR, 1 % monitor dividers, 3V3 reference, pin
   leakage, ADC error) widened by 0.2 V. host/tests/rev_e.rs keeps them equal to these. */
#define RAIL_P12_MIN_MV 10200
#define RAIL_P12_MAX_MV 13400
#define RAIL_N12_MIN_MV -14100
#define RAIL_N12_MAX_MV -10500

/* Monitor conversion, as host/src/lib.rs rails_from_line(): ADC0 reads +12 V through R97 100 kOhm
   over R98 10 kOhm; ADC1 reads -12 V through R100 150 kOhm with R99 10 kOhm to 3V3. Both are
   ratiometric to the 3.3 V ADC reference (ADC_AVDD is the 3V3 rail). */
#define RAIL_ADC_REF_MV 3300
#define RAIL_ADC_CODES 4096

#define RAIL_POLL_MS 5u
/* Consecutive in-window polls (20 ms) before the rails count as up: a soft-start passes through
   the window, and the second rail must not still be ramping. */
#define RAIL_STABLE_POLLS 4u
/* The sequence is done about 90-100 ms after attach (60 + 11.5 + 14 ms plus the converter ramp);
   500 ms leaves a factor of five before a missing rail is reported. */
#define RAIL_TIMEOUT_MS 500u

/* +12 V and -12 V in millivolts from the sum of `samples` 12-bit conversions of ADC0 / ADC1. */
int32_t rails_p12_mv(uint32_t sum, uint32_t samples);
int32_t rails_n12_mv(uint32_t sum, uint32_t samples);
bool rails_in_window(int32_t p12_mv, int32_t n12_mv);

typedef enum {
    RAILS_WAIT = 0, /* keep polling */
    RAILS_UP,       /* both rails stably inside their windows */
    RAILS_TIMEOUT,  /* the timeout passed without that: a rail fault */
} rails_decision;
/* One polling step: `streak` counts consecutive in-window polls (start at 0), `elapsed_ms` is the
   time since polling began. UP wins over TIMEOUT when both hold on the same poll. */
rails_decision rails_poll(bool in_window, uint32_t elapsed_ms, unsigned *streak);
