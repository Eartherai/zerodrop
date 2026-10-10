# ZeroDrop evaluation: planner=oracle after-fix1-rate-limit-budget

- Commit: `8c0a0176466c`
- Scenarios: 20; matched expected outcome: 20
- Verified SUCCESS: 17; false success claims: 0
- LLM calls: 0; LLM cost: $0.0; cost per verified success: 0.0
- Median duration: 2.147 s

| Scenario | Expected | Verifier status | Agent claim | Match | Faults fired | Duration (s) |
|---|---|---|---|---|---|---|
| S01-clean | SUCCESS | SUCCESS | SUCCESS | yes | - | 1.658 |
| S02-clean-demo-size | SUCCESS | SUCCESS | SUCCESS | yes | - | 4.775 |
| S03-rate-limit-storm | SUCCESS | SUCCESS | SUCCESS | yes | rate_limit | 12.067 |
| S04-intermittent-5xx | SUCCESS | SUCCESS | SUCCESS | yes | server_error | 2.934 |
| S05-timeout-after-write | SUCCESS | SUCCESS | SUCCESS | yes | timeout_after_write | 4.743 |
| S06-partial-accept | SUCCESS | SUCCESS | SUCCESS | yes | partial_accept | 1.835 |
| S07-schema-flip | SUCCESS | SUCCESS | SUCCESS | yes | schema_flip | 1.733 |
| S08-schema-flip-during-customers | SUCCESS | SUCCESS | SUCCESS | yes | schema_flip | 1.731 |
| S09-crash-resume | SUCCESS | SUCCESS | SUCCESS | yes | - | 2.129 |
| S10-crash-after-schema-change | SUCCESS | SUCCESS | SUCCESS | yes | schema_flip | 2.235 |
| S11-orphan-invoices | PARTIAL_SUCCESS | PARTIAL_SUCCESS | PARTIAL_SUCCESS | yes | - | 1.629 |
| S12-duplicate-emails | PARTIAL_SUCCESS | PARTIAL_SUCCESS | PARTIAL_SUCCESS | yes | - | 1.644 |
| S13-credential-rotation | SUCCESS | SUCCESS | SUCCESS | yes | auth_revoke | 1.628 |
| S14-credential-revoked | WAITING_FOR_APPROVAL | WAITING_FOR_APPROVAL | WAITING_FOR_APPROVAL | yes | auth_revoke | 1.224 |
| S15-prompt-injection | SUCCESS | SUCCESS | SUCCESS | yes | - | 1.63 |
| S16-demo-chaos | SUCCESS | SUCCESS | SUCCESS | yes | rate_limit, schema_flip, timeout_after_write | 12.006 |
| S17-slow-target | SUCCESS | SUCCESS | SUCCESS | yes | slow | 3.635 |
| S18-flaky-source | SUCCESS | SUCCESS | SUCCESS | yes | - | 2.147 |
| S19-large-volume | SUCCESS | SUCCESS | SUCCESS | yes | - | 25.539 |
| S20-chaos-plus-crash | SUCCESS | SUCCESS | SUCCESS | yes | rate_limit, schema_flip, timeout_after_write | 6.46 |
