# Review probes

Six inputs supplied during review of the `zapote-claims` checks. Each was
originally accepted by the implementation (`LEDGER SOUND`, exit 0) and each is
now rejected. They are retained as fixtures: `campaign_ledgers.rs` asserts that
none of them produces a clean pass, so a future change that re-opens one of these
holes fails the suite.

| Probe | Failure it exercises |
| --- | --- |
| `changed_condition.json` | a derived claim moves the source condition (50 A -> 500 A) with no declared transformation |
| `changed_part.json` | a derived claim changes the part identity with no declared transformation |
| `qualified_root_without_evidence.json` | a **root** claim asserted `qualified` with no evidence reference |
| `unverified_evidence.json` | a qualified prediction whose evidence reference does not resolve |
| `unsupported_completion_history.json` | a completion promotion whose `from` status the history never established, citing a nonexistent record |
| `empty_ledger.json` | a ledger with nothing in it, which must not read as a clean pass |

They are kept verbatim as supplied, so some use the pre-hardening schema; a
schema rejection is an acceptable outcome for those. The invariant is that **no
probe yields a clean pass**.
