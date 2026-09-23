#ifndef TEMPER_POWER_ENTRY_JOURNAL_H
#define TEMPER_POWER_ENTRY_JOURNAL_H

#include <stdbool.h>
#include <stdint.h>

#define PE_JOURNAL_SLOTS 16u
#define PE_JOURNAL_SLOT_BYTES 32u
#define PE_JOURNAL_BYTES (PE_JOURNAL_SLOTS * PE_JOURNAL_SLOT_BYTES)
/* Candidate policy: at most 1,000 overwrite cycles per slot. Reassess with
 * the exact temperature/endurance guarantee before production use. */
#define PE_JOURNAL_ID_CEILING UINT64_C(16000)

typedef struct {
    void *context;
    uint8_t (*read_byte)(void *context, uint16_t address);
    /* Must return only after NVM completion and status checking. False
     * includes a power interruption; no caller may publish a challenge. */
    bool (*write_byte)(void *context, uint16_t address, uint8_t value);
} pe_journal_io_t;

typedef struct {
    uint64_t highwater;
    uint8_t newest_slot;
    uint8_t count;
} pe_journal_state_t;

/* A blank, corrupt, duplicate, or ambiguous store fails closed. Manufacturing
 * must provision one valid ID=0 record in slot 0. */
bool pe_journal_scan(const pe_journal_io_t *io, pe_journal_state_t *state);
/* Requires external abort physically asserted throughout. On failure, caller
 * must lock out and reboot/scan; it must not retry in the same session. */
bool pe_journal_reserve(const pe_journal_io_t *io, uint64_t *reserved_id);

#endif
