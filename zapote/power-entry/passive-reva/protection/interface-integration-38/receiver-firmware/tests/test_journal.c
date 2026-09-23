#include "../journal.h"
#include "../protocol.h"

#include <assert.h>
#include <limits.h>
#include <string.h>

typedef struct {
    uint8_t bytes[PE_JOURNAL_BYTES];
    int writes;
    int fail_after;
} memory_t;

static uint8_t read_byte(void *context, uint16_t address) {
    memory_t *memory = context;
    assert(address < PE_JOURNAL_BYTES);
    return memory->bytes[address];
}

static bool write_byte(void *context, uint16_t address, uint8_t value) {
    memory_t *memory = context;
    assert(address < PE_JOURNAL_BYTES);
    if (memory->writes == memory->fail_after) return false;
    memory->bytes[address] = value;
    ++memory->writes;
    return memory->writes != memory->fail_after;
}

static pe_journal_io_t io_for(memory_t *memory) {
    pe_journal_io_t io = {memory, read_byte, write_byte};
    return io;
}

/* Manufacturing fixture only: initialize ID zero once, before deployment.
 * Runtime code has no provision-blank operation. */
static void provision(memory_t *memory) {
    memset(memory, 0xFF, sizeof(*memory));
    memory->writes = 0;
    memory->fail_after = INT_MAX;
    uint8_t *p = memory->bytes;
    p[0] = 'T'; p[1] = 'P'; p[2] = 'E'; p[3] = 1;
    for (unsigned i = 0; i < 8; ++i) {
        p[4 + i] = 0;
        p[12 + i] = 0xFF;
    }
    uint32_t crc = pe_crc32(p, 20);
    for (unsigned i = 0; i < 4; ++i) p[20 + i] = (uint8_t)(crc >> (8u * i));
    p[31] = 0x3C;
}

static void every_write_boundary_fails_closed_or_advances(void) {
    for (int stop = 0; stop <= 64; ++stop) {
        memory_t memory;
        provision(&memory);
        memory.fail_after = stop;
        pe_journal_io_t io = io_for(&memory);
        pe_journal_state_t state;
        uint64_t published = UINT64_MAX;
        assert(!pe_journal_reserve(&io, &published));
        assert(published == UINT64_MAX);
        memory.fail_after = INT_MAX;
        memory.writes = 0;
        if (pe_journal_scan(&io, &state)) {
            assert(state.highwater == 0 || state.highwater == 1);
            uint64_t next = 0;
            assert(pe_journal_reserve(&io, &next));
            assert(next > state.highwater);
        }
    }
}

static void rotation_and_corruption(void) {
    memory_t memory;
    provision(&memory);
    pe_journal_io_t io = io_for(&memory);
    pe_journal_state_t state;
    uint64_t id = 0;
    for (unsigned i = 1; i <= 40; ++i) {
        assert(pe_journal_reserve(&io, &id));
        assert(id == i);
    }
    assert(pe_journal_scan(&io, &state));
    assert(state.count == PE_JOURNAL_SLOTS && state.highwater == 40);
    memory.bytes[state.newest_slot * PE_JOURNAL_SLOT_BYTES + 12] ^= 1u;
    assert(!pe_journal_scan(&io, &state));
    assert(!pe_journal_reserve(&io, &id));
}

static void blank_store_never_reprovisions_itself(void) {
    memory_t memory;
    memset(&memory, 0xFF, sizeof(memory));
    pe_journal_io_t io = io_for(&memory);
    uint64_t id;
    assert(!pe_journal_reserve(&io, &id));
}

int main(void) {
    every_write_boundary_fails_closed_or_advances();
    rotation_and_corruption();
    blank_store_never_reprovisions_itself();
    return 0;
}
