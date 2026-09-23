#include "protocol.h"

#include <string.h>

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

void pe_stream_init(pe_stream_t *stream, uint32_t max_gap_ms) {
    memset(stream, 0, sizeof(*stream));
    stream->max_gap_ms = max_gap_ms;
}

pe_stream_result_t pe_stream_push_result(pe_stream_t *stream, uint8_t byte,
                                          uint64_t now_ms, pe_frame_t *frame) {
    if (stream == NULL || frame == NULL || stream->max_gap_ms == 0) {
        return PE_STREAM_ERROR;
    }
    bool interrupted = false;
    if (stream->count != 0 &&
        (now_ms < stream->last_byte_ms ||
         now_ms - stream->last_byte_ms > stream->max_gap_ms)) {
        stream->count = 0;
        interrupted = true;
    }
    stream->last_byte_ms = now_ms;
    if (stream->count == 0 && byte != PE_FRAME_MAGIC) {
        return interrupted ? PE_STREAM_ERROR : PE_STREAM_INCOMPLETE;
    }
    stream->bytes[stream->count++] = byte;
    if (stream->count != PE_FRAME_SIZE) {
        return interrupted ? PE_STREAM_ERROR : PE_STREAM_INCOMPLETE;
    }
    if (pe_frame_decode(stream->bytes, PE_FRAME_SIZE, frame)) {
        stream->count = 0;
        return PE_STREAM_FRAME;
    }
    for (unsigned i = 1; i < PE_FRAME_SIZE; ++i) {
        if (stream->bytes[i] == PE_FRAME_MAGIC) {
            stream->count = PE_FRAME_SIZE - i;
            memmove(stream->bytes, stream->bytes + i, stream->count);
            return PE_STREAM_ERROR;
        }
    }
    stream->count = 0;
    return PE_STREAM_ERROR;
}

bool pe_stream_expire(pe_stream_t *stream, uint64_t now_ms) {
    if (stream == NULL || stream->max_gap_ms == 0) return true;
    if (stream->count == 0) return false;
    if (now_ms >= stream->last_byte_ms &&
        now_ms - stream->last_byte_ms <= stream->max_gap_ms) return false;
    stream->count = 0;
    return true;
}

bool pe_stream_push(pe_stream_t *stream, uint8_t byte, uint64_t now_ms,
                    pe_frame_t *frame) {
    return pe_stream_push_result(stream, byte, now_ms, frame) == PE_STREAM_FRAME;
}
