#include "isolation.h"

enum { PICKUP_US=73000, REPROVE_US=110000, PROOF_HOLD_US=50000, CLOSE_US=100000, OPEN_US=40000, STABLE_US=10000,
       AGE_US=2000, STEP_US=1000, TRANSFER_US=446458 };

static void enter(pc_controller *s, pc_state state, uint32_t now) {
    s->state=state; s->entered_us=now; s->stable=false;
    s->proof_low_seen=false;
    if (state==PC_FAULT) s->reset_armed=false;
}
static bool held(pc_controller *s, bool condition, uint32_t now) {
    if (!condition) { s->stable=false; return false; }
    if (!s->stable) { s->stable=true; s->stable_us=now; }
    return now-s->stable_us >= STABLE_US;
}
static void fault(pc_controller *s, uint32_t now) { enter(s, PC_FAULT, now); }

bool pc_decode_mirrors(const uint8_t slots[6], uint8_t *closed_mask) {
    if (slots[0]) return false;
    uint8_t mask=0;
    for (unsigned n=0;n<5;n++) {
        uint8_t allowed=(uint8_t)(1u<<n);
        if (slots[n+1] & (uint8_t)~allowed) return false;
        mask |= slots[n+1];
    }
    *closed_mask=mask;
    return true;
}

void pc_step(pc_controller *s, const pc_inputs *i) {
    const bool fresh=i->mirror_valid && i->now_us-i->mirror_us<=AGE_US;
    const bool start=i->start && !s->previous_start;
    const bool reset=i->reset && !s->previous_reset;
    s->previous_start=i->start; s->previous_reset=i->reset;
    s->out=(pc_outputs){0};
    if (s->initialized && (i->now_us-s->previous_us>STEP_US || i->now_us==s->previous_us))
        fault(s,i->now_us);
    s->initialized=true; s->previous_us=i->now_us;
    if (s->state==PC_FAULT) {
        const bool safe=!i->start && i->healthy && fresh && i->a_nc && i->b_nc &&
            i->source_released && i->bypass_released && i->discharged;
        if (!safe) s->reset_armed=false;
        if (safe && !i->reset) s->reset_armed=true;
        if (safe && reset && s->reset_armed) {
            s->reset_armed=false; enter(s,PC_OFF,i->now_us);
        }
        /* A new cold per-resistor POST token is still required by START. */
        return;
    }
    if (s->state!=PC_OFF && (!i->healthy || !fresh)) {
        fault(s,i->now_us); return;
    }
    /* Self-test must never energize a contact while a source contact is closed. */
    if (s->state>=PC_TEST_A_CLOSE && s->state<=PC_CONNECT &&
        (!i->source_released || !i->bypass_released || !i->discharged)) {
        fault(s,i->now_us); return;
    }
    if (s->state>=PC_PRECHARGE && s->state<=PC_REPROVE &&
        i->now_us-s->source_us>=TRANSFER_US) {
        fault(s,i->now_us); return;
    }
    if (s->state>=PC_REARM && s->state<=PC_RUN &&
        (!i->a_nc || !i->b_nc || !i->bypass_proven)) {
        fault(s,i->now_us); return;
    }
    if (s->state>=PC_TEST_A_CLOSE && s->state<=PC_RUN && !i->feedback_static) {
        fault(s,i->now_us); return;
    }
    uint32_t age=i->now_us-s->entered_us;
    switch(s->state) {
    case PC_OFF:
        if (start) {
            if (i->reset || !i->healthy || !fresh || !i->feedback_static || !i->a_nc || !i->b_nc ||
                !i->source_released || !i->bypass_released || !i->discharged ||
                !i->cold || !i->post_valid || i->post_token<=s->used_post) {
                fault(s,i->now_us); break;
            }
            s->used_post=i->post_token;
            enter(s,PC_TEST_A_CLOSE,i->now_us);
        }
        break;
    case PC_TEST_A_CLOSE:
        if (!i->b_nc || age>=CLOSE_US) fault(s,i->now_us);
        else if (held(s,!i->a_nc,i->now_us) && age>=PICKUP_US) enter(s,PC_TEST_A_OPEN,i->now_us);
        break;
    case PC_TEST_A_OPEN:
        if (!i->b_nc || age>=OPEN_US) fault(s,i->now_us);
        else if (held(s,i->a_nc,i->now_us)) enter(s,PC_TEST_B_CLOSE,i->now_us);
        break;
    case PC_TEST_B_CLOSE:
        if (!i->a_nc || age>=CLOSE_US) fault(s,i->now_us);
        else if (held(s,!i->b_nc,i->now_us) && age>=PICKUP_US) enter(s,PC_TEST_B_OPEN,i->now_us);
        break;
    case PC_TEST_B_OPEN:
        if (!i->a_nc || age>=OPEN_US) fault(s,i->now_us);
        else if (held(s,i->b_nc,i->now_us)) enter(s,PC_CONNECT,i->now_us);
        break;
    case PC_CONNECT:
        if (age>=CLOSE_US) fault(s,i->now_us);
        else if (held(s,!i->a_nc && !i->b_nc,i->now_us) && age>=PICKUP_US && i->feedback_static) {
            s->source_us=i->now_us; enter(s,PC_PRECHARGE,i->now_us);
        }
        break;
    case PC_PRECHARGE:
        if (i->a_nc || i->b_nc) fault(s,i->now_us);
        else if (i->precharge_complete) enter(s,PC_BYPASS,i->now_us);
        break;
    case PC_BYPASS:
        if (i->a_nc || i->b_nc) fault(s,i->now_us);
        /* The existing supervisor owns KB pickup and electrical proof stages;
         * this gate retains the global transfer deadline, not a new timer reset. */
        else if (i->bypass_proven) enter(s,PC_ISOLATE,i->now_us);
        break;
    case PC_ISOLATE:
        if (!i->bypass_proven || age>=OPEN_US) fault(s,i->now_us);
        else if (held(s,i->a_nc && i->b_nc,i->now_us)) enter(s,PC_REARM,i->now_us);
        break;
    case PC_REARM:
        /* Wrapper requires first KT edge +131433us, physical one-shot window
         * low and >=2ms low guard. Low command does not reset LTC6993-1. */
        if (i->proof_timer_ready) enter(s,PC_REPROVE,i->now_us);
        break;
    case PC_REPROVE:
        /* Reject a cached pre-isolation proof. The owner must begin a new
         * loaded KT measurement epoch, then hold fresh good evidence 50 ms. */
        if (!i->post_isolation_proven) s->proof_low_seen=true;
        if (age>=REPROVE_US) fault(s,i->now_us);
        else if (s->proof_low_seen && i->post_isolation_proven && age>=PROOF_HOLD_US)
            enter(s,PC_READY,i->now_us);
        break;
    case PC_READY:
        if (i->run_qualified) enter(s,PC_RUN,i->now_us);
        break;
    case PC_RUN:
        if (!i->run_qualified) fault(s,i->now_us);
        break;
    case PC_FAULT: break;
    }
    s->out.a=s->state==PC_TEST_A_CLOSE ||
        (s->state>=PC_CONNECT && s->state<=PC_BYPASS);
    s->out.b=s->state==PC_TEST_B_CLOSE ||
        (s->state>=PC_CONNECT && s->state<=PC_BYPASS);
    s->out.main=s->state>=PC_PRECHARGE && s->state<=PC_RUN;
    s->out.bypass=s->state>=PC_BYPASS && s->state<=PC_RUN;
    s->out.run=s->state==PC_RUN && fresh && i->a_nc && i->b_nc &&
        !s->out.a && !s->out.b && i->run_qualified;
}
