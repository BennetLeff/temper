# RTD validator coverage inventory

| Requirement / fault | Rust owner | Evidence class | Cases |
|---|---|---|---|
| Exact ADC, connector, RREF, REF2025 identity | `zapote-erc::check_topology` | exact structural | valid + connector/RREF mutations |
| Four-wire FORCE/SENSE pin and net partition | `zapote-erc::check_topology` | exact structural + native endpoint clusters | valid, swap, force/sense short |
| Native copper endpoint connectivity | `zapote-erc::check_topology` | native measured input | missing/split cluster is indeterminate/fail |
| Upstream vs post-ferrite rail identity | `zapote-drc::check_rail` | exact structural | valid + wrong rail |
| Local ADC/reference bypass and locality | `zapote-drc::check_decoupling` | authored placement heuristic | missing, wrong rail, out-of-range |
| Sensitive-net/aggressor region | `zapote-drc::check_sensitive_geometry` | authored geometry heuristic | intrusion is fail; missing trace is indeterminate |
| Prohibited domain connection | `zapote-drc::check_prohibited_connections` | exact connection check | component joining authored net pair |
| SPI GPIO/pin/series correspondence | `zapote-erc::check_firmware` | exact source contract | wrong CS/DRDY; DRDY direct is accepted |
| MAX31865 threshold register words | `zapote-erc::max31865_code` | bounded calculation | low/high boundaries + exact ADC-code boundary |
| Short/open/valid, rail loss, conductor-open classification | `zapote-erc::check_fault_scenarios` | bounded behavioral classification | all four conductor opens, unsupported name, short/open boundaries |
| Source/board/suite/model identity | `zapote-core::Identity::validate` | evidence validity + adapter artifact binding | missing/empty/mismatched observed digest cannot pass; only the adapter can establish bytes |

The suite is a validator foundation. It has no claim of complete board
acceptance until an adapter supplies the real source-derived input and native
KiCad measurements. Cable SENSE+ open remains an explicit documented gap.
