#include "wave.h"
#include <math.h>

uint32_t wave_crc32_update(uint32_t crc, const void *buffer, size_t length) {
    const uint8_t *p = buffer;
    crc = ~crc;
    for (size_t i = 0; i < length; ++i) {
        crc ^= p[i];
        for (unsigned bit = 0; bit < 8u; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

uint32_t wave_crc32(const void *buffer, size_t length) { return wave_crc32_update(0, buffer, length); }

static bool period_ok(uint32_t period) {
    return period >= WAVE_MIN_PERIOD && period <= WAVE_MAX_PERIOD;
}

wave_status wave_check(const int32_t *words, uint32_t period) {
    if (!period_ok(period)) return WAVE_ERR_PERIOD;
    for (uint32_t k = 0; k < period; ++k)
        if (words[k] > SOURCE_LIMIT_CODE || words[k] < -SOURCE_LIMIT_CODE) return WAVE_ERR_LEVEL;
    return WAVE_OK;
}

wave_status wave_tone(int32_t *words, uint32_t cycles, uint32_t period, uint32_t millivolts) {
    if (!period_ok(period)) return WAVE_ERR_PERIOD;
    /* FS_HZ * cycles / period <= TONE_MAX_HZ, in integers. */
    if (cycles == 0u || (uint64_t)FS_HZ * cycles > (uint64_t)TONE_MAX_HZ * period)
        return WAVE_ERR_FREQUENCY;
    if (millivolts == 0u || millivolts > SOURCE_LIMIT_MV) return WAVE_ERR_LEVEL;
    const double amplitude = (double)((int64_t)SOURCE_LIMIT_CODE * millivolts / SOURCE_LIMIT_MV);
    const double two_pi = 6.283185307179586476925;
    for (uint32_t k = 0; k < period; ++k) {
        /* Reduce cycles * k modulo the period first so the argument stays in [0, 2 pi). */
        uint32_t phase = (uint32_t)(((uint64_t)cycles * k) % period);
        words[k] = (int32_t)lround(amplitude * sin(two_pi * (double)phase / (double)period));
    }
    return wave_check(words, period);
}
