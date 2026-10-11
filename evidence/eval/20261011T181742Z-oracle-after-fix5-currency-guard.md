# ZeroDrop evaluation: planner=oracle after-fix5-currency-guard

- Commit: `7b34f8c4a72d`
- Scenarios: 18; matched expected outcome: 18
- Verified SUCCESS: 15; false success claims: 0
- LLM calls: 0; LLM cost: $0.0; cost per verified success: 0.0
- Median duration: 0.574 s

| Scenario | Expected | Verifier status | Agent claim | Match | Faults fired | Duration (s) |
|---|---|---|---|---|---|---|
| S01-clean | SUCCESS | SUCCESS | SUCCESS | yes | - | 0.574 |
| S03-rate-limit-storm | SUCCESS | SUCCESS | SUCCESS | yes | rate_limit | 1.733 |
| S04-intermittent-5xx | SUCCESS | SUCCESS | SUCCESS | yes | server_error | 1.734 |
| S05-timeout-after-write | SUCCESS | SUCCESS | SUCCESS | yes | timeout_after_write | 2.441 |
| S06-partial-accept | SUCCESS | SUCCESS | SUCCESS | yes | partial_accept | 0.622 |
| S07-schema-flip | SUCCESS | SUCCESS | SUCCESS | yes | schema_flip | 0.42 |
| S08-schema-flip-during-customers | SUCCESS | SUCCESS | SUCCESS | yes | schema_flip | 0.42 |
| S09-crash-resume | SUCCESS | SUCCESS | SUCCESS | yes | - | 0.417 |
| S10-crash-after-schema-change | SUCCESS | SUCCESS | SUCCESS | yes | schema_flip | 0.417 |
| S11-orphan-invoices | PARTIAL_SUCCESS | PARTIAL_SUCCESS | PARTIAL_SUCCESS | yes | - | 0.417 |
| S12-duplicate-emails | PARTIAL_SUCCESS | PARTIAL_SUCCESS | PARTIAL_SUCCESS | yes | - | 0.418 |
| S13-credential-rotation | SUCCESS | SUCCESS | SUCCESS | yes | auth_revoke | 0.42 |
| S14-credential-revoked | WAITING_FOR_APPROVAL | WAITING_FOR_APPROVAL | WAITING_FOR_APPROVAL | yes | auth_revoke | 0.421 |
| S15-prompt-injection | SUCCESS | SUCCESS | SUCCESS | yes | - | 0.419 |
| S16-demo-chaos | SUCCESS | SUCCESS | SUCCESS | yes | rate_limit, schema_flip, timeout_after_write | 4.68 |
| S17-slow-target | SUCCESS | SUCCESS | SUCCESS | yes | slow | 2.439 |
| S18-flaky-source | SUCCESS | SUCCESS | SUCCESS | yes | - | 0.922 |
| S20-chaos-plus-crash | SUCCESS | SUCCESS | SUCCESS | yes | rate_limit, schema_flip, timeout_after_write | 3.149 |
