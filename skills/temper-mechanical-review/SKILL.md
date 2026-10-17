---
name: temper-mechanical-review
description: Review Temper enclosure, mounting, and mechanical interfaces for functional location, variation, thermal growth, load paths, assembly, and service. Use for mechanical design decisions or design reviews, not for generic PCB routing or visual styling alone.
---

# Temper mechanical review

Start from the user's chosen enclosure concept and the current product requirements. Compare alternatives only when asked or when a discovered conflict blocks the chosen design. Treat course methods as reasoning tools, not as authority for a cooker's numerical limits, materials, torque, seal rating, or safety certification. Read [source notes](references/mit-mechanical-sources.md) when a method needs attribution or its scope is uncertain.

For the few relationships whose variation can change performance, safety, assembly, or user experience, state the required function and its measurable acceptance criterion. Trace each through the features and fixtures that locate it: which surface establishes a datum, which contact constrains each motion, and which fastener merely holds parts together. Include PCB mounts, coil carrier, cookware support, thermal interface, connectors, and serviceable covers only where they affect the task. A CAD collision pass establishes fit in one modeled state; it does not establish strength, stiffness, seal integrity, or performance across variation.

For a critical relationship, budget manufacturing and assembly variation alongside thermal growth, load deflection, and reassembly error. Distinguish specified tolerance from observed process variation and resulting clearance. Use worst-case combinations when an endpoint failure matters; use statistical combination only with a defensible distribution and correlation model. Call out missing prototype measurements rather than inventing a tolerance.

For a switch or plunger, check both ends: minimum available motion must exceed the maximum trip requirement with the specified margin; maximum delivered motion/force must stay below the supplier's safe mechanical limit. A nominal click or detent-motion pass does not establish either inequality. For seals, trace minimum/maximum compression and contact through gland geometry, material tolerances, thermal growth, compression set, cycling, and reassembly; a modeled contact or interference is not evidence of leak resistance.

Look for redundant location that makes tightening, heating, or material expansion bend the PCB, coil carrier, top, or heat sink. A compliant feature can permit intended growth while retaining the needed location; show which direction is constrained and which can move. Trace the load from cookware, handling, drop/transport, and joint preload to supports and fasteners. Estimate deflection or joint separation at the relevant load; a static fit does not prove a joint will retain preload under cycling.

Walk the assembly and service sequence with real parts when available: orientation, lead-ins, visibility, tool reach, cable routing, connector access, seal placement, and the ability to restore critical relationships after opening. Test the states that can change the verdict: cold, hot steady state, thermal cycling, wet exposure where relevant, assembly variation, and reassembly. Propose product-specific test conditions and pass criteria from requirements; do not borrow machine-tool numbers or treat a suggested test as already passed.

Report the few design decisions that would actually change, with the evidence, uncertainty, and next measurement for each. Separate **MIT course method**, **Temper-specific inference**, and **verified product result**. Preserve unresolved concerns as questions to measure, not silent redesigns.
