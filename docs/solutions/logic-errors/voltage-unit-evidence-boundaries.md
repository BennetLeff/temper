---
title: Voltage unit checks need independent identities and worst-case inputs
date: 2026-09-11
category: logic-errors
module: zapote
problem_type: logic_error
severity: high
tags: [kicad, native-evidence, voltage-sensing, semantic-validation]
---

The standalone voltage unit exposed three different ways self-consistent evidence can mislead.

1. The inherited ADC divider (3×169 kΩ +10 kΩ) exceeded the receiver ceiling within the assumed bus envelope. A proposed 270 kΩ replacement looked suitable using an incorrect nominal calculation; independently recomputing tolerance/temperature corners led to 300 kΩ. Check the whole input envelope before adopting a standard-value substitute.
2. Native skeleton generation lost library pad/text orientation and metadata. DRC library comparison found mismatches even though routed connectivity was sound. Reloading original library footprints through KiCad, requiring unchanged pad centres, restored the semantics. Never derive the library oracle from the modified candidate to make this comparison pass.
3. Two SOT-23-5 devices shared a footprint-derived symbol key. Adding datasheet pin names to that shared drawing made the comparator display reference-device pin names while all pin-number nets remained correct. Visual review found this. The voltage drawing now gives each component a distinct symbol identity; package equality does not imply electrical model equality.

The Rust harness now checks complete source/native component and pin-net censuses, values against exact MPN identities, topology, native copper connectivity, source-derived conditional bounds, shared copper clearance and saved-board stackup. A saved-document check independently compares component MPN/pad nets and straight-trace/via data to raw board bytes; rehashing a contradictory export cannot satisfy it. World pad shapes, filled zones and connectivity remain a pinned KiCad-extractor trust boundary. Do not claim that this verifies every possible forged export field.

Regression controls in `zapote/packages/zapote-harness/tests/voltage_sense.rs` reject the old divider, swapped input, missing component/pin evidence, crossing copper, stale hashes, rehashed contradictory saved nets and zero dielectric. Existing common board checks cover the prior “inside a box” stackup defect. A command-level test retains INDETERMINATE and nonzero exit for physical qualification gaps.

The enforceable learning is the validator plus counterexample. A memory note is a retrieval aid, not proof of a model, measurement, or coverage multiplier. The voltage run demonstrated reuse of the selection mechanism; it did not measure an improvement in agent success rate.
