---
title: Zapote home-cooker functional target
date: 2026-09-23
status: active
---

# Zapote home-cooker functional target

Date: 2026-09-23. User direction: aim for cooking functionality comparable to the Breville Control Freak in a home kitchen. This is a **behavioral benchmark**, not permission to copy Breville's internal circuit or adopt its unstated bus, coil, cooling, insulation or discharge specifications.

Breville's published [Control Freak Home product description](https://www.breville.com/en-us/product/bmc800) and [instruction book](https://assets.breville.com/BMC800/BMC800_USCM_IB_J24_LR.pdf) describe setting and holding cooking temperature over 25–250 °C, a through-glass surface-temperature sensor, a food-temperature probe with control and thermometer use, heat-intensity adjustment, presets/modes and a touchscreen. Treat each as a candidate user-visible behavior requiring its own Zapote requirement, accuracy/timing definition and verification method; the quoted range and sampling description are product claims, not demonstrated Zapote performance.

Current evidence gaps remain separate from that product target. No specific Zapote coil/pan or fan prototype is available for measurements; no post-power-off discharge voltage/time criterion has been adopted. The inverter U3 and cooling gates therefore remain unmeasured, and discharge U3 remains unselected. A board candidate may be made for a bounded lab fixture, but it is not an accepted cooker power stage. Native cooker boards require selected components, declared electrical and mechanical envelopes, source identity, and independent schematic/PCB checks. Assembled heating, cooling and safety behavior must be measured on the eventual integrated article.
