# Post 4: every run links to its trace (thread)

Source: `hackathon.md` (Oct 10, 23:28 IST). Attach
`evidence/screenshots/19-neatlogs-after-early-check-stops-the-run.png`.

1/ Every ZeroDrop run is one @neatlogs trace: the planner and diagnoser as agent spans, each model call, each batch write as a tool span, each dry run as a guardrail, each recovery decision, and the independent verifier as an evaluator span.

2/ The root span carries the verdict: the verifier's status, what the agent itself claimed, and whether those two disagree.
The run page links the trace id, and the commit that produced the agent.

3/ Small honest note: our first attempt to read the trace id returned nothing in a real traced run, even though the unit test passed. Running it for real caught it. Fixed by using the SDK's supported propagation API. #neatHack
