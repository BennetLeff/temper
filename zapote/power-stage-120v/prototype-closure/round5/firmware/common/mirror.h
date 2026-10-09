#ifndef R5_MIRROR_H
#define R5_MIRROR_H
#include <stdbool.h>
#include <stdint.h>
#define R5_MIRROR_MAX 5u
/* One all-off + one slot per contact.100us settle,150us slots; publish only
 * complete scans.3channels600us;5channels900us; every scan<=1ms, age<=2ms.
 * Hardware settling/wetting must be qualified before commissioning. */
typedef struct {
    uint32_t slot_at,slot_deadline,scan_at,published_us,changed_us[R5_MIRROR_MAX];
    unsigned count,slot,excite_mask,pending_mask;
    bool sampled,started,raw[R5_MIRROR_MAX],released[R5_MIRROR_MAX];
    bool qualified,fault,static_requested,static_ready;
} r5_mirror_t;
bool r5_mirror_init(r5_mirror_t *,unsigned count);
bool r5_mirror_step(r5_mirror_t *,uint32_t us,const bool receiver[R5_MIRROR_MAX],
                    bool all_coils_off,bool discharged);
/* Boot-only handoff after electrical scan; all excitations remain HIGH. */
bool r5_mirror_hold_static(r5_mirror_t *,uint32_t us);
bool r5_mirror_fresh(const r5_mirror_t *,uint32_t us);
#endif
