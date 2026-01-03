import jax.numpy as jnp
from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.extraction.hypergraph_factory import netlist_to_hypergraph
from temper_placer.routing.bridge.api import get_routing_context
from temper_placer.routing.bridge.types import RoutingStrategy, ZoneConflictType

def test_bridge_inference():
    # 1. Setup Board with zones
    # HV_ZONE: Y > 100, LV only
    # LV_ZONE: Y < 50,  LV only
    board = Board(
        width=100, height=150,
        zones=[
            Zone("HV_ZONE", (0, 100, 100, 150), net_classes=["HighVoltage"]),
            Zone("LV_ZONE", (0, 0, 100, 50), net_classes=["Signal"]),
        ]
    )
    
    # 2. Setup Netlist
    # J_AC_IN is in HV_ZONE but connected to GND (Signal)
    j_ac_in = Component(
        ref="J_AC_IN", footprint="CONN", bounds=(10, 10),
        pins=[Pin(name="GND", number="1", position=(0, 0), net="GND")]
    )
    
    # MCU is in LV_ZONE
    u_mcu = Component(
        ref="U_MCU", footprint="MCU", bounds=(10, 10),
        pins=[Pin(name="GND", number="1", position=(0, 0), net="GND")]
    )
    
    # PGND net - high current
    pgnd_net = Net(name="PGND", pins=[("J_AC_IN", "2"), ("U_MCU", "2")], max_current=40.0, net_class="Power")
    
    # GND net - signal, but enters HV zone via J_AC_IN
    gnd_net = Net(name="GND", pins=[("J_AC_IN", "1"), ("U_MCU", "1")], net_class="Signal")
    
    # Update components to have second pin
    j_ac_in = Component(
        ref="J_AC_IN", footprint="CONN", bounds=(10, 10),
        pins=[
            Pin(name="GND", number="1", position=(0, 0), net="GND"),
            Pin(name="PGND", number="2", position=(1, 1), net="PGND")
        ]
    )
    
    u_mcu = Component(
        ref="U_MCU", footprint="MCU", bounds=(10, 10),
        pins=[
            Pin(name="GND", number="1", position=(0, 0), net="GND"),
            Pin(name="PGND", number="2", position=(1, 1), net="PGND")
        ]
    )
    
    netlist = Netlist(components=[j_ac_in, u_mcu], nets=[gnd_net, pgnd_net])
    
    # 3. Placement Positions
    # J_AC_IN at (10, 125) -> HV_ZONE
    # U_MCU at (50, 25) -> LV_ZONE
    positions = jnp.array([
        [10.0, 125.0],
        [50.0, 25.0]
    ])
    
    # 4. Build Hypergraph
    hg = netlist_to_hypergraph(netlist)
    
    # 5. Run Bridge Analysis
    context = get_routing_context(hg, positions, board, netlist)
    
    # 6. Assertions
    
    # GND should have EDGE_HUG because J_AC_IN is in HV_ZONE but GND is Signal
    assert context.get_strategy("GND") == RoutingStrategy.EDGE_HUG
    
    # PGND should have FLOOD_FILL because max_current=40.0 > 2.0
    assert context.get_strategy("PGND") == RoutingStrategy.FLOOD_FILL
    
    # Verify conflicts record
    assert len(context.conflicts) > 0
    gnd_conflict = [c for c in context.conflicts if c.net_id == "GND"][0]
    assert gnd_conflict.conflict_type == ZoneConflictType.LV_NET_IN_HV_ZONE
    assert "J_AC_IN" in gnd_conflict.pin_id

if __name__ == "__main__":
    test_bridge_inference()
