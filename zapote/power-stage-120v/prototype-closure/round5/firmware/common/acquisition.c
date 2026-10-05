#include "acquisition.h"
#include <math.h>
#include <string.h>
uint16_t ads_crc16(const uint8_t *p, size_t n)
{
    uint16_t crc = 0xffff;
    while (n--) {
        crc ^= (uint16_t)*p++ << 8;
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (uint16_t)((crc << 1) ^ ((crc & 0x8000) ? 0x1021 : 0));
    }
    return crc;
}
void ads_command(uint16_t command, uint16_t data, uint8_t out[ADS_FRAME_BYTES])
{
    memset(out, 0, ADS_FRAME_BYTES);
    out[0] = command >> 8; out[1] = command;
    bool write_one = (command & 0xe000u) == 0x6000u;
    size_t crc_at = write_one ? 6 : 3;
    if (write_one) { out[3] = data >> 8; out[4] = data; }
    /* DIN CRC follows command/register payload, not the final DOUT CRC slot. */
    uint16_t crc = ads_crc16(out, crc_at);
    out[crc_at] = crc >> 8; out[crc_at+1] = crc;
}
bool ads_accept(ads_receiver_t *r, const uint8_t f[ADS_FRAME_BYTES], uint32_t capture,
                uint32_t now, ads_sample_t *s)
{
    if (!r || !f || !s) return false;
    uint16_t status = (uint16_t)((f[0] << 8) | f[1]);
    uint16_t crc = (uint16_t)((f[27] << 8) | f[28]);
    /* LOCK accepted; all eight DRDY bits required. Reject RESET, resync,
       register-map/input CRC faults, ANSI CRC and incorrect word length. */
    bool valid = (status & 0x7fff) == 0x01ff && f[2] == 0 && f[29] == 0 &&
        ads_crc16(f, 27) == crc && (uint32_t)(now - capture) <= 200 &&
        (!r->seen || ((uint32_t)(capture - r->captured_us) >= 200 &&
                     (uint32_t)(capture - r->captured_us) <= 350));
    if (!valid || r->fault) { r->fault = true; return false; }
    for (unsigned i = 0; i < 8; ++i) {
        const uint8_t *p = f + 3 + 3*i;
        uint32_t u = ((uint32_t)p[0] << 16) | ((uint32_t)p[1] << 8) | p[2];
        s->code[i] = (u & 0x800000) ? (int32_t)u - 0x1000000 : (int32_t)u;
        if (s->code[i] >= 8380000 || s->code[i] <= -8380000) {
            r->fault = true; return false; /* Clipping invalidates every channel. */
        }
    }
    r->seen = true; r->captured_us = capture;
    s->captured_us = capture; s->serial = ++r->serial;
    return true;
}
bool ads_fresh(const ads_receiver_t *r, uint32_t now)
{ return r && r->seen && !r->fault && (uint32_t)(now - r->captured_us) <= 1000; }
bool post_record_accept(post_record_t *r, uint32_t nonce, uint32_t serial,
                        uint32_t now, float ohm, float low, float high,
                        bool released, bool discharged, bool operator_ok)
{
    if (!r) return false;
    bool ok = nonce && serial && serial > r->serial && released && discharged && operator_ok &&
        isfinite(ohm) && isfinite(low) && isfinite(high) && low > 0 && high > low &&
        ohm >= low && ohm <= high;
    r->valid = false;
    if (!ok) return false;
    *r = (post_record_t){nonce, serial, now, ohm, true};
    return true;
}
bool post_record_fresh(const post_record_t *r, uint32_t nonce, uint32_t now)
{ return r && r->valid && nonce && r->boot_nonce == nonce && (uint32_t)(now-r->issued_ms) <= 60000; }
void post_record_consume(post_record_t *r) { if (r) r->valid = false; }
bool catch_correlates(float bus, float cap, float error, float diode, bool gain, bool seen)
{
    return gain && seen && isfinite(bus) && isfinite(cap) && isfinite(error) && isfinite(diode) &&
        error >= 0 && error <= 10 && diode >= 0 && diode <= 5 && bus >= 100 &&
        cap >= bus-diode-error && cap <= bus+error;
}
