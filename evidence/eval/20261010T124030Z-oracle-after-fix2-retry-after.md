# ZeroDrop evaluation: planner=oracle after-fix2-retry-after

- Commit: `574aa2bc9388`
- Scenarios: 20; matched expected outcome: 20
- Verified SUCCESS: 17; false success claims: 0
- LLM calls: 0; LLM cost: $0.0; cost per verified success: 0.0
- Median duration: 2.233 s

| Scenario | Expected | Verifier status | Agent claim | Match | Faults fired | Duration (s) |
|---|---|---|---|---|---|---|
| S01-clean | SUCCESS | SUCCESS | SUCCESS | yes | - | 1.666 |
| S02-clean-demo-size | SUCCESS | SUCCESS | SUCCESS | yes | - | 4.893 |
| S03-rate-limit-storm | SUCCESS | SUCCESS | SUCCESS | yes | rate_limit | 2.835 |
| S04-intermittent-5xx | SUCCESS | SUCCESS | SUCCESS | yes | server_error | 2.936 |
| S05-timeout-after-write | SUCCESS | SUCCESS | SUCCESS | yes | timeout_after_write | 4.749 |
| S06-partial-accept | SUCCESS | SUCCESS | SUCCESS | yes | partial_accept | 1.841 |
| S07-schema-flip | SUCCESS | SUCCESS | SUCCESS | yes | schema_flip | 1.844 |
| S08-schema-flip-during-customers | SUCCESS | SUCCESS | SUCCESS | yes | schema_flip | 1.733 |
| S09-crash-resume | SUCCESS | SUCCESS | SUCCESS | yes | - | 2.233 |
| S10-crash-after-schema-change | SUCCESS | SUCCESS | SUCCESS | yes | schema_flip | 2.331 |
| S11-orphan-invoices | PARTIAL_SUCCESS | PARTIAL_SUCCESS | PARTIAL_SUCCESS | yes | - | 1.638 |
| S12-duplicate-emails | PARTIAL_SUCCESS | PARTIAL_SUCCESS | PARTIAL_SUCCESS | yes | - | 1.741 |
| S13-credential-rotation | SUCCESS | SUCCESS | SUCCESS | yes | auth_revoke | 1.635 |
| S14-credential-revoked | WAITING_FOR_APPROVAL | WAITING_FOR_APPROVAL | WAITING_FOR_APPROVAL | yes | auth_revoke | 1.237 |
| S15-prompt-injection | SUCCESS | SUCCESS | SUCCESS | yes | - | 1.632 |
| S16-demo-chaos | SUCCESS | SUCCESS | SUCCESS | yes | rate_limit, schema_flip, timeout_after_write | 11.117 |
| S17-slow-target | SUCCESS | SUCCESS | SUCCESS | yes | slow | 3.641 |
| S18-flaky-source | SUCCESS | SUCCESS | SUCCESS | yes | - | 2.145 |
| S19-large-volume | SUCCESS | SUCCESS | SUCCESS | yes | - | 25.555 |
| S20-chaos-plus-crash | SUCCESS | SUCCESS | SUCCESS | yes | rate_limit, schema_flip, timeout_after_write | 5.754 |
