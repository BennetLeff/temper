"""Flat-cut support and replaceable tube legs; no stiffness/thermal qualification."""
from __future__ import annotations
from math import atan2, degrees, hypot, cos, sin, radians
import cadquery as cq
import baseline_engine as b

LEGS = [(x,y) for x in (-157.,157.) for y in (190.,330.)]


def build() -> list[b.Part]:
    plate = b.ring(104,19.2,85,3,0,261)
    for x,y in LEGS:
        length = hypot(x,y-261)
        arm = b.box(length-70,20,3,(length+70)/2,0,85)
        arm = arm.rotate((0,0,0),(0,0,1),degrees(atan2(y-261,x))).translate((0,261,0))
        plate = plate.fuse(arm).fuse(b.cyl(10,3,x,y,85))
    for x,y in LEGS:
        plate = plate.cut(b.cyl(2.2,5,x,y,84))
    result = [b.Part('coil_support_flat_routed_plate',plate.clean(),(.55,.61,.49),'support',
        '3mm insulating laminate candidate: profile + through holes only. Laminate temperature/EM/load suitability and deflection UNVERIFIED.')]
    spacer = b.ring(19.1,12.1,86,2,0,261)
    adapter = b.ring(21.8,12.1,88,3,0,261)
    for deg in (0,120,240):
        x,y=15*cos(radians(deg)),261+15*sin(radians(deg))
        spacer=spacer.cut(b.cyl(1.45,8,x,y,85))
        adapter=adapter.cut(b.cyl(1.45,8,x,y,85))
        # Existing M2.5x8 shaft ends at z91; use M2.5x12 to engage top nut.
        screw=b.cyl(1.25,12,x,y,83).fuse(b.cyl(2.25,2.5,x,y,80.5))
        result += [b.Part(f'sensor_mount_M2p5x12_{deg}',screw,b.DARK,'hardware','M2.5x12 nominal thread envelope'),
                   b.Part(f'sensor_adapter_M2p5_nut_{deg}',b.hexnut(x,y,91,5,2,1.3),b.DARK,'hardware','M2.5 nut nominal envelope; retention/torque unselected')]
    result += [b.Part('sensor_support_flat_spacer_2mm',spacer,(.60,.64,.55),'support','Flat insulating laminate spacer; OD locates within plate hole with 0.1mm radial nominal clearance.'),
               b.Part('sensor_support_flat_adapter_3mm',adapter,(.60,.64,.55),'support','Flat insulating laminate annulus, bolted through sensor flange; bears on main support.')]
    for x,y in LEGS:
        result.append(b.Part(f'leg_tube_12OD_8ID_75_{x}_{y}',b.ring(6,4,10,75,x,y),b.SILVER,'support','Saw-cut tube 12OD/8ID, length75; grade and cut tolerance pending supplier.'))
        screw=b.cyl(1.95,90,x,y,7.2).fuse(b.cyl(3.5,4,x,y,3.2))
        result += [b.Part(f'leg_M4x90_{x}_{y}',screw,b.DARK,'hardware','M4x90 nominal socket screw; thread/drive not modeled'),
                   b.Part(f'leg_lower_washer_{x}_{y}',b.ring(6,2.15,7.2,.8,x,y),b.SILVER,'hardware','M4 washer OD12 ID4.3 t0.8'),
                   b.Part(f'leg_top_washer_{x}_{y}',b.ring(6,2.15,88,.8,x,y),b.SILVER,'hardware','M4 washer OD12 ID4.3 t0.8'),
                   b.Part(f'leg_M4_nut_{x}_{y}',b.hexnut(x,y,88.8,7,3.2,2.0),b.DARK,'hardware','M4 nut envelope; clamp load and locking method unqualified')]
    return result
