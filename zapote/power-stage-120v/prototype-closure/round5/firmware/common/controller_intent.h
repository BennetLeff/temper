#ifndef R5_CONTROLLER_INTENT_H
#define R5_CONTROLLER_INTENT_H
#include "energy_link.h"
/* Controller contract: REQUEST is emitted only after commissioned on-chip PWM
 * diagnostics pass. It is intent/diagnostics, not measured physical edge capture.
 * Dedicated STM hardware guards continue to dominate coil and RUN permissions. */
static inline bool r5_controller_diagnostics(const energy_link_receiver_t *r,const energy_link_packet_t *p,
                                             uint32_t ms,bool heartbeat)
{
 return p&&p->kind==ENERGY_LINK_COMMAND&&energy_link_fresh(r,ms)&&heartbeat&&!(p->flags&ENERGY_LINK_FAULT);
}
static inline bool r5_controller_intent(const energy_link_receiver_t *r,const energy_link_packet_t *p,
                                       uint32_t ms,bool heartbeat,bool request_wire)
{
 return r5_controller_diagnostics(r,p,ms,heartbeat)&&request_wire&&(p->flags&ENERGY_LINK_REQUEST);
}
#endif
