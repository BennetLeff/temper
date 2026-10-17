"""Nominal engineering review sheets, projected from saved STEP using cadgen."""
from pathlib import Path
from math import cos,sin,radians
from cadgen import read_step, read_scene
from cadgen.eng_drawing import Sheet, eng_drawing

ROOT=Path(__file__).resolve().parents[1]


@eng_drawing(out='../PDF/manufacturing-review.pdf')
def review_drawings():
    knob=read_scene(ROOT/'STEP/knob.step')
    sensor=read_scene(ROOT/'STEP/sensor.step')
    support=read_scene(ROOT/'STEP/support.step')
    enclosure=read_scene(ROOT/'STEP/enclosure.step')
    definitions=[
        ('K-101','TURNED GRIP',knob.resolve('#turned_aluminum_grip_56mm').shape(),'6061-T6 candidate',2,
         ['REVIEW ONLY - NOMINAL DIMENSIONS.', '3X M2X0.4 BLIND TAPS, DEPTH 4.5.', 'CONFIRM TAP RUNOUT AND WORKHOLDING.', 'COSMETIC FINISH AND GRIP TEXTURE TO APPROVE.']),
        ('K-102','REPLACEABLE CAM',knob.resolve('#replaceable_profile_cam_8mm').shape(),'Engineering polymer - select grade',2,
         ['REVIEW ONLY - NOMINAL DIMENSIONS.', '8 MM PLATE; THROUGH PROFILE FROM STEP.', '3X DIA2.2, CSK DIA4.0 X 90 DEG.', '24 DETENTS; PROFILE AMPLITUDE 0.07 MM.']),
        ('S-101','CONTACT CAP',sensor.resolve('#contact_cap_thick_skirt_formed_lip').shape(),'Stainless candidate - select grade',5,
         ['REVIEW ONLY - NOMINAL DIMENSIONS.', 'TURN OPEN CUP, THEN INSERT PLUNGER.', 'FORM LOWER LIP AFTER INSERTION.', 'ROOF 0.35; SKIRT MIN 0.80 MM.', 'SECTION AND FORMING TOOL REVIEW REQUIRED.']),
        ('E-101','COIL SUPPORT PLATE',support.resolve('#coil_support_flat_routed_plate').shape(),'3 mm insulating laminate candidate',.5,
         ['REVIEW ONLY - NOMINAL DIMENSIONS.', 'PROFILE AND THROUGH HOLES ONLY.', '4X DIA4.4 AT X +/-157, Y190 AND 330.', 'DATUM Z85; COIL CENTER X0 Y261.', 'GRADE, DEFLECTION AND HEAT NOT QUALIFIED.']),
        ('E-102','SERVICE HATCH',enclosure.resolve('#sensor_service_cover').shape(),'2 mm aluminum candidate',2,
         ['REVIEW ONLY - NOMINAL DIMENSIONS.', '2X DIA3.4 ON 56 MM PITCH.', 'DEBURR; EDGE AND FINISH TO APPROVE.']),
        ('E-103','TAPPED HATCH STRIP',enclosure.resolve('#hatch_tapped_strip_28').shape(),'3 mm aluminum flat stock candidate',3,
         ['REVIEW ONLY - NOMINAL DIMENSIONS.', 'CENTER M3X0.5 THROUGH TAP.', '2X DIA3.2 RIVET HOLES, 16 MM PITCH.', 'RIVET GRIP 5 MM; SELECT RIVET BEFORE CUT.']),
    ]
    sheets=[]
    for number,title,shape,material,scale,notes in definitions:
        sheet=Sheet('A3',scale=scale,title=title,part_number=number,material=material,revision='R2',
                    notes=notes,author='Temper',general_tolerance='')
        top,front,right,iso=sheet.three_views(shape,iso=True,gap=28)
        top.overall();front.overall()
        if number=='K-102':
            top.hole((0,23.6,6),2.2,thru=True,csk=(4.0,90),count=3,angle=45)
        elif number=='E-102':
            top.hole((28,261,6),3.4,thru=True,count=2,angle=45)
            top.dim((-28,261,6),(28,261,6))
        elif number=='E-103':
            top.hole((28,261,10),3,thru=True,thread='M3x0.5',angle=45)
        sheets.append(sheet)
    return sheets


if __name__=='__main__':review_drawings()
