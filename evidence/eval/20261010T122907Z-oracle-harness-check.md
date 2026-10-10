# ZeroDrop evaluation: planner=oracle harness-check

- Commit: `c4766e230fa8`
- Scenarios: 20; matched expected outcome: 19
- Verified SUCCESS: 16; false success claims: 0
- LLM calls: 0; LLM cost: $0.0; cost per verified success: 0.0
- Median duration: 2.146 s

| Scenario | Expected | Verifier status | Agent claim | Match | Faults fired | Duration (s) |
|---|---|---|---|---|---|---|
| S01-clean | SUCCESS | SUCCESS | SUCCESS | yes | - | 1.556 |
| S02-clean-demo-size | SUCCESS | SUCCESS | SUCCESS | yes | - | 4.772 |
| S03-rate-limit-storm | SUCCESS | FAILED | FAILED | NO | rate_limit | 11.967 |
| S04-intermittent-5xx | SUCCESS | SUCCESS | SUCCESS | yes | server_error | 2.83 |
| S05-timeout-after-write | SUCCESS | SUCCESS | SUCCESS | yes | timeout_after_write | 4.741 |
| S06-partial-accept | SUCCESS | SUCCESS | SUCCESS | yes | partial_accept | 1.831 |
| S07-schema-flip | SUCCESS | SUCCESS | SUCCESS | yes | schema_flip | 1.832 |
| S08-schema-flip-during-customers | SUCCESS | SUCCESS | SUCCESS | yes | schema_flip | 1.736 |
| S09-crash-resume | SUCCESS | SUCCESS | SUCCESS | yes | - | 2.146 |
| S10-crash-after-schema-change | SUCCESS | SUCCESS | SUCCESS | yes | schema_flip | 2.239 |
| S11-orphan-invoices | PARTIAL_SUCCESS | PARTIAL_SUCCESS | PARTIAL_SUCCESS | yes | - | 1.624 |
| S12-duplicate-emails | PARTIAL_SUCCESS | PARTIAL_SUCCESS | PARTIAL_SUCCESS | yes | - | 1.649 |
| S13-credential-rotation | SUCCESS | SUCCESS | SUCCESS | yes | auth_revoke | 1.639 |
| S14-credential-revoked | WAITING_FOR_APPROVAL | WAITING_FOR_APPROVAL | WAITING_FOR_APPROVAL | yes | auth_revoke | 1.237 |
| S15-prompt-injection | SUCCESS | SUCCESS | SUCCESS | yes | - | 1.634 |
| S16-demo-chaos | SUCCESS | SUCCESS | SUCCESS | yes | rate_limit, schema_flip, timeout_after_write | 12.154 |
| S17-slow-target | SUCCESS | SUCCESS | SUCCESS | yes | slow | 3.645 |
| S18-flaky-source | SUCCESS | SUCCESS | SUCCESS | yes | - | 2.133 |
| S19-large-volume | SUCCESS | SUCCESS | SUCCESS | yes | - | 25.454 |
| S20-chaos-plus-crash | SUCCESS | SUCCESS | SUCCESS | yes | rate_limit, schema_flip, timeout_after_write | 6.45 |

## Failed verifier checks

- **S03-rate-limit-storm**: count: source 116 (0 soft-deleted excluded), quarantined 0, target 50; missing_records_quarantined: missing from target and not quarantined: I000051, I000052, I000053, I000054, I000055 (+61 more); money_by_currency: 4 problem(s): EUR: expected 550804, got 138092 (x0.25071); INR: expected 475357600, got 153583200 (x0.32309); JPY: expected 3287130, got 1537380 (x0.467697); USD: expected 1156975, got 334575 (x0.289181); golden_records: 1 problem(s): missing: I000051, I000052, I000053, I000054, I000055 (+61 more)
