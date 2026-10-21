SHELL := /bin/sh
KICAD ?= kicad-cli
RUSTC ?= rustc
NGSPICE ?= ngspice
KICAD_PYTHON ?= /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3

.PHONY: all generate export check leads pcb pcb-generate pcb-check pcb-export pcb-oracle simulate
all:
	$(MAKE) generate
	$(MAKE) export
	$(MAKE) check

generate:
	$(RUSTC) --edition 2021 tools/build.rs -o /tmp/temper-differential-probe-build
	/tmp/temper-differential-probe-build

export:
	$(KICAD) sch export pdf cad/differential-probe.kicad_sch -o previews/differential-probe.pdf
	$(KICAD) sch export svg cad/differential-probe.kicad_sch -o previews/svg
	$(KICAD) sch export netlist --format kicadxml cad/differential-probe.kicad_sch -o validation/netlist.xml
	$(KICAD) sch export bom --fields 'Reference,Value,MPN,Manufacturer,Footprint,QUANTITY,DNP,EXCLUDE_FROM_BOARD,Datasheet,LCSC' --labels 'References,Value,MPN,Manufacturer,Footprint,Qty,DNP,Offboard,Datasheet,LCSC' --group-by 'MPN,Value,Footprint,DNP' cad/differential-probe.kicad_sch -o bom.csv
	$(KICAD) sch erc --exit-code-violations cad/differential-probe.kicad_sch -o validation/erc.rpt

check:
	$(RUSTC) --edition 2021 tools/check.rs -o /tmp/temper-differential-probe-check
	/tmp/temper-differential-probe-check
	$(MAKE) leads

# HV lead budget, setback gates, section view and FR4 part geometry; stage-53 probe points.
leads:
	$(RUSTC) --edition 2021 tools/leads.rs -o /tmp/temper-probe-leads
	/tmp/temper-probe-leads > /dev/null
	python3 tools/stage53_probe_points.py > /dev/null

# Ordered recursive calls keep generation/export dependencies safe under make -j.
pcb:
	$(MAKE) all
	$(MAKE) pcb-generate
	$(MAKE) pcb-check
	$(MAKE) pcb-export

pcb-generate:
	$(RUSTC) --edition 2021 tools/layout.rs -o /tmp/temper-probe-layout
	/tmp/temper-probe-layout
	$(KICAD_PYTHON) tools/pcb_bridge.py seed
	/tmp/temper-probe-layout route
	$(KICAD_PYTHON) tools/pcb_bridge.py apply

pcb-check:
	$(KICAD_PYTHON) tools/pcb_bridge.py pads
	$(RUSTC) --edition 2021 tools/check_pcb.rs -o /tmp/temper-probe-pcb-check
	/tmp/temper-probe-pcb-check
	$(KICAD) pcb drc --exit-code-violations --all-track-errors --format json -o validation/pcb-drc.json cad/differential-probe.kicad_pcb
	jq -e '(.violations|length)==0 and (.unconnected_items|length)==0' validation/pcb-drc.json
	shasum -a 256 cad/differential-probe.kicad_pcb cad/differential-probe.kicad_dru cad/differential-probe.kicad_pro validation/netlist.xml > validation/pcb-sha256.txt

pcb-export:
	$(KICAD) pcb export svg --layers F.Cu,F.SilkS,Edge.Cuts --page-size-mode 2 -o previews/pcb-top.svg cad/differential-probe.kicad_pcb
	$(KICAD) pcb export pdf --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.SilkS,F.Fab --common-layers Edge.Cuts --mode-multipage --crossout-DNP-footprints-on-fab-layers -o previews/pcb-layers.pdf cad/differential-probe.kicad_pcb
	$(KICAD) pcb render -o previews/pcb-3d.png --width 2200 --height 1400 --side top --rotate 15,0,0 cad/differential-probe.kicad_pcb

pcb-oracle:
	KICAD='$(KICAD)' KICAD_PYTHON='$(KICAD_PYTHON)' sh tools/check_drc_rules.sh

# Optional nominal low-voltage model checks; these do not qualify the hardware.
simulate:
	shasum -a 256 -c validation/spice/sha256.txt
	$(NGSPICE) -n -D ngbehavior=ps -b validation/spice/ac.cir > validation/spice/ac.log 2>&1
	$(NGSPICE) -n -D ngbehavior=ps -b validation/spice/unused-fine-saturation.cir > validation/spice/unused-fine-saturation.log 2>&1
	$(RUSTC) --edition 2021 tools/check_spice.rs -o /tmp/temper-probe-spice-check
	/tmp/temper-probe-spice-check
