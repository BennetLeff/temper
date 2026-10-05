"""R4 flush front with hidden carrier. mm. Nominal sealing architecture, not hot/oil qualification."""
from __future__ import annotations
from dataclasses import replace
import cadquery as cq
import baseline_engine as b

X,Y=-35.,50.
DISPLAY_Y=64.
BUTTONS=[(-75.,'BACK',6.),(-35.,'SELECT / START',6.),(5.,'STOP',8.)]
MOUNTS=[(X+x,Y+y) for x in (-64.,64.) for y in(-33.,0.,33.)]
SILVER=b.SILVER;BLACK=(.08,.10,.11);SEAL=(.68,.38,.22);GREEN=(.20,.38,.28)

def rr(w,h,t,r,x=X,y=Y,z=0):return b.base.rr(w,h,t,r,x,y,z)
def ring_rect(wo,ho,wi,hi,z,t,x=X,y=Y,ro=4.,ri=2.):
    return rr(wo,ho,t,ro,x,y,z).cut(rr(wi,hi,t+2,ri,x,y,z-1))
def world(s):return s.rotate((0,0,0),(1,0,0),35).translate((0,0,b.base.FRONT_Z))
def text_shape(text,size,x,y,z):
    return cq.Workplane('XY').text(text,size,.015,font='Arial',halign='center',valign='center').val().translate((x,y,z))

def build():
    parts=[]
    def add(name,shape,color=SILVER,evidence='Custom prototype geometry; dimensions not released',envelope=False):
        parts.append(b.Part('front_'+name,shape,color,'front_panel',evidence,envelope))
    # The 2mm formed aluminum itself is the visible front; no separate bezel.
    add('flush_lens_108x38x2',rr(108,38,2,4,X,DISPLAY_Y,-2),(.08,.11,.12),
        'Flush at local Z=0. Nominal 0.4mm perimeter joint. Glass grade, edge finish, impact and thermal shock unqualified.')
    add('lens_perimeter_seal_ALLOCATION',ring_rect(108.8,38.8,108,38,-2,2,X,DISPLAY_Y,4.4,4),BLACK,
        '0.4mm nominal flush-filled perimeter joint. Compound, adhesion and thermal movement unqualified.',True)
    add('lens_rear_support_ring',ring_rect(118,48,100,30,-3.5,1.2,X,DISPLAY_Y,6,3),SILVER,
        'Flat 1.2mm support ring bonded behind sheet and glass. Supports inward loads; outward retention depends on qualified bond. Separate from removable electronics.')
    add('lens_rear_bondline_ALLOCATION',ring_rect(118,48,100,30,-2.3,.3,X,DISPLAY_Y,6,3),SEAL,
        '0.3mm adhesive allocation joining ring to both glass and aluminum. Flush assembly needs an exterior datum jig. No adhesive or bond-strength claim.',True)
    plate=rr(154,88,2,6,z=-6.5).cut(rr(102,34,5,3,X,DISPLAY_Y,-7))
    for x,label,r in BUTTONS:plate=plate.cut(b.cyl(r+1,5,x,26,-7))
    for x,y in MOUNTS:plate=plate.cut(b.cyl(1.7,5,x,y,-7))
    walls=ring_rect(144,82,140,78,-26,19.5)
    carrier=plate.fuse(walls)
    # Rear cover bosses intersect side walls at the corners; local pad seals around screw holes.
    lid_mounts=[(X+x,Y+y) for x in(-68.,68.) for y in(-37.,37.)]
    for x,y in lid_mounts:carrier=carrier.fuse(b.cyl(4,8,x,y,-26).cut(b.cyl(1.5,8,x,y,-26)))
    # Display supported from front carrier with insulating posts, not a floating OLED.
    for dx in(-41.6,41.6):
        for dy in(-19.,19.):
            x,y=X+dx,DISPLAY_Y+dy
            post=b.ring(2.4,1.0,-8.5,2.0,x,y)
            carrier=carrier.fuse(post)
            carrier=carrier.cut(b.cyl(1,3.3,x,y,-8.5))
    # UI button-board mounting posts.
    for x in(X-50,X+50):
        for y in(17.,35.):
            carrier=carrier.fuse(b.ring(2.5,1.0,-10.4,3.9,x,y))
            carrier=carrier.cut(b.cyl(1,4.9,x,y,-10.4))
    # One right-facing cable passage. Feedthrough below is a procurement envelope.
    hole=cq.Solid.makeCylinder(6,10,cq.Vector(X+66,40,-18),cq.Vector(1,0,0))
    carrier=carrier.cut(hole).clean()
    add('carrier_and_closed_sidewalls',carrier,BLACK,'Machined insulating-polymer candidate; cold printed fit trial first. Six internally bonded stud bases; rear-service lid; four OLED posts at83.2x38 pitch. Electrical/thermal/flame/cleaner properties and creep unselected.')
    for x,y in MOUNTS:
        add(f'stud_base_bond_{x}_{y}',b.cyl(5,.3,x,y,-2.3),SEAL,
            'Bonded-stud base adhesive,0.3mm. Exact adhesive, surface preparation and hot pull/creep strength unqualified.',True)
        base=b.cyl(5,1.7,x,y,-4).fuse(b.cyl(1.45,7,x,y,-11))
        add(f'concealed_M3_stud_{x}_{y}',base,evidence='Nominal bonded mounting-pad/stud envelope,10mm base. No penetration of visible sheet. Supplier, attachment strength and locking unselected.')
        add(f'carrier_standoff_{x}_{y}',b.ring(3,1.7,-4.5,.5,x,y),evidence='0.5mm spacer fixes carrier front at -4.5; stack tolerance unqualified.')
        add(f'carrier_washer_{x}_{y}',b.ring(3.2,1.6,-7,.5,x,y),evidence='M3 washer envelope.')
        add(f'carrier_M3_nut_{x}_{y}',b.hexnut(x,y,-9.4,5.5,2.4,1.5),evidence='M3 nut envelope; accessible from inside before body assembly. Locking and torque unselected.')
    # All three buttons share one continuous membrane behind the sheet.
    membrane=rr(116,26,.8,3,X,26,-2.8).fuse(ring_rect(116,26,108,18,-4.5,1.7,X,26,3,2))
    for x,label,r in BUTTONS:
        membrane=membrane.fuse(b.cyl(r,2,x,26,-2)).fuse(b.cyl(2.5,2,x,26,-4.8))
    add('three_button_continuous_membrane_INSTALLED',membrane.clean(),BLACK,
        'Flush button tops Z=0;0.8mm web behind sheet.2.5mm installed perimeter stack from3.125mm free allocation. Force, return, overtravel, oil/heat and seal behavior unqualified.',True)
    for x,label,r in BUTTONS:add('label_'+label.replace(' / ','_'),text_shape(label,2.5,x,14,.01),(.12,.15,.14),'Marking illustration on continuous aluminum; no physical relief.',True)
    # Real module mounting geometry from Newhaven rev7 drawing, conservative decomposed envelope.
    board=b.box(89.2,44,1,X,DISPLAY_Y,-9.5)
    for dx in(-41.6,41.6):
        for dy in(-19.,19.):board=board.cut(b.cyl(1.25,3,X+dx,DISPLAY_Y+dy,-10))
    add('NHD_3p12_25664UCW2_PCB_ENVELOPE',board,GREEN,'Newhaven rev7 2024-08-25 drawing:89.2x44 PCB,4xØ2.5,83.2x38 pitch;1mm board. Module total6max. Envelope, not vendor STEP.',True)
    add('NHD_display_bezel_ENVELOPE',b.box(89,29.6,2.5,X,DISPLAY_Y-.6,-8.5),(.035,.045,.05),'Candidate module front bezel89x29.6 offset0.6mm from PCB center; physical thickness allocation within6mm module envelope.',True)
    add('NHD_rear_components_KEEPOUT',b.box(80,28,2.5,X,DISPLAY_Y,-12),GREEN,'Conservative rear-component allocation; verify all component heights against purchased module.',True)
    for dx in(-41.6,41.6):
        for dy in(-19.,19.):
            x,y=X+dx,DISPLAY_Y+dy
            screw=b.cyl(.95,4,x,y,-9.5).fuse(b.cyl(1.8,1.2,x,y,-10.7))
            add(f'OLED_M2x4_rear_{dx}_{dy}',screw,evidence='Rear-inserted M2x4 envelope;1mm PCB+3mm nominal post engagement; torque and threaded insert material open.')
    # Header routing allocation separated from components. Hole pattern at top y=19.5.
    add('OLED_header_and_bend_KEEPOUT',b.box(52,5,8,X,DISPLAY_Y+19.5,-18),(.44,.35,.19),'1x20 at2.54mm pitch; rear-facing header/harness allocation. Actual connector/bend radius not selected.',True)
    buttons_board=b.box(112,24,1.6,X,26,-12)
    for x in(X-50,X+50):
        for y in(17.,35.):buttons_board=buttons_board.cut(b.cyl(1.2,4,x,y,-13))
    add('button_PCB_ENVELOPE',buttons_board,GREEN,'Custom low-voltage button PCB allocation112x24x1.6. No PCB implementation or switch selection in this CAD.',True)
    for x,label,r in BUTTONS:
        add('switch_'+label.replace(' / ','_')+'_ENVELOPE',b.box(6,6,4,X+(x-X),26,-10.4).fuse(b.cyl(1.5,1.4,x,26,-6.4)),GREEN,'Unselected switch allocation.0.2mm rest gap to membrane pusher; operating/overtravel/force not validated.',True)
    for x in(X-50,X+50):
        for y in(17.,35.):add(f'button_board_M2x6_{x}_{y}',b.cyl(.95,6,x,y,-12).fuse(b.cyl(1.8,1.2,x,y,-13.2)),evidence='M2x6 rear-inserted envelope; actual switch-board assembly needs tolerance/overtravel design.')
    lid=rr(146,84,2,5,z=-29)
    gasket=ring_rect(144,82,140,78,-27,1)
    for x,y in lid_mounts:
        lid=lid.cut(b.cyl(1.7,5,x,y,-30))
        gasket=gasket.fuse(b.ring(4,1.7,-27,1,x,y))
        # Stops are part of the body and pass through pad seal clearance.
        # The thin wall seam still needs real compound and leak testing.
        stop=b.ring(2,1.5,-27,1,x,y)
        add(f'lid_compression_stop_{x}_{y}',stop,BLACK,'1mm rear gasket stop; fit retained by cover bolt, not bonded.')
        gasket=gasket.cut(b.cyl(2.05,3,x,y,-28))
        add(f'lid_M3x10_{x}_{y}',b.cyl(1.45,10,x,y,-29.5).fuse(b.cyl(2.75,3,x,y,-32.5)),evidence='M3x10 simplified envelope; rear screw penetration needs qualified sealing washer.')
        add(f'lid_sealing_washer_{x}_{y}',b.ring(3.2,1.5,-29.5,.5,x,y),SEAL,'Bonded-seal washer installed envelope; compound and tightening specification not selected.',True)
    add('rear_lid',lid,BLACK,'Flat2mm removable rear lid. Repeated service and gasket compression require validation.')
    add('rear_lid_gasket_INSTALLED',gasket.clean(),SEAL,'1.25mm free ->1mm installed,20% target. Narrow2mm wall land is a prototype constraint requiring leak/process review.',True)
    gland=cq.Solid.makeCylinder(5.8,8,cq.Vector(X+68,40,-18),cq.Vector(1,0,0)).fuse(cq.Solid.makeCylinder(8,3,cq.Vector(X+72,40,-18),cq.Vector(1,0,0)))
    gland=gland.cut(cq.Solid.makeCylinder(2,12,cq.Vector(X+66,40,-18),cq.Vector(1,0,0)))
    add('side_cable_feedthrough_ENVELOPE',gland,BLACK,'M12-class feedthrough allocation only. Actual gland, thread, wall seal, cable diameter, strain relief and hot-oil rating unselected.',True)
    add('cable_ENVELOPE',cq.Solid.makeCylinder(2,24,cq.Vector(X+61,40,-18),cq.Vector(1,0,0)),(.35,.25,.16),'4mm OD cable route allocation; conductor count and bend/strain relief unselected.',True)
    # Display artwork only: actual pixels must be generated by firmware.
    add('readout_artwork',text_shape('SET 180 C',5.5,X,DISPLAY_Y+3,.015),(.90,.92,.83),'Surface illustration only; not physical relief or implemented firmware.',True)
    return parts


def exploded(parts):
    result=[]
    for p in parts:
        n=p.name;dz=0
        if 'label_' in n or n=='front_face_excerpt':dz=14
        elif any(k in n for k in ['flush_lens','lens_perimeter','lens_rear','readout_artwork']):dz=14
        elif 'three_button_continuous' in n:dz=14
        elif 'rear_lid' in n or 'lid_M3' in n or 'lid_sealing' in n or 'lid_compression' in n:dz=-26
        result.append(replace(p,shape=p.shape.translate((0,0,dz))))
    return result
