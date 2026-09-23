#include "protocol.h"

uint32_t pe_crc32(const uint8_t *data, size_t length) {
    uint32_t crc = UINT32_MAX;
    for (size_t i = 0; i < length; ++i) {
        crc ^= data[i];
        for (unsigned bit = 0; bit < 8; ++bit) {
            crc = (crc >> 1) ^ ((crc & 1u) ? UINT32_C(0xEDB88320) : 0u);
        }
    }
    return ~crc;
}

static uint32_t read32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void write32(uint8_t *p, uint32_t value) {
    for (unsigned i = 0; i < 4; ++i) {
        p[i] = (uint8_t)(value >> (8u * i));
    }
}

void pe_frame_encode(const pe_frame_t *frame, uint8_t out[PE_FRAME_SIZE]) {
    out[0] = PE_FRAME_MAGIC;
    out[1] = PE_FRAME_VERSION;
    out[2] = (uint8_t)frame->type;
    out[3] = 0u;
    for (unsigned i = 0; i < 8; ++i) {
        out[4 + i] = (uint8_t)(frame->session >> (8u * i));
    }
    write32(out + 12, frame->value);
    write32(out + 16, pe_crc32(out, 16));
}

bool pe_frame_decode(const uint8_t *data, size_t length, pe_frame_t *frame) {
    if (data == NULL || frame == NULL || length != PE_FRAME_SIZE ||
        data[0] != PE_FRAME_MAGIC || data[1] != PE_FRAME_VERSION ||
        data[3] != 0u || data[2] < PE_PREPARE_CHALLENGE ||
        data[2] > PE_ABORT || read32(data + 16) != pe_crc32(data, 16)) {
        return false;
    }
    uint64_t session = 0;
    for (unsigned i = 0; i < 8; ++i) {
        session |= (uint64_t)data[4 + i] << (8u * i);
    }
    frame->type = (pe_frame_type_t)data[2];
    frame->session = session;
    frame->value = read32(data + 12);
    return true;
}
