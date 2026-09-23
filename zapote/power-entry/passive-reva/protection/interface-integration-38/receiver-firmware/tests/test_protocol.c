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

int main(void) {
    round_trip_all_types();
    invalid_frames_are_rejected();
    return 0;
}
