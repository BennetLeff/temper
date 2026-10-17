**Safe state incorrect for the all-state active-low requirement: D21's A=0/B=1 force polarity is correct, but failed-init cleanup disables the GPIO outputs again; physical pin levels remain undetermined.**

This closes the **steady force-polarity question**, not the review's target/HIL
acceptance gate. Work stopped at the real SDK-versus-host-stub discrepancy;
no firmware patch, firmware edit, powered test, QEMU pin result, or PR1643
modification is included. The requested fix is withheld under the stop/report
rule until this contradictory cleanup contract is resolved.

## Artifact and authoritative sources

Analyzed [draft PR1643](https://github.com/BennetLeff/temper/pull/1643), head
`9cddf149a1500896a7cf8fbca78ee2cc901f04ba`, not the older firmware on the
D25 base. D25's clean base is `c09244caa7588bb72d786a8b1b884390003a5caf`.
[Provenance](provenance.json) records runtime and identity; [sources.json](sources.json)
records complete SHA-256 hashes, exact source URLs and Git snapshot paths.
Downloads and unchanged D21 snapshots stay in ignored `cache/` and can be
recreated from pinned URLs without a local D21 Git object. PCB, netlist and component qualification are outside this finding.

- **TRM:** [ESP32-S3 Technical Reference Manual, v1.8](https://documentation.espressif.com/esp32-s3_technical_reference_manual_en.pdf), Chapter 36: §36.3.3/Figure 36.3-13 p1339; §36.3.3.1 pp1341,1348–1349; §36.3.3.2/Figure 36.3-21 p1351 and Table 36.3-5 p1352; GEN0_FORCE register 36.20 p1376; DT0_CFG register 36.23 p1379. Pages are printed PDF pages, matching the PDF page index starting at one. Full PDF hash is pinned; an upstream replacement fails verification rather than silently changing the authority.
- **SDK:** [ESP-IDF v5.3](https://github.com/espressif/esp-idf/tree/e0991facf5ecb362af6aac1fae972139eb38d2e4), tag resolves to `e0991facf5ecb362af6aac1fae972139eb38d2e4`. Every source link below uses that commit.
- **Emulator:** Espressif QEMU `febae182e132e4055529be423a818225ebddaa3a` and toolchain support documentation `cdee381dce7b88b5207ec48c72984ca31d495dd3`. This claim is scoped to those revisions.

## Signal order: TRM and SDK agree

The TRM operator diagram orders **PWM generator → dead-time generator →
carrier → fault handler**. Generator software force belongs to the first
block; fault-handler software trip is a different mechanism. The dead-time
diagram places the RED/FED inversion switches after their delays. With
D21's separate raw sources, A follows RED(A); B follows inverted FED(B).
Constant A=0/B=1 therefore yields constant Aout=0/Bout=0. This is a static
logic conclusion, with carrier and downstream fault overrides inactive,
GPIO-matrix inversion disabled, and the programmed configuration effective.
Sources: TRM Figure 36.3-13, §36.3.3.1, Figure 36.3-21/Table 36.3-5 above.

The SDK independently agrees:

| Layer | Pinned evidence | Meaning |
|---|---|---|
| API contract | [mcpwm_gen.h:59–75](https://github.com/espressif/esp-idf/blob/e0991facf5ecb362af6aac1fae972139eb38d2e4/components/esp_driver_mcpwm/include/driver/mcpwm_gen.h#L59-L75), especially line65; [line271](https://github.com/espressif/esp-idf/blob/e0991facf5ecb362af6aac1fae972139eb38d2e4/components/esp_driver_mcpwm/include/driver/mcpwm_gen.h#L271) | Forced level can be inverted by dead-time/GPIO matrix; dead-time flag inverts after delay. |
| Force driver | [mcpwm_gen.c:128–151](https://github.com/espressif/esp-idf/blob/e0991facf5ecb362af6aac1fae972139eb38d2e4/components/esp_driver_mcpwm/src/mcpwm_gen.c#L128-L151) | `hold_on=true` calls the continuous generator-force LL function. It does not invoke fault-handler output forcing. |
| Force LL | [mcpwm_ll.h:933–940](https://github.com/espressif/esp-idf/blob/e0991facf5ecb362af6aac1fae972139eb38d2e4/components/hal/esp32s3/include/hal/mcpwm_ll.h#L933-L940) | Writes immediate update and `level+1` into GENx_FORCE's A/B modes. |
| Dead-time driver and LL | [mcpwm_gen.c:359–390](https://github.com/espressif/esp-idf/blob/e0991facf5ecb362af6aac1fae972139eb38d2e4/components/esp_driver_mcpwm/src/mcpwm_gen.c#L359-L390); [mcpwm_ll.h:990–1107](https://github.com/espressif/esp-idf/blob/e0991facf5ecb362af6aac1fae972139eb38d2e4/components/hal/esp32s3/include/hal/mcpwm_ll.h#L990-L1107) | Independent RED/FED input selection, inversion, bypass and output swap fields match the TRM switches. Delay fields encode requested ticks minus one. |
| HAL/default routing | [mcpwm_hal.c:34–55](https://github.com/espressif/esp-idf/blob/e0991facf5ecb362af6aac1fae972139eb38d2e4/components/hal/mcpwm_hal.c#L34-L55); [mcpwm_gen.c:83–98](https://github.com/espressif/esp-idf/blob/e0991facf5ecb362af6aac1fae972139eb38d2e4/components/esp_driver_mcpwm/src/mcpwm_gen.c#L83-L98) | Immediate delay updates and cleared software brake/force actions; generator's `invert_pwm` controls the separate GPIO-matrix inversion. D21 zero-initializes that flag. |

**Do not change low-generator force from 1 to 0 to address the review:** the
truth table in [register_check.txt](register_check.txt) shows that would make
the steady low-side PWM output high under this topology.

## Independent register calculation and state boundaries

[register_check.c](register_check.c) invokes verbatim pinned LL functions on
the SDK register structure, using a hand-transcribed call sequence from the
pinned driver's D21 configuration path. A separate literal-bit decoder uses
the TRM diagram. This checks encoding and static logic, not actual MMIO,
clock propagation, pending delay events, or a running ESP32 image.

For D21's existing host fixture, 307 ns requests 24 ticks. RED/FED fields are
23; the topology-only DT_CFG bits [16:8] are `0x05000`: A input for RED, B
input for FED, FED inversion enabled, no bypass/swap/DEB. GEN_FORCE's A/B
modes are 1/2 with immediate update, yielding `0x240`. Full DT_CFG also
contains clock/update fields, deliberately excluded from this topology mask.
The existing fixture is not the owner's selected controller gap; no new gap
is selected or validated here. Evidence: [calculation output](register_check.txt),
[SDK clock selection](https://github.com/espressif/esp-idf/blob/e0991facf5ecb362af6aac1fae972139eb38d2e4/components/esp_driver_mcpwm/src/mcpwm_oper.c#L178-L180).

| State | Source-derived state | What is established |
|---|---|---|
| Init while routing/configuring | D21 holds pads low while setting raw A=0/B=1, then programs dead time | Intent and API sequence only; intermediate pad-hold behavior is not measured. Before inversion exists, raw B=1 is not intrinsically a low pad. |
| Successfully initialized, force retained | GEN_FORCE A/B=1/2; DT topology above | Steady peripheral outputs 0/0, assuming configured path effective. |
| Normal stop / successful emergency stop | Rewrites A=0 then B=1, keeps timer clocked | Same steady 0/0 result. Separate writes are not simultaneous; no shutdown latency, glitch-free transition, or immediate physical gate-off guarantee is proven. |
| Start | Both force modes cleared | Generator actions resume; no new dynamic waveform verification claimed. |
| Failed init after generator allocation | Drives low, then deletes generators, resetting those GPIOs | Output drive becomes disabled with pull-up enabled; actual voltage is undetermined. |
| Deinit | Same drive-low then generator-delete ordering | Same GPIO-mode defect; no new powered-operation claim. |

## Blocking discrepancy: cleanup undoes the GPIO drive

In pinned [D21 hal_pwm_esp32.c:156–159](https://github.com/BennetLeff/temper/blob/9cddf149a1500896a7cf8fbca78ee2cc901f04ba/firmware/components/hal/esp32/hal_pwm_esp32.c#L156-L159),
failed init calls `invalidate()` then `release_resources()`. The former
runs `low_pin()`; the latter deletes each allocated generator at lines76–77.
But actual [SDK mcpwm_gen.c:114–124](https://github.com/espressif/esp-idf/blob/e0991facf5ecb362af6aac1fae972139eb38d2e4/components/esp_driver_mcpwm/src/mcpwm_gen.c#L114-L124)
calls `gpio_reset_pin()` during deletion. [gpio.c:436–448](https://github.com/espressif/esp-idf/blob/e0991facf5ecb362af6aac1fae972139eb38d2e4/components/esp_driver_gpio/src/gpio.c#L436-L448)
sets mode DISABLE, pull-up enabled, pull-down disabled; [gpio.c:383–401](https://github.com/espressif/esp-idf/blob/e0991facf5ecb362af6aac1fae972139eb38d2e4/components/esp_driver_gpio/src/gpio.c#L383-L401)
implements those effects. No later `low_pin()` runs on that return path.

[D21's stub:53–59](https://github.com/BennetLeff/temper/blob/9cddf149a1500896a7cf8fbca78ee2cc901f04ba/firmware/test/pwm_sdk_stub/sdk_stub.c#L53-L59)
omits generator deletion's GPIO-reset effect, treats reset as a stored zero,
and ignores output direction. Its zero-valued `sdk_pin()` cannot establish
active-low drive after cleanup. This is the concrete contradiction that
triggered stop/report; the vendor force-order sources themselves agree.

[cleanup_probe.c](cleanup_probe.c) runs the **unchanged** D21 HAL and adds
only the relevant SDK direction/reset side effects to its existing stub.
It preserves the original one-shot public-API failure positions; no external
circuit, analog pad voltage, hold timing, or general SDK emulation is added.
[Output](cleanup_probe.txt) reproduces 11 of 29 init failure positions ending
with at least one output disabled while the old stub still returns level 0.
This is a bounded host reproduction of the source defect, not HIL evidence.
Output-disabled with an enabled weak pull-up does **not** establish a high
pin, a low pin, or a gate turning on: external loads/pull-downs matter.

## QEMU capability

[Capability receipt](qemu-capability.txt) checks a complete, non-truncated
pinned source tree and the ESP32-S3 machine definition. There is no MCPWM
source path or instantiated/mapped MCPWM device in [esp32s3.c](https://github.com/espressif/qemu/blob/febae182e132e4055529be423a818225ebddaa3a/hw/xtensa/esp32s3.c).
Its generic unsupported-I/O handlers at lines461–476 return zero for reads
and discard writes; such zeros are not GPIO-output evidence. The pinned
[official supported-feature table](https://github.com/espressif/esp-toolchain-docs/blob/cdee381dce7b88b5207ec48c72984ca31d495dd3/qemu/README.md#L42)
also marks GPIO matrix/IOMUX unsupported. **No QEMU image was built or run**:
this revision cannot perform the requested MCPWM-to-pad observation.

## Reproduction and remaining acceptance

From this directory:

```sh
python3 -B reproduce.py fetch   # only needed to obtain ignored pinned sources
python3 -B reproduce.py run     # two small C probes; cache-only build/output
python3 -B reproduce.py check   # read-only source/evidence integrity check
```

`run` passes only when the polarity calculation passes **and the unfixed
cleanup defect is reproduced**. A zero exit is not safe-state acceptance.
[Attempt history](attempts/README.md) preserves an initial INDETERMINATE
probe abort caused by a swapped-bit transcription in this evidence tool,
then its source-grounded correction. No abort was counted as a pass.

Outstanding: resolve the GPIO cleanup contract and update the misleading
stub, then compile the reviewed firmware for the pinned target SDK and
measure both pins in forced/init/failed-init/stop states. The PR review's
physical target/HIL gate remains open. This source analysis cannot waive it,
qualify pad holds, prove simultaneous turn-off, or validate gate voltages.
No patch is supplied because remediation stopped at the reported contradiction.
