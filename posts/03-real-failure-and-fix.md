# Post 3: a real failure our own evaluation found (thread)

Source for the numbers: `EVALUATION.md`, `evidence/eval/20261010T122907Z-oracle-harness-check.md`,
`evidence/eval/20261010T123834Z-oracle-after-fix1-rate-limit-budget.md`,
`evidence/eval/20261010T124030Z-oracle-after-fix2-retry-after.md`.

1/ We wrote 20 failure scenarios before trusting our agent: rate-limit storms, timeouts after a write landed, crashes, a breaking API change mid-run, prompt injection in the data.
First full run: 19 of 20. One real bug.

2/ The rate-limit storm scenario failed. Six 429s in a row used up the six-attempt retry budget and 66 invoices were never written.
The verifier caught it. The agent's own claim was also FAILED, so no false success. But still a failure.

3/ Root cause: a 429 with Retry-After was counted as a failed attempt. It is not a failure, it is the server saying "wait".
Fix: rate-limit waits get their own budget. 20 of 20.

4/ Second fix from the same evaluation: we were waiting longer than the server asked. Now we wait exactly Retry-After.
That scenario went from 12.1 s to 2.8 s with the same outcome.

Commits 8c0a017 and 574aa2b. #neatHack
