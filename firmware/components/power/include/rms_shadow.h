#ifndef TEMPER_RMS_SHADOW_H
#define TEMPER_RMS_SHADOW_H
/*
 * Bench-only shadow tank-RMS from the raw CT_MON samples of the ADC1 continuous stream
 * (option C2 of zapote/controller/evidence/rms-alternatives/, DECISIONS C35). Pure functions, no HAL.
 *
 * It exists to compare a no-converter RMS against the AD8436 reading over temperature and 31-55 kHz
 * before the converter chain is deleted. It NEVER feeds a limit, a trip, the frequency loop or the
 * power estimate: the binding only copies it into telemetry (n21_telemetry_t.shadow_*), and the
 * whole feature is behind Kconfig TEMPER_POWER_SHADOW_RMS (default off, bench builds only).
 *
 * Why the sample clock is chosen. The ADC1 pattern is 9 slots with CT_MON in slots 1 and 3, so CT_MON
 * samples come in pairs 2/fs apart every 9/fs. At fs = 80 kS/s the pair spacing is 25 us (one carrier
 * period at exactly 40 kHz) and the pattern repeat is 112.5 us (k x 8.889 kHz): there the samples sit
 * on two carrier phases and the mean square reads anywhere from -98 % to +42 % (study finding 4).
 * For a unit sine the sampled mean square is (1 - Re(S e^{j2phi})) / 2 with S = mean(exp(j 4 pi f t_k)),
 * so |S| bounds the relative mean-square error over carrier phase; the same figure at 2/4/6 f covers
 * the fundamental x 3rd/5th products. rms_shadow_lock_metric() computes it for the real sample
 * instants of one half line cycle; rms_shadow_select_fs() picks, from 64 clocks 72.0-79.875 kS/s, the
 * one with the smallest figure for the commanded frequency. VBUS keeps >= 24 kS/s (needs 20).
 */
#include <stdbool.h>
#include <stdint.h>

#define RMS_SHADOW_PATTERN_LEN   9u
#define RMS_SHADOW_CT_SLOT_A     1u
#define RMS_SHADOW_CT_SLOT_B     3u
#define RMS_SHADOW_FS_NOMINAL_HZ 80000u   /* the as-built clock (n21_hw_esp32.c) */
#define RMS_SHADOW_FS_STEP_HZ    125u
#define RMS_SHADOW_FS_COUNT      64u      /* 80000 - 125 m, m = 0..63 */
/* Reselect (reconfigure the ADC) only when the clock in use is worse than this; the figure is the
 * worst relative mean-square error, 0.02 = about 1 % in RMS. */
#define RMS_SHADOW_LOCK_HOLD     0.02f
#define RMS_SHADOW_MIN_SAMPLES   100u     /* a half holds about 148 CT_MON samples */

/* Figure of merit |sum w exp(j 2 pi k f t)| / sum w (k = 2, 4, 6; weights 1, 0.3, 0.1) over the CT_MON
 * sample instants of one 1/120 s window at clock fs_hz. 0 = well conditioned, ~1 = phase locked.
 * The study's figure weights every sample equally (w = 1). Here w = sin^2(pi t / half), the energy the
 * reading carries under the unsmoothed line envelope, because the product of that envelope with the
 * carrier term shifts the beat by +-120 Hz, a full cycle over the window; with w = 1 a 50 Hz scan of
 * 31-55 kHz leaves one bin at 4.6 % error (48.6 kHz), with the weight the worst bin is 0.5 %. */
float rms_shadow_lock_metric(float f_hz, uint32_t fs_hz);
/* argmin over the 64 clocks (first minimum). metric_out may be NULL. */
uint32_t rms_shadow_select_fs(float f_hz, float *metric_out);
/* As the binding uses it: keep cur_fs_hz while its figure is <= RMS_SHADOW_LOCK_HOLD, else select. */
uint32_t rms_shadow_hold_fs(float f_hz, uint32_t cur_fs_hz);

typedef struct {
    double sumsq;
    uint32_t n;
} rms_shadow_t;
void rms_shadow_reset(rms_shadow_t *);
/* One CT_MON sample, mV at the pin (calibrated), against the idle level zero_mv (0 = 1650 mV). */
void rms_shadow_add_mv(rms_shadow_t *, float mv, float zero_mv);
/* Merge a partial sum (the ADC task accumulates per frame). */
void rms_shadow_add_sum(rms_shadow_t *, double sumsq_a2, uint32_t n);
/* Half-cycle RMS in A from what was added; false (and *rms_a = NAN) with too few samples. Resets. */
bool rms_shadow_close(rms_shadow_t *, float *rms_a);
#endif
