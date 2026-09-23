#include "journal.h"
#include "protocol.h"

#include <stddef.h>
#include <string.h>

/* 0..3 magic/version, 4..11 ID, 12..19 complement, 20..23 CRC of
 * bytes 0..19, 24..30 erased FF, 31 final commit marker. */
#define COMMIT_OFFSET 31u
#define COMMIT_MARKER 0x3Cu

static void read_slot(const pe_journal_io_t *io, unsigned slot,
                      uint8_t bytes[PE_JOURNAL_SLOT_BYTES]) {
    for (unsigned i = 0; i < PE_JOURNAL_SLOT_BYTES; ++i) {
        bytes[i] = io->read_byte(io->context,
                                 (uint16_t)(slot * PE_JOURNAL_SLOT_BYTES + i));
    }
}

static bool blank(const uint8_t bytes[PE_JOURNAL_SLOT_BYTES]) {
    for (unsigned i = 0; i < PE_JOURNAL_SLOT_BYTES; ++i) {
        if (bytes[i] != 0xFFu) return false;
    }
    return true;
}

static uint32_t read32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint64_t read64(const uint8_t *p) {
    uint64_t value = 0;
    for (unsigned i = 0; i < 8; ++i) value |= (uint64_t)p[i] << (8u * i);
    return value;
}

static void write32(uint8_t *p, uint32_t value) {
    for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(value >> (8u * i));
}

static void write64(uint8_t *p, uint64_t value) {
    for (unsigned i = 0; i < 8; ++i) p[i] = (uint8_t)(value >> (8u * i));
}

static void make_record(uint64_t id, uint8_t bytes[PE_JOURNAL_SLOT_BYTES]) {
    memset(bytes, 0xFF, PE_JOURNAL_SLOT_BYTES);
    bytes[0] = 'T'; bytes[1] = 'P'; bytes[2] = 'E'; bytes[3] = 1;
    write64(bytes + 4, id);
    write64(bytes + 12, ~id);
    write32(bytes + 20, pe_crc32(bytes, 20));
    bytes[COMMIT_OFFSET] = COMMIT_MARKER;
}

static bool valid(const uint8_t bytes[PE_JOURNAL_SLOT_BYTES], uint64_t *id) {
    if (bytes[0] != 'T' || bytes[1] != 'P' || bytes[2] != 'E' ||
        bytes[3] != 1 || bytes[COMMIT_OFFSET] != COMMIT_MARKER ||
        read32(bytes + 20) != pe_crc32(bytes, 20)) return false;
    for (unsigned i = 24; i < COMMIT_OFFSET; ++i) {
        if (bytes[i] != 0xFFu) return false;
    }
    *id = read64(bytes + 4);
    return read64(bytes + 12) == ~*id && *id <= PE_JOURNAL_ID_CEILING;
}

bool pe_journal_scan(const pe_journal_io_t *io, pe_journal_state_t *state) {
    if (io == NULL || io->read_byte == NULL || state == NULL) return false;
    uint64_t ids[PE_JOURNAL_SLOTS];
    unsigned slots[PE_JOURNAL_SLOTS];
    unsigned count = 0;
    uint8_t bytes[PE_JOURNAL_SLOT_BYTES];
    for (unsigned slot = 0; slot < PE_JOURNAL_SLOTS; ++slot) {
        read_slot(io, slot, bytes);
        if (blank(bytes)) continue;
        uint64_t id;
        if (!valid(bytes, &id) || slot != id % PE_JOURNAL_SLOTS) return false;
        ids[count] = id;
        slots[count++] = slot;
    }
    if (count == 0) return false;
    /* Every completed reservation increments exactly once; retained records
     * must therefore form one contiguous run, including skipped challenges. */
    for (unsigned i = 0; i < count; ++i) {
        for (unsigned j = i + 1; j < count; ++j) {
            if (ids[j] < ids[i]) {
                uint64_t id = ids[i]; ids[i] = ids[j]; ids[j] = id;
                unsigned slot = slots[i]; slots[i] = slots[j]; slots[j] = slot;
            }
        }
    }
    if (ids[0] == 0 && slots[0] != 0) return false;
    for (unsigned i = 1; i < count; ++i) {
        if (ids[i] != ids[i - 1] + 1 ||
            slots[i] != (slots[i - 1] + 1u) % PE_JOURNAL_SLOTS) return false;
    }
    state->highwater = ids[count - 1];
    state->newest_slot = (uint8_t)slots[count - 1];
    state->count = (uint8_t)count;
    return true;
}

bool pe_journal_reserve(const pe_journal_io_t *io, uint64_t *reserved_id) {
    pe_journal_state_t before, after;
    if (io == NULL || io->write_byte == NULL || reserved_id == NULL ||
        !pe_journal_scan(io, &before) ||
        before.highwater >= PE_JOURNAL_ID_CEILING) return false;
    unsigned slot = (before.newest_slot + 1u) % PE_JOURNAL_SLOTS;
    uint8_t record[PE_JOURNAL_SLOT_BYTES];
    uint8_t actual[PE_JOURNAL_SLOT_BYTES];
    make_record(before.highwater + 1u, record);
    for (unsigned i = 0; i < PE_JOURNAL_SLOT_BYTES; ++i) {
        if (!io->write_byte(io->context,
                            (uint16_t)(slot * PE_JOURNAL_SLOT_BYTES + i),
                            0xFFu)) return false;
    }
    read_slot(io, slot, actual);
    if (!blank(actual)) return false;
    for (unsigned i = 0; i < COMMIT_OFFSET; ++i) {
        if (!io->write_byte(io->context,
                            (uint16_t)(slot * PE_JOURNAL_SLOT_BYTES + i),
                            record[i])) return false;
    }
    read_slot(io, slot, actual);
    if (memcmp(actual, record, COMMIT_OFFSET) != 0 ||
        actual[COMMIT_OFFSET] != 0xFFu) return false;
    if (!io->write_byte(io->context,
                        (uint16_t)(slot * PE_JOURNAL_SLOT_BYTES + COMMIT_OFFSET),
                        COMMIT_MARKER)) return false;
    if (!pe_journal_scan(io, &after) ||
        after.highwater != before.highwater + 1u ||
        after.newest_slot != slot) return false;
    *reserved_id = after.highwater;
    return true;
}
