"""Folded Temper prototype study, mm. Provisional bend rules, not a cut release."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from math import atan2, cos, sin, tan, pi, hypot
import gzip
import hashlib
import json
import cadquery as cq

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT.parent / 'temper-inbox-cad'
T, RI, K = 2., 3., .42
RO = RI + T
W, D, TOP = 370., 440., 105.
FRONT_Z = TOP - 82 * tan(35*pi/180)
SILVER = (.73,.76,.75)

@dataclass(frozen=True)
class Part:
    name: str
    shape: cq.Shape
    color: tuple[float,float,float]
    group: str

@dataclass(frozen=True)
class Feature:
    segment: int
    u: float
    q: float
    width: float
    height: float
    radius: float = 0.
    kind: str = 'rect'


def box(w,d,h,x,y,z):
    return cq.Workplane('XY').box(w,d,h,centered=(True,True,False)).translate((x,y,z)).val()

def rr(w,d,h,r,x=0,y=0,z=0):
    solid=cq.Workplane('XY').box(w,d,h,centered=(True,True,False))
    if r: solid=solid.edges('|Z').fillet(r)
    return solid.translate((x,y,z)).val()

def cylinder(r,h,x,y,z):
    return cq.Solid.makeCylinder(r,h,cq.Vector(x,y,z))

def poly_yz(points, width=W):
    return cq.Workplane('YZ',origin=(-width/2,0,0)).polyline(points).close().extrude(width).val()

def rounded_path(points):
    tangents=[]; normals=[]; lengths=[]
    for a,b in zip(points,points[1:]):
        length=hypot(b[0]-a[0],b[1]-a[1]); d=((b[0]-a[0])/length,(b[1]-a[1])/length)
        tangents.append(d);normals.append((d[1],-d[0]));lengths.append(length)
    trims=[0.]*len(points);angles=[0.]*len(points)
    for i in range(1,len(points)-1):
        d0,d1=tangents[i-1],tangents[i]
        angle=atan2(d0[0]*d1[1]-d0[1]*d1[0],d0[0]*d1[0]+d0[1]*d1[1])
        assert angle<0
        angles[i]=-angle;trims[i]=RO*tan(-angle/2)
    solids=[];segments=[];bends=[];developed=0.
    for i,(a,b) in enumerate(zip(points,points[1:])):
        d,n=tangents[i],normals[i]
        start=(a[0]+trims[i]*d[0],a[1]+trims[i]*d[1])
        end=(b[0]-trims[i+1]*d[0],b[1]-trims[i+1]*d[1])
        straight=lengths[i]-trims[i]-trims[i+1]
        solids.append(poly_yz([start,end,(end[0]+T*n[0],end[1]+T*n[1]),(start[0]+T*n[0],start[1]+T*n[1])]))
        segments.append(dict(start=start,end=end,d=d,n=n,length=straight,flat_start=developed))
        developed+=straight
        if i<len(points)-2:
            center=(end[0]+RO*n[0],end[1]+RO*n[1]);a0=atan2(-n[1],-n[0]);a1=a0-angles[i+1]
            def p(radius,angle): return(center[0]+radius*cos(angle),center[1]+radius*sin(angle))
            profile=(cq.Workplane('YZ',origin=(-W/2,0,0)).moveTo(*p(RO,a0))
                     .threePointArc(p(RO,(a0+a1)/2),p(RO,a1)).lineTo(*p(RI,a1))
                     .threePointArc(p(RI,(a0+a1)/2),p(RI,a0)).close().extrude(W).val())
            solids.append(profile)
            allowance=(RI+K*T)*angles[i+1]
            bends.append(dict(angle_deg=angles[i+1]*180/pi,flat_center=developed+allowance/2,allowance=allowance))
            developed+=allowance
    shape=solids[0]
    for solid in solids[1:]:shape=shape.fuse(solid)
    return shape.clean(),segments,bends,developed


def cutter(feature,plane):
    local=cq.Workplane(plane).workplane(offset=1).center(feature.u,feature.q)
    if feature.kind=='circle': return local.circle(feature.width/2).extrude(-5).val()
    if feature.kind=='slot': return local.slot2D(feature.height,feature.width,90).extrude(-5).val()
    shape=rr(feature.width,feature.height,5,feature.radius)
    return shape.translate((feature.u,feature.q,-4)).located(cq.Location(plane))


def flat_cut(plate,feature,start=0):
    f=Feature(0,feature.u,feature.q+start,feature.width,feature.height,feature.radius,feature.kind)
    return plate.cut(cutter(f,cq.Plane(origin=(0,0,2))))


def bounds(shape):
    b=shape.BoundingBox();return [b.xmin,b.ymin,b.zmin,b.xmax,b.ymax,b.zmax]

def overlap(a,b):
    aa,bb=bounds(a),bounds(b)
    if any(aa[i+3]<=bb[i]+1e-7 or bb[i+3]<=aa[i]+1e-7 for i in range(3)):return 0.
    return a.intersect(b).Volume()

def main():
    parts=[]
    wrap,segments,bends,flat_length=rounded_path([(0,10.5),(0,FRONT_Z),(82,TOP),(D,TOP),(D,10.5)])
    flat=box(W,flat_length,T,0,flat_length/2,0)
    features=[Feature(1,-35,64-RO*tan(55*pi/360),108.8,38.8,4.4),
              Feature(2,0,261-segments[2]['start'][0],339.2,327.2,16.6)]
    features += [Feature(1,x,26-RO*tan(55*pi/360),diameter,diameter,kind='circle') for x,diameter in [(-75,12.6),(-35,12.6),(5,16.6)]]
    features += [Feature(2,x,y-segments[2]['start'][0],3.4,3.4,kind='circle') for x in(-174,174) for y in(140,380)]
    features += [Feature(3,-45+(i-8.5)*9,segments[3]['start'][1]-67,5,36,kind='slot') for i in range(18)]
    features += [Feature(3,135,segments[3]['start'][1]-34,34,24)]
    for f in features:
        seg=segments[f.segment];start=seg['start'];n=seg['n']
        plane=cq.Plane(origin=(0,*start),xDir=(1,0,0),normal=(0,-n[0],-n[1]))
        wrap=wrap.cut(cutter(f,plane))
        flat=flat_cut(flat,f,seg['flat_start'])
    # Shallow hand countersinks at the four top-cover screws, outside the glass.
    for x in(-174,174):
        for y in(140,380):
            wrap=wrap.cut(cq.Solid.makeCone(3.2,1.7,1.5,cq.Vector(x,y,105),cq.Vector(0,0,-1)))
    parts.append(Part('three_bend_front_top_rear_cover',wrap,SILVER,'cover'))

    # Bottom-and-side U: rounded 90-degree bends; side profile cut to clear cover.
    y0,y1=2.5,437.5
    base=box(360,y1-y0,2,0,220,8)
    def roof(y):return min(102.5,FRONT_Z+tan(35*pi/180)*y-3.5,102.5-max(0,y-434.5)*2/3)
    transition=(102.5-FRONT_Z+3.5)/tan(35*pi/180)
    for sign in(-1,1):
        side=cq.Workplane('YZ',origin=(183 if sign==1 else -185,0,0)).polyline([(y0,13),(y1,13),(y1,roof(y1)),(434.5,102.5),(transition,102.5),(y0,roof(y0))]).close().extrude(2).val()
        # Quarter annulus in XZ, extruded along Y. Explicit corner geometry.
        center=sign*180
        pts=lambda r,a:(center+r*cos(a),13+r*sin(a))
        a0,a1=(-pi/2,0) if sign==1 else(-pi,-pi/2)
        elbow=(cq.Workplane('XZ',origin=(0,y1,0)).moveTo(*pts(RO,a0)).threePointArc(pts(RO,(a0+a1)/2),pts(RO,a1))
               .lineTo(*pts(RI,a1)).threePointArc(pts(RI,(a0+a1)/2),pts(RI,a0)).close().extrude(y1-y0).val())
        base=base.fuse(side).fuse(elbow)
    ba90=(RI+K*T)*pi/2
    def wing(y):return ba90+roof(y)-13
    outline=[(-180-wing(y0),y0),(-180,y0),(180,y0),(180+wing(y0),y0),(180+wing(transition),transition),(180+wing(434.5),434.5),(180+wing(y1),y1),(-180-wing(y1),y1),(-180-wing(434.5),434.5),(-180-wing(transition),transition)]
    baseflat=cq.Workplane('XY').polyline(outline).close().extrude(2).val()
    for y in(301,312,323,334,345,356):
        hole=cq.Workplane('XY').workplane(offset=7).center(-45,y).slot2D(110,6).extrude(5).val()
        base=base.cut(hole)
        baseflat=baseflat.cut(hole.translate((0,0,-8)))
    # Simple fixed feet and a removable central service cover use laser-cut holes.
    baseholes=[(x,y,2) for x in(-145,145) for y in(38,404)] + [(-28,261,1.7),(28,261,1.7),(0,261,22)]
    for x,y,r in baseholes:
        base=base.cut(cylinder(r,5,x,y,7));baseflat=baseflat.cut(cylinder(r,5,x,y,-1))
    # Right probe port retained; no fixed connector part assumed.
    base=base.cut(cq.Solid.makeCylinder(6.5,6,cq.Vector(181,72,55),cq.Vector(1,0,0)))
    baseflat=baseflat.cut(cylinder(6.5,5,180+ba90+55-13,72,-1))
    for sign in(-1,1):
        for y in(140,380):
            base=base.cut(cq.Solid.makeCylinder(1.7,6,cq.Vector(sign*180,y+7,93),cq.Vector(sign,0,0)))
            baseflat=baseflat.cut(cylinder(1.7,5,sign*(180+ba90+93-13),y+7,-1))
    base=base.clean();parts.append(Part('two_bend_bottom_and_sides',base,(.66,.69,.69),'tray'))
    carrier=rr(358,346,2,18,0,261,97).cut(rr(326,314,5,10,0,261,96))
    for x in(-174,174):
        for y in(140,380): carrier=carrier.cut(cylinder(1.7,5,x,y,96))
    parts.append(Part('flat_glass_carrier_ring',carrier,(.51,.56,.55),'carrier'))
    carrierflat=carrier.translate((0,-88,-97))
    glass=rr(338,326,4,16,0,261,101).cut(cylinder(9,6,0,261,100))
    gasket=rr(338,326,2,16,0,261,99).cut(rr(326,314,4,10,0,261,98))
    parts += [Part('glass_338x326_with_center_aperture',glass,(.06,.085,.088),'glass'),Part('glass_bedding_ENVELOPE',gasket,(.15,.17,.16),'gasket')]
    for sign in(-1,1):
        for y in(140,380):
            x=sign*174
            # Nominal stock-angle envelope; source the actual extrusion before cutting.
            angle=box(12.7,24,1.6,sign*176.65,y,101.4).fuse(box(1.6,24,11.1,sign*182.2,y,90.3))
            angle=angle.cut(cylinder(1.7,8,x,y,96))
            angle=angle.cut(cq.Solid.makeCylinder(1.7,8,cq.Vector(sign*179,y+7,93),cq.Vector(sign,0,0)))
            parts.append(Part(f'stock_angle_mount_{sign}_{y}',angle,(.58,.62,.61),'mounts'))
            spacer=cylinder(3,2.4,x,y,99).cut(cylinder(1.7,4,x,y,98))
            parts.append(Part(f'washer_stack_2p4_ENVELOPE_{sign}_{y}',spacer,(.48,.51,.49),'mounts'))
            # Heads are appearance only; screws, nuts and preload not qualified.
            head=cq.Solid.makeCone(1.65,3.1,1.45,cq.Vector(x,y,103.55)).fuse(cylinder(3.1,.1,x,y,105))
            head=head.cut(box(.65,4,1,x,y,104.7))
            parts.append(Part(f'top_screw_head_ENVELOPE_{sign}_{y}',head,(.54,.59,.58),'hardware'))
            headside=cq.Solid.makeCylinder(2.8,1.8,cq.Vector(sign*185,y,95),cq.Vector(sign,0,0))
            parts.append(Part(f'side_screw_head_ENVELOPE_{sign}_{y}',headside,(.50,.55,.53),'hardware'))
    cover=cylinder(32,2,0,261,6)
    for x in(-28,28):cover=cover.cut(cylinder(1.7,4,x,261,5))
    parts.append(Part('sensor_service_cover',cover,(.35,.38,.37),'tray'))
    for x in(-145,145):
        for y in(38,404):parts.append(Part(f'foot_{x}_{y}',cylinder(11,8,x,y,0),(.09,.11,.10),'feet'))

    return parts, {"cover":flat,"tray":baseflat,"glass-carrier":carrierflat}, segments, bends, flat_length
