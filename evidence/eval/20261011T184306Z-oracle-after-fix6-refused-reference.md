# ZeroDrop evaluation: planner=oracle after-fix6-refused-reference

- Commit: `6c07c9f41c81`
- Scenarios: 18; matched expected outcome: 18
- Verified SUCCESS: 15; false success claims: 0
- LLM calls: 0; LLM cost: $0.0; cost per verified success: 0.0
- Median duration: 0.596 s

| Scenario | Expected | Verifier status | Agent claim | Match | Faults fired | Duration (s) |
|---|---|---|---|---|---|---|
| S01-clean | SUCCESS | SUCCESS | SUCCESS | yes | - | 0.596 |
| S03-rate-limit-storm | SUCCESS | SUCCESS | SUCCESS | yes | rate_limit | 1.738 |
| S04-intermittent-5xx | SUCCESS | SUCCESS | SUCCESS | yes | server_error | 1.732 |
| S05-timeout-after-write | SUCCESS | SUCCESS | SUCCESS | yes | timeout_after_write | 2.444 |
| S06-partial-accept | SUCCESS | SUCCESS | SUCCESS | yes | partial_accept | 0.617 |
| S07-schema-flip | SUCCESS | SUCCESS | SUCCESS | yes | schema_flip | 0.42 |
| S08-schema-flip-during-customers | SUCCESS | SUCCESS | SUCCESS | yes | schema_flip | 0.414 |
| S09-crash-resume | SUCCESS | SUCCESS | SUCCESS | yes | - | 0.413 |
| S10-crash-after-schema-change | SUCCESS | SUCCESS | SUCCESS | yes | schema_flip | 0.518 |
| S11-orphan-invoices | PARTIAL_SUCCESS | PARTIAL_SUCCESS | PARTIAL_SUCCESS | yes | - | 0.415 |
| S12-duplicate-emails | PARTIAL_SUCCESS | PARTIAL_SUCCESS | PARTIAL_SUCCESS | yes | - | 0.417 |
| S13-credential-rotation | SUCCESS | SUCCESS | SUCCESS | yes | auth_revoke | 0.418 |
| S14-credential-revoked | WAITING_FOR_APPROVAL | WAITING_FOR_APPROVAL | WAITING_FOR_APPROVAL | yes | auth_revoke | 0.414 |
| S15-prompt-injection | SUCCESS | SUCCESS | SUCCESS | yes | - | 0.415 |
| S16-demo-chaos | SUCCESS | SUCCESS | SUCCESS | yes | rate_limit, schema_flip, timeout_after_write | 4.676 |
| S17-slow-target | SUCCESS | SUCCESS | SUCCESS | yes | slow | 2.433 |
| S18-flaky-source | SUCCESS | SUCCESS | SUCCESS | yes | - | 0.925 |
| S20-chaos-plus-crash | SUCCESS | SUCCESS | SUCCESS | yes | rate_limit, schema_flip, timeout_after_write | 3.149 |
