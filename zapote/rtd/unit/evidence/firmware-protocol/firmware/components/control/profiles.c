/**
 * @file profiles.c
 * @brief Implementation of multi-stage cooking profiles
 */

#include "profiles.h"
#include <string.h>

void profile_init_status(profile_status_t *status) {
    memset(status, 0, sizeof(profile_status_t));
}

void profile_start(profile_status_t *status, const cooking_profile_t *profile, uint32_t now_ms) {
    status->active_profile = profile;
    status->current_stage_idx = 0;
    status->stage_start_time_ms = now_ms;
    status->active = (profile != NULL && profile->num_stages > 0);
    status->completed = false;
}

bool profile_update(profile_status_t *status, float current_temp, uint32_t now_ms) {
    if (!status->active || status->completed || !status->active_profile) {
        return false;
    }

    const profile_stage_t *stage = &status->active_profile->stages[status->current_stage_idx];
    bool stage_done = false;

    // Transition condition 1: Time-based
    if (stage->duration_ms > 0) {
        if ((now_ms - status->stage_start_time_ms) >= stage->duration_ms) {
            stage_done = true;
        }
    }

    // Transition condition 2: Temperature-based (only if duration is 0 or we want to wait for temp first)
    // For now, let's keep it simple: if duration is 0, we just hold at temp.
    // If we wanted "Heat to X then move to Y", we'd need another field like 'until_temp_reached'.

    if (stage_done) {
        status->current_stage_idx++;
        status->stage_start_time_ms = now_ms;

        if (status->current_stage_idx >= status->active_profile->num_stages) {
            status->completed = true;
            status->active = false;
        }
        return true;
    }

    return false;
}

void profile_get_current_settings(const profile_status_t *status, float *target_temp, uint8_t *intensity, bool *use_probe) {
    if (!status->active || !status->active_profile) return;

    const profile_stage_t *stage = &status->active_profile->stages[status->current_stage_idx];
    if (target_temp) *target_temp = stage->target_temp;
    if (intensity) *intensity = stage->intensity;
    if (use_probe) *use_probe = stage->use_probe;
}

static const cooking_profile_t SIMMER_PROFILE = {
    .name = "Simmer",
    .num_stages = 1,
    .stages = {
        { .target_temp = 95.0f, .intensity = 3, .duration_ms = 0, .use_probe = false }
    }
};

static const cooking_profile_t SEAR_AND_HOLD_PROFILE = {
    .name = "Sear & Hold",
    .num_stages = 2,
    .stages = {
        { .target_temp = 230.0f, .intensity = 10, .duration_ms = 120000, .use_probe = false }, // 2 min sear
        { .target_temp = 65.0f, .intensity = 2, .duration_ms = 0, .use_probe = false }         // hold
    }
};

static const cooking_profile_t SOUS_VIDE_PROFILE = {
    .name = "Sous Vide",
    .num_stages = 1,
    .stages = {
        { .target_temp = 58.0f, .intensity = 2, .duration_ms = 0, .use_probe = true }
    }
};

const cooking_profile_t* profile_get_simmer(void) { return &SIMMER_PROFILE; }
const cooking_profile_t* profile_get_sear_and_hold(void) { return &SEAR_AND_HOLD_PROFILE; }
const cooking_profile_t* profile_get_sous_vide(void) { return &SOUS_VIDE_PROFILE; }
