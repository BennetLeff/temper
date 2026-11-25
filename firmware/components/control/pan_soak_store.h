/**
 * @file pan_soak_store.h
 * @brief Coil-off time across a power cycle for the cold-soak check
 *        (output/temper-sensor-r3/firmware/DECISIONS.md D-SOAKNV, open item 14).
 *
 * The cold-soak check (pan_cold_soak.h, D-SOAK) needs the coil off >= 30 min
 * and 15 min of flat history. Without a store, power-up counts as coil
 * activity, so after any power cycle the check waits 30 min of uptime.
 *
 * Time across a power loss: the ESP32-S3 has no battery-backed clock. Its RTC
 * timer "can also persist time keeping across any resets (with the exception
 * of power-on resets which reset the RTC timer)" (ESP-IDF v5.3.6
 * docs/en/api-reference/system/system_time.rst), and zapote/controller has no
 * backup supply or external RTC, so after mains loss neither clock knows how
 * long the unit was unpowered. Wall time (SNTP) is not assumed: the unit may
 * have no network. The store therefore keeps a LOWER BOUND only: "the coil had
 * been off at least off_s when this was written". The unpowered interval
 * counts as zero, which is conservative: it can only make the unit look less
 * soaked than it is.
 *
 * The token (a u32, off_s) in NVS (main/soak_store_nvs.c):
 *   write   once per coil-off period, when the coil-off time first reaches
 *           PSS_TOKEN_OFF_S (soak_n - window = 15 min): with it, the check
 *           after a power cycle runs as soon as the 15 min RAM history is
 *           complete (the window cannot be persisted: the temperatures during
 *           the outage are unknown and flatness must be observed);
 *   revoke  (erase) before the coil is energised (pan_control_begin) and on any
 *           coil activity the history sees, whenever a token is present;
 *   boot    a present, plausible token (1 .. PSS_TOKEN_MAX_S) credits off_s:
 *           pcs last-activity = now - off_s. Absent, unreadable or implausible
 *           = unknown = not soaked (power-up counts as activity), as before.
 * Writes: at most one write and one erase per cook cycle; never periodic.
 * ESP-IDF NVS: "one should be able to power off the device at any point and
 * time ... This should not result in loss of data, except for the new
 * key-value pair if it was being written at the moment of powering off"
 * (nvs_flash.rst): a torn write is an absent token (unknown, safe). A torn
 * erase leaves the token, but the erase precedes energising and is verified,
 * so the coil was still off.
 *
 * A failed revoke: the token stays and could credit a coil-off period the next
 * boot that a later cook interrupted. The worst it can do is let the check run
 * on a unit still cooling from that cook: a soaked-looking unit with the
 * heatsink still warm over the Pt100 reads as a leak (a false, clearable
 * FAULT_PROBE_LEAKAGE); a skip and a pass have the same effect (no latch), so
 * no leak is missed that the RAM-only check would have caught. Heating is
 * therefore not blocked on a store failure: the store is disabled for the
 * session (no further writes) and the failure is counted.
 */

#ifndef PAN_SOAK_STORE_H
#define PAN_SOAK_STORE_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** soak_n - window (pan_cold_soak.h PCS_SOAK_N_S - PCS_WINDOW_S). */
#define PSS_TOKEN_OFF_S 900u
/** A token above this is implausible (only PSS_TOKEN_OFF_S is ever written). */
#define PSS_TOKEN_MAX_S 3600u

typedef struct {
    /** Read the token; false: absent or unreadable. */
    bool (*load)(void *ctx, uint32_t *off_s);
    /** Write and commit the token. */
    bool (*save)(void *ctx, uint32_t off_s);
    /** Erase and commit; an absent token is success. */
    bool (*clear)(void *ctx);
    void *ctx;
} pss_hal_t;

typedef struct {
    bool token_present;    /**< NVS holds a token, as far as this session knows */
    bool written_this_off; /**< the token was written in this coil-off period */
    bool disabled;         /**< a store operation failed: no more writes this session */
    uint32_t writes, clears, failures;
    uint32_t boot_credit_s;/**< what the boot credited (0: unknown) */
} pss_t;

/** At boot: read the token. Returns the coil-off seconds to credit (0 = unknown). */
uint32_t pss_boot(pss_t *s, const pss_hal_t *hal);

/**
 * Each history note (pan_control_soak_note): coil_active revokes a present
 * token; otherwise, the first time off_s reaches PSS_TOKEN_OFF_S in this
 * coil-off period, the token is written.
 */
void pss_note(pss_t *s, const pss_hal_t *hal, bool coil_active, float off_s);

/** Before energising: revoke a present token. True when none remains. */
bool pss_revoke(pss_t *s, const pss_hal_t *hal);

/** The credit a (re)initialised history may take now: PSS_TOKEN_OFF_S while a
 *  token stands for this coil-off period, else 0. */
uint32_t pss_credit_s(const pss_t *s);

#ifdef __cplusplus
}
#endif

#endif /* PAN_SOAK_STORE_H */
