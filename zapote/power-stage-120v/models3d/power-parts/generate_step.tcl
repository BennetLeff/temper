# OpenCascade DRAWEXE model source. Run:
#   for part in bridge diode kds tmov choke ct; do
#       PS_MODEL=$part DRAWEXE -b -f generate_step.tcl
#   done
# Units: mm. These are provisional envelope models, not vendor CAD.
# Model X = footprint X, model Y = -footprint Y, Z is height above PCB.
# Negate both endpoints of a footprint Y interval before taking its minimum.
pload ALL
set out [file dirname [info script]]
if {![info exists ::env(PS_MODEL)]} {
    error "Set PS_MODEL to bridge, diode, kds, tmov, choke, or ct"
}

proc makebox {name x y z sx sy sz} {
    uplevel #0 [list box $name -min $x $y $z -size $sx $sy $sz]
}
proc makecylinder {name x y z radius height} {
    uplevel #0 [list pcylinder $name $radius $height]
    uplevel #0 [list ttranslate $name $x $y $z]
}
proc exportmodel {name parts path} {
    if {$::env(PS_MODEL) ne $name} {
        return
    }
    uplevel #0 [list compound {*}$parts $name]
    puts "$name: [uplevel #0 [list checkshape $name]]"
    puts [uplevel #0 [list bounding $name -dump]]
    uplevel #0 [list stepwrite 0 $name $path]
}

# Diodes Incorporated GBJ2510-F. Body 30.3 x 4.8 x 17.5 above
# 2.8 mm lead stubs gives the 20.3 mm published total-height envelope.
makebox bridge_body -2.65 -2.4 2.8 30.3 4.8 17.5
set bridge_parts {bridge_body}
foreach {name x} {bridge_pin1 0 bridge_pin2 10 bridge_pin3 17.5 bridge_pin4 25} {
    makebox $name [expr {$x - 0.5}] -0.4 0 1.0 0.8 2.8
    lappend bridge_parts $name
}
exportmodel bridge $bridge_parts "$out/GBJ2510-F_provisional.step"

# Microchip MRT130KP295CV. Package body 12.954 x 7.874 diameter,
# horizontally mounted at P20. Formed leads are a local assumption.
pcylinder diode_body 3.937 12.954
trotate diode_body 0 0 0 0 1 0 90
ttranslate diode_body 3.523 0 4.1
set diode_parts {diode_body}
makebox diode_lead_left 0 -0.4 3.7 3.523 0.8 0.8
makebox diode_lead_right 16.477 -0.4 3.7 3.523 0.8 0.8
makecylinder diode_pin1 0 0 0 0.4 4.1
makecylinder diode_pin2 20 0 0 0.4 4.1
lappend diode_parts diode_lead_left diode_lead_right diode_pin1 diode_pin2
exportmodel diode $diode_parts "$out/MRT130KP295CV_provisional.step"

# Phoenix Contact KDS 3 1704004. Published installed body 5.08 x 27 x 25;
# solder pins are at local (0,0) and (0,15.24), with 3.5 mm tails.
makebox kds_body -2.54 -22.9 0 5.08 27 25
set kds_parts {kds_body}
makebox kds_pin1 -0.55 -0.4 -3.5 1.1 0.8 3.5
makebox kds_pin2 -0.55 -15.64 -3.5 1.1 0.8 3.5
lappend kds_parts kds_pin1 kds_pin2
exportmodel kds $kds_parts "$out/KDS3_1704004_provisional.step"

# Littelfuse TMOV20RP175E: 23 mm maximum disc diameter, 9 mm maximum
# thickness, 28 mm seated height. Lead forming to 7.5 mm is provisional.
pcylinder tmov_body 11.5 9
trotate tmov_body 0 0 0 1 0 0 90
ttranslate tmov_body 3.75 4.5 16.5
set tmov_parts {tmov_body}
makecylinder tmov_pin1 0 0 0 0.6 5
makecylinder tmov_pin2 7.5 0 0 0.6 5
lappend tmov_parts tmov_pin1 tmov_pin2
exportmodel tmov $tmov_parts "$out/TMOV20RP175E_provisional.step"

# TDK B82726S2203A020 45 x 25.5 x 41 maximum envelope. The torus
# represents the open ferrite/windings; exact winding profile is unavailable.
makebox choke_carrier -17.5 -25.25 0 45 25.5 3
ptorus choke_ring 12.5 6.0
trotate choke_ring 0 0 0 1 0 0 90
ttranslate choke_ring 5 -12.5 20.5
set choke_parts {choke_carrier choke_ring}
foreach {name x y} {choke_pin1 0 0 choke_pin2 10 0 choke_pin3 10 -25 choke_pin4 0 -25} {
    makecylinder $name $x $y -3.5 1.0 3.5
    lappend choke_parts $name
}
exportmodel choke $choke_parts "$out/B82726S2203A020_provisional.step"

# Coilcraft CST3015-100ED 23 x 30 x 15.2 maximum body. Pad row centres
# are y=-11.55 and +13.75 mm from the reviewed local footprint.
makebox ct_base -11.5 -15 0 23 30 2.5
makebox ct_core -11 -9.5 2.5 22 22 12.7
set ct_parts {ct_base ct_core}
foreach {name x y sx sy} {ct_pad1 5.58 11.55 4.8 9.0 ct_pad2 -5.58 11.55 4.8 9.0 ct_pad3 -6.88 -13.75 3.0 4.6 ct_pad4 6.88 -13.75 3.0 4.6} {
    makebox $name [expr {$x - $sx/2}] [expr {$y - $sy/2}] 0 $sx $sy 0.9
    lappend ct_parts $name
}
exportmodel ct $ct_parts "$out/CST3015-100ED_provisional.step"
