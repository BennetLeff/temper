"""R2 process changes. Millimetres; selected dimensions are nominal, not qualification."""
from __future__ import annotations

from dataclasses import replace
from math import cos, sin, pi, radians

import cadquery as cq
import numpy as np

import baseline_engine as b

Part = b.Part
CAM_AMPLITUDE = 0.07
# Assembly setting: balance the two margins around the catalog 0.3mm stroke.
# R2 compression was 0.0310..0.1710; +0.049 moves it to 0.0800..0.2200.
# The combined ±0.05mm offset below is a DESIGN BUDGET, not supplier capability.
PLUNGER_FACE = 20.849
PLUNGER_OFFSET_BUDGET = 0.05
PLUNGER_END_MARGIN = 0.025
PLUNGER_LENGTH = 4.0
PLUNGER_BALL_R = 0.5
PLUNGER_STROKE = 0.3
CAM_SCREW_RADIUS = 23.6


def rotor_parts(angle: float, press: float) -> list[Part]:
    """Turned grip + 8mm profile-cut cam; three underside M2 countersunk screws."""
    shell=b.cyl(28,16,0,0,4).cut(b.cyl(26.4,10.1,0,0,3.9)).cut(b.cyl(21.3,4.5,0,0,14))
    shell=cq.Workplane(obj=shell).edges('>Z').fillet(1).val()
    for i in range(48):
        a=2*pi*i/48
        shell=shell.cut(b.cyl(1.2,10,28.8*cos(a),28.8*sin(a),6))
    hub=b.cyl(6,17.7,0,0,.8).cut(b.cyl(4.1,2.6,0,0,.7)).cut(b.ring(6.1,5.4,1.175,.85))
    shell=shell.fuse(hub).fuse(b.ring(14,7.5,14,4.5))
    bore=cq.Workplane('XY').workplane(offset=5.9).spline(b.kc.original.PROFILE.tolist(),periodic=True).close().extrude(8.2).val()
    cam=b.cyl(26.2,8,0,0,6).cut(bore)
    screws=[]
    for deg in (90,210,330):
        x,y=CAM_SCREW_RADIUS*cos(radians(deg)),CAM_SCREW_RADIUS*sin(radians(deg))
        cam=cam.cut(b.cyl(1.1,10,x,y,5)).cut(cq.Solid.makeCone(2.0,1.1,.9,cq.Vector(x,y,6)))
        shell=shell.cut(b.cyl(1.0,4.5,x,y,14))
        screw=b.cyl(.95,10.8,x,y,7.3).fuse(cq.Solid.makeCone(1.9,.7,1.2,cq.Vector(x,y,6.1)))
        screws.append(Part(f'cam_M2x12_countersunk_{deg}',screw,b.DARK,'knob','Accu SPK-M2-12-A4-BL DIN965Z candidate: M2x12, head3.8 max, k1.2, 90deg, PZ0. Simplified thread/drive; torque and availability unverified.'))
    raw=[Part('turned_aluminum_grip_56mm',shell.clean(),b.SILVER,'knob','6061-T6 candidate: turned steps/bore/hub, 3 underside blind M2 taps, edge grip texture; estimated two axial setups plus indexing, tool/fixture plan unverified.'),
         Part('replaceable_profile_cam_8mm',cam.clean(),(.23,.46,.59),'knob','8mm engineering-polymer plate candidate: 2.5D through profile, 3 holes/countersinks; no hidden pockets. Material, fit and wear need temperature/bench validation.')]+screws
    return [replace(p,shape=p.shape.rotate((0,0,0),(0,0,1),angle).translate((0,0,-press))) for p in raw]


def configure_cam() -> None:
    """Retain 24 detents, with travel compatible with the GN615-M2 nominal envelope."""
    original = b.kc.original
    original.PROFILE = np.array([
        [(21 + CAM_AMPLITUDE*cos(24*a))*cos(a),
         (21 + CAM_AMPLITUDE*cos(24*a))*sin(a)]
        for a in np.linspace(0, 2*pi, 769)[:-1]
    ])
    original.fixed_geometry.cache_clear()


def ball_center(angle: float) -> float:
    """Numerical inward contact against the sampled cam; rigid STEP checks follow."""
    a = radians(angle)
    rotation = np.array([[cos(a), -sin(a)], [sin(a), cos(a)]])
    points = b.kc.original.PROFILE @ rotation.T
    edges = np.roll(points, -1, axis=0) - points
    lo, hi = 20.0, 21.0
    for _ in range(48):
        mid = (lo + hi)/2
        delta = np.array([mid, 0.0]) - points
        t = np.clip(np.sum(delta*edges, axis=1)/np.sum(edges*edges, axis=1), 0, 1)
        distance = np.linalg.norm(delta-t[:, None]*edges, axis=1).min()
        if distance > PLUNGER_BALL_R + 0.001:
            lo = mid
        else:
            hi = mid
    return (lo + hi)/2


def knob(angle: float = 0, press: float = 0) -> list[Part]:
    parts = []
    omitted = ('keyed_split_guide_lid_', 'guide_lid_screw_',
               'rounded_radial_follower_', 'radial_detent_coil_')
    for p in b.knob(angle, press):
        if p.name == 'silver_rotor_integral_radial_cam':
            parts.extend(rotor_parts(angle,press))
            continue
        if p.name.startswith(omitted):
            continue
        if p.name == 'corrected_open_trough_shoe':
            shape = p.shape
            for deg in (0, 180):
                cut = b.box(6.8, 10, 8, 17.6, 0, 5).rotate((0,0,0),(0,0,1),deg)
                shape = shape.cut(cut)
                block = b.box(4.7, 4.0, 7.2, 18.15, 0, 5)
                bore = cq.Solid.makeCylinder(1.0, 5, cq.Vector(15.7,0,10.5), cq.Vector(1,0,0))
                block = block.cut(bore).rotate((0,0,0),(0,0,1),deg)
                shape = shape.fuse(block)
            p = replace(p, name='shoe_with_two_M2_plunger_bores', shape=shape.clean(),
                        evidence='Two radial M2 tapped bores; major-diameter thread envelopes, not pilot drill size. Machined engineering polymer candidate; heat/creep fit unqualified.')
        parts.append(p)
    center = ball_center(angle)
    for deg in (0, 180):
        body = cq.Solid.makeCylinder(1, PLUNGER_LENGTH,
            cq.Vector(PLUNGER_FACE-PLUNGER_LENGTH,0,10.5),cq.Vector(1,0,0))
        body = body.cut(cq.Solid.makeCylinder(.51,1.2,cq.Vector(PLUNGER_FACE-1.15,0,10.5),cq.Vector(1,0,0)))
        ball = cq.Solid.makeSphere(.5,cq.Vector(center,0,10.5),angleDegrees1=-90,angleDegrees2=90)
        for name, shape in [('body',body),('ball',ball)]:
            parts.append(Part(f'GN615_M2_KN_{deg}_{name}',shape.rotate((0,0,0),(0,0,1),deg),
                b.SILVER,'knob','Ganter GN615-M2-KN dimensional stand-in; M2x4, ball1, stroke0.3. R2.1 body-face radial setting20.849, nominal shoe-mouth projection0.349; set and lock against cam. Combined offset budget ±0.05mm, not a released supplier tolerance. Two solids represent one purchased assembly.'))
    return parts


def sensor(travel: float = 0) -> list[Part]:
    parts = []
    for p in b.sensor(travel):
        if p.name.startswith('glass_face_datum_pad_'):
            continue
        if p.name == 'body_with_independent_flange':
            # Extend the existing gland land to support a flat, replaceable annular shim.
            p = replace(p,shape=p.shape.fuse(b.ring(13,11.25,-6,1.85)).clean())
        elif p.name == 'insulating_guide':
            p = replace(p,shape=p.shape.cut(b.ring(5.1,4.6,-3.6,.4)),
                evidence='Turned upper OD relief Ø9.2 x0.4 clears formed cap lip at full travel; remaining radial guide wall1.4mm. End-stop/strength unqualified.')
        elif p.name == 'hollow_insulating_plunger_with_capture_groove':
            shape = p.shape.cut(b.ring(5.6,5.1,-2-travel,.6))
            p = replace(p,shape=shape,evidence='Head reduced to Ø10.2 for thicker cap; dielectric material/creep unqualified.')
        elif p.name == 'contact_cap_with_proposed_rolled_capture_lip':
            # Open cup before assembly: turn the bore; insert the head; form lower lip.
            shape = b.cyl(6,.35,0,0,.25-travel).fuse(b.ring(6,5.2,-2.25-travel,2.5))
            shape = shape.fuse(b.ring(6,4.8,-1.4-travel,1.65))
            shape = shape.fuse(b.ring(6,4.8,-2.25-travel,.2))
            shape = shape.cut(b.ring(6.1,5.8,-1.0-travel,.7))
            p = replace(p,name='contact_cap_thick_skirt_formed_lip',shape=shape.clean(),
                evidence='Ø12 stepped cup, 0.8mm skirt, 1.0mm groove-root wall, 0.35mm roof; lower lip formed AFTER insertion. Diaphragm bead retained. Forming, seal and thermal performance unqualified.')
        elif p.name == 'flex_diaphragm_ENVELOPE':
            p = replace(p,evidence='Existing diaphragm bead captured in groove now backed by 1mm wall. Custom elastomer/tooling, hot leakage and fatigue remain unqualified.')
        parts.append(p)
    parts.append(Part('glass_load_spreader_flat_annulus',b.ring(12.8,11.25,-4.15,.15),
        (.75,.72,.62),'sensor','Flat die-cut insulating shim candidate, 117mm² nominal area; preload, compound and glass contact remain unqualified.'))
    return parts


configure_cam()
