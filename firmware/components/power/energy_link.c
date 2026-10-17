#include "energy_link.h"
static void put32(uint8_t *b, uint32_t n){
    for (unsigned i = 0; i < 4; i++)
        b[i] = (uint8_t)(n >> (24 - 8 * i));
}
static uint32_t get32(const uint8_t *b)
{
    return ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16) | ((uint32_t)b[2] << 8) | b[3];
}
static uint32_t crc32(const uint8_t *b, size_t n)
{
    uint32_t c = UINT32_MAX;
    for (size_t i = 0; i < n; i++) {
        c ^= b[i];
        for (unsigned j = 0; j < 8; j++)
            c = (c >> 1) ^ (UINT32_C(0xedb88320) & (0 - (c & 1)));
    }
    return ~c;
}
static bool valid(const energy_link_packet_t *p)
{
    return p && (p->kind == ENERGY_LINK_COMMAND || p->kind == ENERGY_LINK_STATUS) &&
        p->state <= 8 && !(p->flags & ~7u) && p->requested_mw <= 2000000 &&
        (p->kind != ENERGY_LINK_STATUS || p->requested_mw == 0) &&
        (!(p->flags & ENERGY_LINK_FAULT) || !(p->flags & ENERGY_LINK_REQUEST));
}
bool energy_link_encode(const energy_link_packet_t *p, uint8_t b[ENERGY_LINK_SIZE])
{
    if (!b || !valid(p))
        return false;
    b[0] = 'T';
    b[1] = 'E';
    b[2] = 1;
    b[3] = p->kind;
    put32(b + 4, p->sequence);
    b[8] = (uint8_t)(p->flags >> 8);
    b[9] = (uint8_t)p->flags;
    b[10] = p->state;
    b[11] = 0;
    put32(b + 12, p->requested_mw);
    put32(b + 16, crc32(b, 16));
    return true;
}
bool energy_link_receive(energy_link_receiver_t *r, uint8_t kind, const uint8_t *b, size_t n, uint32_t now, energy_link_packet_t *out)
{
    if (!r || !b || !out || n != ENERGY_LINK_SIZE || b[0] != 'T' || b[1] != 'E' || b[2] != 1 ||
        b[3] != kind || b[11] != 0 || get32(b + 16) != crc32(b, 16))
        return false;
    energy_link_packet_t p = {.kind = b[3],.sequence = get32(b + 4),.flags = (uint16_t)((b[8] << 8) | b[9]),.state = b[10],.requested_mw = get32(b + 12)};
    uint32_t delta = p.sequence - r->sequence;
    if (!valid(&p) || (r->seen && (delta == 0 || delta >= UINT32_C(0x80000000))))
        return false;
    r->seen = true;
    r->sequence = p.sequence;
    r->received_ms = now;
    *out = p;
    return true;
}
bool energy_link_fresh(const energy_link_receiver_t *r, uint32_t now)
{
    return r && r->seen && (uint32_t)(now - r->received_ms) <= 20;
}
