#pragma once
/* DAC waveform rules and generation. No Pico SDK dependency (test/test_host.c).

   A waveform is `period` signed 32-bit DAC words played in a loop at FS_HZ. Word 2^31
   would be the TAC5112 differential full scale, 2 Vrms = 2.828 V peak (SLASF24A 6.5). The
   OPA810 difference stage (2.0 kOhm / 2.2 kOhm) scales it to SOURCE_BUF, so full scale is
   2.571 V peak there. Rev E caps SOURCE_BUF at 1.7 V peak (docs/rev-e-front-end.md):
   SOURCE_LIMIT_CODE = floor(1.7 / (2 sqrt(2) * 2.0 / 2.2) * 2^31). */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define FS_HZ 187500u
#define WAVE_MIN_PERIOD 16u
#define WAVE_MAX_PERIOD 4096u
#define SOURCE_LIMIT_MV 1700u
#define SOURCE_LIMIT_CODE 1419797733
#define TONE_MAX_HZ 85000u /* wideband-mode passband, 0.454 fs */

typedef enum {
    WAVE_OK = 0,
    WAVE_ERR_PERIOD,    /* period outside WAVE_MIN_PERIOD..WAVE_MAX_PERIOD */
    WAVE_ERR_FREQUENCY, /* cycles == 0 or tone above TONE_MAX_HZ */
    WAVE_ERR_LEVEL,     /* amplitude 0 or above the source limit */
} wave_status;

/* IEEE reflected CRC32, as protocol 2. update(update(0, a), b) = crc32(a followed by b). */
uint32_t wave_crc32(const void *buffer, size_t length);
uint32_t wave_crc32_update(uint32_t crc, const void *buffer, size_t length);
/* WAVE_OK if the period is legal and every word is within +-SOURCE_LIMIT_CODE. */
wave_status wave_check(const int32_t *words, uint32_t period);
/* `cycles` sine cycles in `period` words, peak `millivolts` at SOURCE_BUF:
   word k = round(A sin(2 pi cycles k / period)), A = millivolts * LIMIT / 1700.
   Frequency = FS_HZ * cycles / period exactly. */
wave_status wave_tone(int32_t *words, uint32_t cycles, uint32_t period, uint32_t millivolts);
