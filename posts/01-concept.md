# Post 1: the idea (thread)

1/ Building for #neatHack this weekend: ZeroDrop, a migration agent that proves nothing was lost.

Every SaaS switch is a data migration. And migrations fail quietly: a dropped batch, a duplicate after a timeout, an API that changes halfway.

2/ One design rule:
The LLM decides. Code executes. An independent checker judges.

Claude writes the field mapping in a restricted language. A deterministic engine runs it. A verifier that shares no code with the agent gives the verdict.

3/ Why a separate verifier? Because an agent that grades its own work will tell you it succeeded.
We count every time the agent believed SUCCESS and the verifier disagreed. We call it a false success claim, and it is a metric on the scoreboard.

4/ Stack: Claude for mapping and diagnosis, @neatlogs for a trace of every run, Entire for a checkpoint of every coding session, cfo.ai for the business model. Repo goes public at submission.
