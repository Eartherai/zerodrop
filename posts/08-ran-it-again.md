# Post 8: we ran it again, and it got worse before it got better (thread; text ready, the owner posts it)

Source for every number: `EVIDENCE.md` section 7 and `EVALUATION.md` ("More passes", improvements
4 to 6, "The final code on a real model"). Attach
`evidence/screenshots/14-before-trace-s02-false-success.png` and
`15-after-trace-s02-verified.png`.

1/ Yesterday our migration agent passed 18 of 18 failure scenarios on a real model. We could have stopped there. We ran it again instead.

2/ Pass 2: 17 of 18. The model wrote yen amounts 100 times too large. The engine said SUCCESS. The independent verifier said FAILED, to the yen.

3/ We fixed that cause, test first. Pass 3: 15 of 18. Same symptom by a different route, plus one run the model could not repair and one killed by a 503 from the model provider.

4/ Three more fixes, each with a failing test first, two of them built from the exact mapping the model wrote. The engine now rejects those mappings before a single record is written.

5/ Every scenario, real model: 20 of 20, zero false successes. Then once more on the final code: 20 of 20. 12,458 records in the largest one, about $0.46 of model time per pass at list price.

6/ Seven false successes in total across all passes. The verifier caught seven. That is the whole idea: the agent does not grade its own work. Every pass is in the repo, the bad ones too. @neatlogs #neatHack
