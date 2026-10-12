# ZeroDrop evaluation: planner=oracle after-fix7-early-check

- Commit: `286c7286038c`
- Scenarios: 20; matched expected outcome: 20
- Verified SUCCESS: 17; false success claims: 0
- LLM calls: 0; LLM cost: $0.0; cost per verified success: 0.0
- Median duration: 0.626 s

| Scenario | Expected | Verifier status | Agent claim | Match | Faults fired | Duration (s) |
|---|---|---|---|---|---|---|
| S01-clean | SUCCESS | SUCCESS | SUCCESS | yes | - | 0.565 |
| S02-clean-demo-size | SUCCESS | SUCCESS | SUCCESS | yes | - | 0.637 |
| S03-rate-limit-storm | SUCCESS | SUCCESS | SUCCESS | yes | rate_limit | 1.752 |
| S04-intermittent-5xx | SUCCESS | SUCCESS | SUCCESS | yes | server_error | 1.744 |
| S05-timeout-after-write | SUCCESS | SUCCESS | SUCCESS | yes | timeout_after_write | 2.558 |
| S06-partial-accept | SUCCESS | SUCCESS | SUCCESS | yes | partial_accept | 0.626 |
| S07-schema-flip | SUCCESS | SUCCESS | SUCCESS | yes | schema_flip | 0.524 |
| S08-schema-flip-during-customers | SUCCESS | SUCCESS | SUCCESS | yes | schema_flip | 0.525 |
| S09-crash-resume | SUCCESS | SUCCESS | SUCCESS | yes | - | 0.52 |
| S10-crash-after-schema-change | SUCCESS | SUCCESS | SUCCESS | yes | schema_flip | 0.516 |
| S11-orphan-invoices | PARTIAL_SUCCESS | PARTIAL_SUCCESS | PARTIAL_SUCCESS | yes | - | 0.416 |
| S12-duplicate-emails | PARTIAL_SUCCESS | PARTIAL_SUCCESS | PARTIAL_SUCCESS | yes | - | 0.419 |
| S13-credential-rotation | SUCCESS | SUCCESS | SUCCESS | yes | auth_revoke | 0.422 |
| S14-credential-revoked | WAITING_FOR_APPROVAL | WAITING_FOR_APPROVAL | WAITING_FOR_APPROVAL | yes | auth_revoke | 0.423 |
| S15-prompt-injection | SUCCESS | SUCCESS | SUCCESS | yes | - | 0.424 |
| S16-demo-chaos | SUCCESS | SUCCESS | SUCCESS | yes | rate_limit, schema_flip, timeout_after_write | 4.816 |
| S17-slow-target | SUCCESS | SUCCESS | SUCCESS | yes | slow | 2.561 |
| S18-flaky-source | SUCCESS | SUCCESS | SUCCESS | yes | - | 0.931 |
| S19-large-volume | SUCCESS | SUCCESS | SUCCESS | yes | - | 1.494 |
| S20-chaos-plus-crash | SUCCESS | SUCCESS | SUCCESS | yes | rate_limit, schema_flip, timeout_after_write | 3.177 |
