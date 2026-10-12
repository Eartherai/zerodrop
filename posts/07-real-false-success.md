# Post 7: the verifier caught a real model lying to itself (thread)

Source for every number: `EVALUATION.md` ("Improvement 3") and `evidence/runs/*before-identity-guard.json`.

1/ The most useful thing that happened this weekend was a failure.
We ran our migration agent with the smallest Gemini model. Five runs finished and the engine said SUCCESS.

2/ The independent verifier said FAILED. The target had one record per entity instead of hundreds.

3/ Root cause: the model mapped every record's id to the same constant. Each payload looked valid, so the dry run passed. The target said "already have that one" 1,898 times, and the engine counted them as written.

4/ This is exactly the failure the project exists for: a migration that looks finished and is wrong. The agent could not have caught it by grading itself.

5/ Fix, test first, using the model's exact mapping: the dry run now rejects a mapping that gives different records the same identity, before any write. Same five scenarios, same model: five of five verified.

6/ All twenty of our failure scenarios have now passed with a real model. Every failing run has its @neatlogs trace next to the verifier's report. #neatHack
