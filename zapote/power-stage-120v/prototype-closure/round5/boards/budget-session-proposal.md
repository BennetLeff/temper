# Retained qualified RUN ECO — reviewed implementation

Before this ECO, native U_BUDGET1 input2 was SUP_RUN_OK_LOCAL. A valid session faults after demand drops once TOTAL_WINDOW has expired. The rejected BYPASS-only replacement is withdrawn and source first restored to its prior native semantics before the distinct reviewed correction.

## Counterexample to rejected replacement

With ATTEMPT=1, PRECHARGE_ISOLATED=1, PROOF_WINDOW=1 and PRECHARGE_DONE=1, a PB13 rising edge can set BYPASS_PROVEN. There is no independent hardware proof counter or50ms dwell qualification. If MCU_RUN never rises then RUN_ARMED remains0, RUNTIME_ALLOWED remains1 via RUN_NOT_ARMED, and BYPASS-only escape would extend an attempt even with unhealthy controller runtime inputs. This is a real weakening, not a naming misunderstanding.

## Distinct proposed change

1. U_RUN3 physical input2: CTRL_RAIL_OK_LOCAL → RUNTIME_HEALTHY. The latter is CTRL_RAIL_OK_LOCAL AND CTRL_HEARTBEAT_OK AND NATIVE_FAULT_N AND CTRL_INTERLOCK_OK_LOCAL; this adds the interlock to actual RUN qualification and preserves all previous conditions.
2. U_RUN_ARM physical CLK1: MCU_RUN → SUP_RUN_OK_LOCAL. Its D2 remains POD_3V3. It can only set on a fully qualified physical RUN rising edge.
3. U_RUN_ARM physical CLR_N6: ATTEMPT → FINAL_PROOF_CLEAR_N (ATTEMPT AND PRECHARGE_ISOLATED). Fault/end already clears ATTEMPT; isolation loss additionally clears the retained permission.
4. New SN74LVC1G08DBVR gate plus100nF bypass: input1 RUN_ARMED, input2 RUNTIME_HEALTHY, output SESSION_BUDGET_OK.
5. U_BUDGET1 physical input2: SUP_RUN_OK_LOCAL → SESSION_BUDGET_OK. TOTAL_WINDOW input1 stays unchanged.

U_RUNTIME_ALLOW remains NOT RUN_ARMED OR RUNTIME_HEALTHY. Do not clear RUN_ARM directly with RUNTIME_HEALTHY: doing that would bypass the runtime fault path before it can latch. Instead the live health gate immediately removes budget escape, while the existing runtime fault chain drops LATCH_OK and ATTEMPT. Source drivers retain ATTEMPT, budget and LATCH gates.

Independent review exercised29settled pin-driven state cases. A first proof, PB13 alone, or MCU_RUN alone cannot latch the proposed session. A successful actual RUN edge under all guards can latch it. Heat demand falling leaves the latch and live health intact, without triggering or extending either one-shot. Runtime fault, hard fault and end remove source permission. Isolation loss clears RUN/PERMIT and retained proof/session immediately; during the still-active startup window source may remain until firmware fault or deadline. After expiry, isolation loss removes source through the budget fault path. This remains a Boolean/state argument; asynchronous propagation, setup/hold and clear recovery require timing qualification.

The source implements this distinct reviewed ECO. Regenerated native checks and final routing receipts are required before acceptance. The rejected BYPASS-only alternative is not implemented.
