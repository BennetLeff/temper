#include "power_entry_authorization.h"

#include <limits.h>
#include <string.h>

static void reset_actions(const pe_source_t *source, pe_source_actions_t *actions) {
    memset(actions, 0, sizeof(*actions));
    actions->stop_n = source->state != PE_SOURCE_LOCKOUT;
    actions->challenge_active = source->state == PE_SOURCE_SEEN_ARMED ||
                                source->state == PE_SOURCE_CLEAR_SEEN;
}

static void abort_source(pe_source_t *source, pe_source_actions_t *actions) {
    source->state = PE_SOURCE_LOCKOUT;
    source->session = 0;
    source->intent = 0;
    source->awaiting_pong = 0;
    source->button_released = false;
    source->local_permit_seen = false;
    source->hot_permit_seen = false;
    source->local_fed = source->local_epoch;
    source->link_fed = source->link_epoch;
    reset_actions(source, actions);
}

static bool physical_disarmed(pe_source_inputs_t inputs) {
    return inputs.rail_good && inputs.safety_ok &&
           !inputs.local_permit_q && !inputs.hot_permit &&
           !inputs.hot_session_q;
}

static bool seen_cleared(pe_source_inputs_t inputs) {
    return physical_disarmed(inputs) && !inputs.permit_seen_q;
}

static bool deadline(uint64_t now, uint32_t window, uint64_t *out) {
    if (window == 0 || UINT64_MAX - now < window) return false;
    *out = now + window;
    return true;
}

static void send(pe_source_actions_t *actions, pe_frame_type_t type,
                 uint64_t session, uint32_t value) {
    actions->transmit = true;
    actions->frame = (pe_frame_t){type, session, value};
}

static bool link_progress(pe_source_t *source, pe_source_actions_t *actions) {
    if (source->link_epoch == UINT32_MAX) {
        abort_source(source, actions);
        return false;
    }
    ++source->link_epoch;
    return true;
}

void pe_source_init(pe_source_t *source, pe_source_config_t config) {
    memset(source, 0, sizeof(*source));
    source->config = config;
    source->state = PE_SOURCE_LOCKOUT;
}

void pe_source_sample(pe_source_t *source, uint64_t now_ms,
                      pe_source_inputs_t inputs, pe_source_actions_t *actions) {
    reset_actions(source, actions);
    if (now_ms < source->now_ms) {
        source->clock_fault = true;
        abort_source(source, actions);
        return;
    }
    source->now_ms = now_ms;
    if (source->clock_fault || !inputs.rail_good || !inputs.safety_ok ||
        source->config.prepare_window_ms == 0 ||
        source->config.start_window_ms == 0 ||
        source->config.watchdog_window_ms == 0) {
        abort_source(source, actions);
        return;
    }
    if (source->state == PE_SOURCE_LOCKOUT) {
        if (physical_disarmed(inputs)) {
            source->state = PE_SOURCE_WAIT_CHALLENGE;
            source->last_wdi_ms = now_ms;
        }
    } else if ((source->state <= PE_SOURCE_READY &&
                (inputs.local_permit_q || inputs.hot_permit)) ||
               (source->state < PE_SOURCE_WAIT_READY && inputs.hot_session_q) ||
               (source->state >= PE_SOURCE_WAIT_ACK &&
                (!inputs.local_permit_q || !inputs.hot_permit ||
                 !inputs.hot_session_q)) ||
               (source->state >= PE_SOURCE_READY &&
                inputs.permit_seen_q && !inputs.hot_permit) ||
               (source->state == PE_SOURCE_PERMIT_PENDING &&
                ((source->local_permit_seen && !inputs.local_permit_q) ||
                 (source->hot_permit_seen && !inputs.hot_permit) ||
                 (inputs.permit_seen_q && !inputs.hot_permit))) ||
               (source->state >= PE_SOURCE_WAIT_READY &&
                !inputs.hot_session_q && source->state != PE_SOURCE_WAIT_READY) ||
               ((source->state == PE_SOURCE_SEEN_ARMED ||
                 source->state == PE_SOURCE_CLEAR_SEEN ||
                 source->state == PE_SOURCE_WAIT_READY ||
                 source->state == PE_SOURCE_PERMIT_PENDING ||
                 source->state == PE_SOURCE_WAIT_ACK) &&
                now_ms >= source->deadline_ms) ||
               now_ms - source->last_wdi_ms >=
                   source->config.watchdog_window_ms) {
        abort_source(source, actions);
        return;
    }

    if (source->state == PE_SOURCE_READY) {
        if (!inputs.start_button_pressed) source->button_released = true;
        if (inputs.start_button_pressed && source->button_released) {
            if (source->next_intent == UINT32_MAX ||
                !deadline(now_ms, source->config.start_window_ms,
                          &source->deadline_ms)) {
                abort_source(source, actions);
                return;
            }
            source->intent = ++source->next_intent;
            source->button_released = false;
            source->local_permit_seen = false;
            source->hot_permit_seen = false;
            source->state = PE_SOURCE_PERMIT_PENDING;
            actions->permit_set_pulse = true;
        }
    } else if (source->state == PE_SOURCE_PERMIT_PENDING) {
        source->local_permit_seen |= inputs.local_permit_q;
        source->hot_permit_seen |= inputs.hot_permit;
        if (inputs.local_permit_q && inputs.hot_permit &&
            inputs.hot_session_q) {
            source->state = PE_SOURCE_WAIT_ACK;
            send(actions, PE_REQUEST, source->session, source->intent);
        }
    }

    if (source->state != PE_SOURCE_LOCKOUT &&
        source->local_epoch != source->local_fed &&
        (source->state == PE_SOURCE_WAIT_CHALLENGE ||
         source->link_epoch != source->link_fed)) {
        source->local_fed = source->local_epoch;
        source->link_fed = source->link_epoch;
        source->last_wdi_ms = now_ms;
        actions->wdi_falling_pulse = true;
    }
    actions->stop_n = source->state != PE_SOURCE_LOCKOUT;
    actions->challenge_active = source->state == PE_SOURCE_SEEN_ARMED ||
                                source->state == PE_SOURCE_CLEAR_SEEN;
}

bool pe_source_clock_seen_reset(pe_source_t *source, uint64_t now_ms,
                                 pe_source_inputs_t inputs,
                                 pe_source_actions_t *actions) {
    pe_source_sample(source, now_ms, inputs, actions);
    if (source->state != PE_SOURCE_SEEN_ARMED ||
        !physical_disarmed(inputs) || now_ms >= source->deadline_ms) {
        abort_source(source, actions);
        return false;
    }
    source->state = PE_SOURCE_CLEAR_SEEN;
    actions->challenge_active = true;
    actions->seen_reset_pulse = true;
    return true;
}

bool pe_source_confirm_seen_reset(pe_source_t *source, uint64_t now_ms,
                                   pe_source_inputs_t inputs,
                                   pe_source_actions_t *actions) {
    pe_source_sample(source, now_ms, inputs, actions);
    if (source->state != PE_SOURCE_CLEAR_SEEN || !seen_cleared(inputs) ||
        now_ms >= source->deadline_ms) {
        abort_source(source, actions);
        return false;
    }
    source->state = PE_SOURCE_WAIT_READY;
    actions->challenge_active = false;
    send(actions, PE_DISARM_ACK, source->session, 0);
    return true;
}

void pe_source_frame(pe_source_t *source, pe_frame_t frame, uint64_t now_ms,
                     pe_source_inputs_t inputs, pe_source_actions_t *actions) {
    pe_source_sample(source, now_ms, inputs, actions);
    if (frame.type == PE_STOP || frame.type == PE_ABORT) {
        abort_source(source, actions);
        return;
    }
    if (source->state == PE_SOURCE_LOCKOUT) return;
    if (frame.type == PE_PREPARE_CHALLENGE) {
        if (source->state != PE_SOURCE_WAIT_CHALLENGE ||
            frame.session <= source->last_session ||
            frame.value != 0 || !physical_disarmed(inputs) ||
            !deadline(now_ms, source->config.prepare_window_ms,
                      &source->deadline_ms)) {
            abort_source(source, actions);
            return;
        }
        source->session = frame.session;
        source->last_session = frame.session;
        source->state = PE_SOURCE_SEEN_ARMED;
        actions->challenge_active = true;
        return;
    }
    if (frame.session != source->session || source->session == 0) {
        abort_source(source, actions);
        return;
    }
    switch (frame.type) {
    case PE_READY:
        if (source->state == PE_SOURCE_WAIT_READY && frame.value == 0 &&
            inputs.hot_session_q && !inputs.local_permit_q &&
            !inputs.hot_permit) {
            source->state = PE_SOURCE_READY;
            source->button_released = false;
            if (!link_progress(source, actions)) return;
            return;
        }
        break;
    case PE_ACK:
        if (source->state == PE_SOURCE_WAIT_ACK &&
            frame.value == source->intent &&
            now_ms < source->deadline_ms &&
            inputs.local_permit_q && inputs.hot_permit &&
            inputs.hot_session_q) {
            source->state = PE_SOURCE_START_SENT;
            if (!link_progress(source, actions)) return;
            send(actions, PE_START, source->session, source->intent);
            return;
        }
        break;
    case PE_PING:
        if (frame.value > source->last_peer_ping &&
            source->state >= PE_SOURCE_READY) {
            source->last_peer_ping = frame.value;
            if (!link_progress(source, actions)) return;
            send(actions, PE_PONG, source->session, frame.value);
            return;
        }
        break;
    case PE_PONG:
        if (frame.value != 0 && frame.value == source->awaiting_pong) {
            source->awaiting_pong = 0;
            if (!link_progress(source, actions)) return;
            return;
        }
        break;
    default:
        break;
    }
    abort_source(source, actions);
}

void pe_source_byte(pe_source_t *source, pe_stream_t *stream, uint8_t byte,
                    uint64_t now_ms, pe_source_inputs_t inputs,
                    pe_source_actions_t *actions) {
    pe_frame_t frame;
    pe_stream_result_t result =
        pe_stream_push_result(stream, byte, now_ms, &frame);
    if (result == PE_STREAM_FRAME) {
        pe_source_frame(source, frame, now_ms, inputs, actions);
        return;
    }
    pe_source_sample(source, now_ms, inputs, actions);
    if (result == PE_STREAM_ERROR) abort_source(source, actions);
}

void pe_source_stream_idle(pe_source_t *source, pe_stream_t *stream,
                           uint64_t now_ms, pe_source_inputs_t inputs,
                           pe_source_actions_t *actions) {
    bool expired = pe_stream_expire(stream, now_ms);
    pe_source_sample(source, now_ms, inputs, actions);
    if (expired) abort_source(source, actions);
}

void pe_source_local_progress(pe_source_t *source, uint32_t epoch) {
    if (source->state != PE_SOURCE_LOCKOUT && epoch > source->local_epoch) {
        source->local_epoch = epoch;
    }
}

bool pe_source_ping(pe_source_t *source, uint64_t now_ms,
                    pe_source_inputs_t inputs, pe_source_actions_t *actions) {
    pe_source_sample(source, now_ms, inputs, actions);
    if (source->state < PE_SOURCE_READY || source->awaiting_pong != 0 ||
        source->next_ping == UINT32_MAX) return false;
    source->awaiting_pong = ++source->next_ping;
    send(actions, PE_PING, source->session, source->awaiting_pong);
    return true;
}

void pe_source_stop(pe_source_t *source, pe_source_actions_t *actions) {
    uint64_t old_session = source->session;
    abort_source(source, actions);
    if (old_session != 0) send(actions, PE_STOP, old_session, 0);
}

bool pe_source_disarmed_for_restart(const pe_source_t *source,
                                    pe_source_inputs_t inputs) {
    return source->state == PE_SOURCE_LOCKOUT && physical_disarmed(inputs);
}
