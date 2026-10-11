# Post 5: first real-model runs (thread)

Source for every number: `evidence/runs/*.json` and the "Real-model runs" table in
`EVALUATION.md`. Re-check the table before posting; more runs may have been added since.
Attach `evidence/screenshots/10-neatlogs-trace-s16-gemini.png`.

1/ First real-model runs of ZeroDrop. We had no Claude credit, so we added Gemini as a second planner behind the same interface. The independent verifier does not care which model planned.

2/ The chaos demo with Gemini 3.6 Flash: rate-limit storm, a timeout after a write that landed, and the API changing version mid-run.
It rewrote two mappings after the change, found 50 already-written records instead of re-sending them, and the verifier passed 24 of 24 checks. 12 model calls, about $0.08 at list price.

3/ The honest part: the first attempt failed. The free tier ran out of daily quota mid-migration. The engine halted and reported FAILED itself, and the verifier listed exactly what was missing. No false success.

4/ And one more bug found by running it: a per-minute 429 from the model API killed a run on its first call. Same lesson we had already learned for the target API: a rate limit with a retry hint is a wait, not a failure. Fixed test-first.

5/ Since then: nine of our twenty failure scenarios run with a real model, all nine ending where they should, including the ones that must NOT end in success: orphans quarantined, a revoked credential stopping to ask. Zero false success claims.

6/ In the @neatlogs trace you can see it: every Gemini call with tokens and cost, the one that errored on the rate limit, the retry, and the verifier at the end. #neatHack
