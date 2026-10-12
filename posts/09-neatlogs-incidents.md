# Post 9: what Neatlogs' incidents found in our agent (thread; text ready, the owner posts it)

Source for every claim: `EVIDENCE.md` section 1 and `evidence/neatlogs/investigation-report.md`.
Attach `evidence/screenshots/20-neatlogs-incidents-board-three-raised.png`,
`19-neatlogs-after-early-check-stops-the-run.png` and
`22-neatlogs-incidents-board-three-resolved.png`.

1/ This morning we pointed @neatlogs' investigation agent at every trace our migration agent produced this weekend. It raised three incidents. The critical one: "agent SUCCESS, evaluator FAILED".

2/ Its five evidence traces were exactly the real-model runs our independent checker had flagged: every record given the same id, and yen written 100 times too large. We had fixed those causes yesterday.

3/ But its recommended action had one more step: a blocking check that asks the evaluator before the agent may claim success. We built that. After the first batch, the checker re-reads those records and the run stops if they do not match.

4/ Same wrong plan, two traces. Before: 182 records written and a false success. After: stopped at 28, and the agent reports FAILED itself.

5/ Honest part: it was not all right. One incident's evidence traces were healthy recoveries, not stuck runs, and we did not take its first suggestion (moving the checker into the agent would end its independence). It is all written down in the repo.

6/ All three incidents are resolved, and the false-success detector Neatlogs suggested from our traces is switched on. Try the replay: https://eartherai.github.io/zerodrop/ #neatHack
