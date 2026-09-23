#include "receiver.h"

#include <limits.h>
#include <string.h>

static void actions_reset(pe_receiver_t *receiver, pe_receiver_actions_t *actions) {
    memset(actions, 0, sizeof(*actions));
    actions->abort_n = receiver->abort_n;
}

static void abort_session(pe_receiver_t *receiver, pe_receiver_actions_t *actions) {
    receiver->abort_n = false;
    receiver->state = PE_RX_LOCKOUT;
    receiver->session = 0;
    receiver->intent = 0;
    receiver->awaiting_pong = 0;
    receiver->revalidation_issued = false;
    actions_reset(receiver, actions);
}

static bool deadline(uint64_t now, uint32_t window, uint64_t *result) {
    if (UINT64_MAX - now < window) return false;
    *result = now + window;
    return true;
}

static bool common_healthy(pe_receiver_inputs_t inputs) {
    return inputs.rail_good && !inputs.fault && !inputs.preparation_abort;
}

static bool current_session_valid(pe_receiver_inputs_t inputs) {
    return common_healthy(inputs) && inputs.session_q;
}

static void send(pe_receiver_actions_t *actions, pe_frame_type_t type,
                 uint64_t session, uint32_t value) {
    actions->transmit = true;
    actions->frame.type = type;
    actions->frame.session = session;
    actions->frame.value = value;
}

void pe_receiver_init(pe_receiver_t *receiver, pe_receiver_config_t config) {
    memset(receiver, 0, sizeof(*receiver));
    receiver->config = config;
    receiver->state = PE_RX_LOCKOUT;
    /* Invalid config remains permanently locked out. */
}

void pe_receiver_sample(pe_receiver_t *receiver, uint64_t now_ms,
                        pe_receiver_inputs_t inputs, pe_receiver_actions_t *actions) {
    actions_reset(receiver, actions);
    if (now_ms < receiver->now_ms) {
        receiver->clock_fault = true;
        abort_session(receiver, actions);
        return;
    }
    receiver->now_ms = now_ms;
    if (receiver->state == PE_RX_LOCKOUT) return;
    if (!common_healthy(inputs) ||
        (receiver->state >= PE_RX_READY && !inputs.session_q) ||
        (receiver->state >= PE_RX_START_PENDING && !inputs.physical_permit) ||
        (receiver->state == PE_RX_RUNNING && !inputs.run_q) ||
        ((receiver->state == PE_RX_READY ||
          receiver->state == PE_RX_START_PENDING) && inputs.run_q) ||
        (receiver->state == PE_RX_PREPARING &&
         (inputs.physical_permit || inputs.run_q ||
          (!receiver->revalidation_issued && inputs.session_q))) ||
        (receiver->state == PE_RX_PREPARING &&
         now_ms >= receiver->prepare_deadline_ms) ||
        (receiver->state == PE_RX_START_PENDING &&
         now_ms >= receiver->start_deadline_ms) ||
        (receiver->state == PE_RX_RUN_CONFIRM &&
         now_ms >= receiver->start_deadline_ms) ||
        (receiver->abort_n &&
         now_ms - receiver->last_wdi_ms >= receiver->config.watchdog_window_ms)) {
        abort_session(receiver, actions);
        return;
    }
    if (receiver->state == PE_RX_PREPARING && receiver->revalidation_issued &&
        inputs.session_q) {
        receiver->state = PE_RX_READY;
        send(actions, PE_READY, receiver->session, 0);
    } else if (receiver->state == PE_RX_RUN_CONFIRM && inputs.run_q) {
        receiver->state = PE_RX_RUNNING;
    }
    if (receiver->abort_n && receiver->local_epoch != receiver->local_fed &&
        receiver->link_epoch != receiver->link_fed) {
        receiver->local_fed = receiver->local_epoch;
        receiver->link_fed = receiver->link_epoch;
        receiver->last_wdi_ms = now_ms;
        actions->wdi_falling_pulse = true;
    }
    actions->abort_n = receiver->abort_n;
}

bool pe_receiver_begin(pe_receiver_t *receiver, const pe_journal_io_t *journal,
                       uint64_t now_ms, pe_receiver_inputs_t inputs,
                       pe_receiver_actions_t *actions) {
    pe_receiver_sample(receiver, now_ms, inputs, actions);
    if (receiver->state != PE_RX_LOCKOUT || !common_healthy(inputs) ||
        receiver->clock_fault || receiver->storage_fault ||
        inputs.physical_permit || inputs.session_q || inputs.run_q ||
        !inputs.disarm_seen || receiver->config.prepare_window_ms == 0 ||
        receiver->config.start_window_ms == 0 ||
        receiver->config.watchdog_window_ms == 0 ||
        !deadline(now_ms, receiver->config.prepare_window_ms,
                  &receiver->prepare_deadline_ms)) return false;
    uint64_t id;
    if (!pe_journal_reserve(journal, &id)) {
        receiver->storage_fault = true;
        return false;
    }
    receiver->state = PE_RX_PREPARING;
    receiver->session = id;
    receiver->intent = 0;
    receiver->revalidation_issued = false;
    receiver->next_ping = 0;
    receiver->awaiting_pong = 0;
    receiver->local_epoch = receiver->local_fed = 0;
    receiver->link_epoch = receiver->link_fed = 0;
    send(actions, PE_PREPARE_CHALLENGE, id, 0);
    return true;
}

void pe_receiver_frame(pe_receiver_t *receiver, pe_frame_t frame,
                       uint64_t now_ms, pe_receiver_inputs_t inputs,
                       pe_receiver_actions_t *actions) {
    pe_receiver_sample(receiver, now_ms, inputs, actions);
    if (frame.type == PE_STOP || frame.type == PE_ABORT) {
        abort_session(receiver, actions);
        return;
    }
    if (receiver->state == PE_RX_LOCKOUT) return;
    if (frame.session != receiver->session) {
        abort_session(receiver, actions);
        return;
    }
    switch (frame.type) {
    case PE_DISARM_ACK:
        if (receiver->state != PE_RX_PREPARING || frame.value != 0 ||
            !common_healthy(inputs) || inputs.physical_permit ||
            inputs.session_q || inputs.run_q || !inputs.disarm_seen ||
            receiver->revalidation_issued) break;
        receiver->abort_n = true;
        receiver->last_wdi_ms = now_ms;
        receiver->revalidation_issued = true;
        actions->abort_n = true;
        actions->revalidate_pulse = true;
        return;
    case PE_REQUEST:
        if (receiver->state != PE_RX_READY || frame.value == 0 ||
            !current_session_valid(inputs) || !inputs.physical_permit ||
            inputs.run_q ||
            !deadline(now_ms, receiver->config.start_window_ms,
                      &receiver->start_deadline_ms)) break;
        receiver->state = PE_RX_START_PENDING;
        receiver->intent = frame.value;
        send(actions, PE_ACK, receiver->session, receiver->intent);
        return;
    case PE_START:
        if (receiver->state != PE_RX_START_PENDING ||
            frame.value != receiver->intent ||
            now_ms >= receiver->start_deadline_ms ||
            !current_session_valid(inputs) || !inputs.physical_permit ||
            inputs.run_q) break;
        receiver->state = PE_RX_RUN_CONFIRM;
        actions->run_set_pulse = true;
        return;
    case PE_PING:
        if (frame.value == 0) break;
        send(actions, PE_PONG, receiver->session, frame.value);
        return;
    case PE_PONG:
        if (receiver->awaiting_pong == 0 ||
            frame.value != receiver->awaiting_pong ||
            receiver->link_epoch == UINT32_MAX) break;
        receiver->awaiting_pong = 0;
        ++receiver->link_epoch;
        return;
    default:
        break;
    }
    abort_session(receiver, actions);
}

void pe_receiver_local_progress(pe_receiver_t *receiver, uint32_t epoch) {
    if (receiver->state != PE_RX_LOCKOUT && epoch > receiver->local_epoch) {
        receiver->local_epoch = epoch;
    }
}

bool pe_receiver_ping(pe_receiver_t *receiver, uint64_t now_ms,
                      pe_receiver_inputs_t inputs,
                      pe_receiver_actions_t *actions) {
    pe_receiver_sample(receiver, now_ms, inputs, actions);
    if (!receiver->abort_n || receiver->state == PE_RX_LOCKOUT ||
        receiver->awaiting_pong != 0 || receiver->next_ping == UINT32_MAX) {
        return false;
    }
    receiver->awaiting_pong = ++receiver->next_ping;
    send(actions, PE_PING, receiver->session, receiver->awaiting_pong);
    return true;
}
