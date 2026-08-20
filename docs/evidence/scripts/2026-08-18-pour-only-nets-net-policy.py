#!/usr/bin/env python3
# provenance: commit=2abb246db697da2685a652b93632a42d11595d51 dirty=false
from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS, TEMPER_NET_CLASSES
from temper_placer.router_v6._net_policy import _should_route
from temper_placer.router_v6._zone_pour_stitch import (
    _zone_layers_for_net, _CONTINUITY_EXEMPT_CLASSES, _CONTINUITY_EXEMPT_NETS,
    _zone_params_for_net,
)
from temper_placer.router_v6.net_classification import is_power_net, is_ground_net, is_hv_net

NINE = ["+170V_BUS","DC_BUS_RTN","PWR_RTN","SW_NODE","ac_n","power_in.ntc-no",
        "tank.c_tank1-p2","w1_1","w1_2"]
print(f"{'net':22} {'class':18} {'strategy':16} {'zone_layers':30} {'should_route':5} {'exempt':6} {'pwr/gnd/hv'}")
for n in NINE:
    nc = TEMPER_NET_ASSIGNMENTS.get(n,"<none>")
    r = TEMPER_NET_CLASSES.get(nc)
    strat = r.routing_strategy if r else "<none>"
    zl = _zone_layers_for_net(n)
    ex = (nc in _CONTINUITY_EXEMPT_CLASSES) or (n in _CONTINUITY_EXEMPT_NETS)
    flags = f"{int(is_power_net(n))}{int(is_ground_net(n))}{int(is_hv_net(n))}"
    print(f"{n:22} {nc:18} {str(strat):16} {str(zl):30} {str(_should_route(n)):5} {str(ex):6} {flags}  params={_zone_params_for_net(n)}")
print()
print("ALL netclasses:")
for nc, r in sorted(TEMPER_NET_CLASSES.items()):
    print(f"  {nc:20} strategy={r.routing_strategy!s:18} dru_priority={r.dru_priority} width={getattr(r,'trace_width',None)} clearance={getattr(r,'clearance',None)}")
