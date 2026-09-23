#include "../protocol.h"

#include <assert.h>
#include <string.h>

static void round_trip_all_types(void) {
    for (int type = PE_PREPARE_CHALLENGE; type <= PE_ABORT; ++type) {
        pe_frame_t original = {(pe_frame_type_t)type,
                               UINT64_C(0x8070605040302010),
                               UINT32_C(0xA1B2C3D4)};
        pe_frame_t decoded = {0};
        uint8_t bytes[PE_FRAME_SIZE];
        pe_frame_encode(&original, bytes);
        assert(bytes[0] == 0xA5 && bytes[1] == 1 && bytes[2] == type);
        assert(bytes[4] == 0x10 && bytes[11] == 0x80);
        assert(bytes[12] == 0xD4 && bytes[15] == 0xA1);
        if (type == PE_START) {
            /* Independent zlib.crc32 vector over A5 01 06 00 ... A1. */
            assert(bytes[16] == 0x63 && bytes[17] == 0x28);
            assert(bytes[18] == 0x55 && bytes[19] == 0x89);
        }
        assert(pe_frame_decode(bytes, sizeof(bytes), &decoded));
        assert(decoded.type == original.type);
        assert(decoded.session == original.session);
        assert(decoded.value == original.value);
    }
}

static void invalid_frames_are_rejected(void) {
    pe_frame_t input = {PE_START, 42, 7};
    pe_frame_t output = {0};
    uint8_t bytes[PE_FRAME_SIZE];
    pe_frame_encode(&input, bytes);
    assert(!pe_frame_decode(bytes, sizeof(bytes) - 1, &output));
    for (size_t i = 0; i < sizeof(bytes); ++i) {
        bytes[i] ^= 1u;
        assert(!pe_frame_decode(bytes, sizeof(bytes), &output));
        bytes[i] ^= 1u;
    }
    uint8_t bad_version[PE_FRAME_SIZE];
    memcpy(bad_version, bytes, sizeof(bytes));
    bad_version[1] = 2;
    assert(!pe_frame_decode(bad_version, sizeof(bad_version), &output));
}

static void stream_resynchronizes_without_crediting_bad_frames(void) {
    pe_frame_t input = {PE_PING, 64, 12};
    pe_frame_t output = {0};
    uint8_t bytes[PE_FRAME_SIZE];
    pe_frame_encode(&input, bytes);
    pe_stream_t stream;
    pe_stream_init(&stream, 5);
    assert(!pe_stream_push(&stream, 0x17, 0, &output));
    for (size_t i = 0; i < sizeof(bytes); ++i) {
        uint8_t byte = bytes[i] ^ (i == 6 ? 1u : 0u);
        assert(!pe_stream_push(&stream, byte, i + 1, &output));
    }
    for (size_t i = 0; i < sizeof(bytes); ++i) {
        bool complete = pe_stream_push(&stream, bytes[i], i + 30, &output);
        assert(complete == (i == sizeof(bytes) - 1));
    }
    assert(output.type == PE_PING && output.session == 64 && output.value == 12);

    pe_stream_init(&stream, 5);
    for (size_t i = 0; i < sizeof(bytes) / 2; ++i) {
        assert(!pe_stream_push(&stream, bytes[i], i, &output));
    }
    for (size_t i = sizeof(bytes) / 2; i < sizeof(bytes); ++i) {
        assert(!pe_stream_push(&stream, bytes[i], i + 30, &output));
    }
}

int main(void) {
    round_trip_all_types();
    invalid_frames_are_rejected();
    stream_resynchronizes_without_crediting_bad_frames();
    return 0;
}
