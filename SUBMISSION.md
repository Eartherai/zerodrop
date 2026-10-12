# Submission

Submit between **Mon Oct 12, 19:00 and 23:55 IST** by quoting the official neatlogs post. The
sponsors engage with the first 50 quote posts, so 19:00 sharp is worth it.

## 1. The quote post (fits X's 280 characters: 279, so a longer name still fits)

Attach `evidence/video/zerodrop-demo-x.mp4` (2:19; the full 2:37 cut is at the Demo link).
Change the name if you want a different one shown.

```
Team Tokenmaxing · Khamir Desai
ZeroDrop: the migration agent that proves nothing was lost.

It said SUCCESS; the data was wrong. A separate checker caught it 7x, and a @neatlogs incident led to one more fix.

Demo: https://eartherai.github.io/zerodrop/
Repo: https://github.com/Eartherai/zerodrop
#neatHack
```

## 2. Reply underneath (264 characters)

```
@neatlogs: every run is a trace. Its Incidents board raised 3 incidents on our runs; all resolved, 1 with a code change.
Entire: build checkpoint in git, entire-graph before changes.
cfo.ai: $499 per verified migration, break-even Mar 2027.
https://eartherai.github.io/zerodrop/evidence/
```

## 3. Long form (Discord, a form, or a thread)

**ZeroDrop: the migration agent that proves nothing was lost**
An LLM writes the field mapping, deterministic code moves the records through rate limits,
timeouts, crashes and a mid-run API change, and an independent checker re-reads both systems
and gives the verdict the agent cannot give itself.

Try it: https://eartherai.github.io/zerodrop/
Repo: https://github.com/Eartherai/zerodrop
Demo video (2:37): https://eartherai.github.io/zerodrop/video/zerodrop-demo.mp4

Press **Start migration** on "Everything goes wrong": the page replays a real run planned by
Gemini (`gemini-3.5-flash-lite`, final code). The target answers 429 four times and the agent
waits what the server asks. A write times out after it landed, so the agent looks up 50 records
instead of sending them twice. The API changes version mid-run and the model rewrites the
mapping. After the first batch of each mapping the independent checker re-reads those records;
at the end it re-reads everything: 1,901 of 1,901 records, 24 of 24 checks, 8 model calls,
$0.03, 31 seconds. Then open "A real model's false success": the agent said SUCCESS, one
record per entity had arrived, and the checker said FAILED.

I built ZeroDrop solo for neatHack 2026. Each tool has one job. **neatlogs** traces every run
(model calls with tokens and cost, tool calls, guardrails, recoveries, state changes, the
verdict); its investigation agent raised three incidents on our traces, the critical one led
to a code change the same morning, and all three are resolved. **Entire** keeps a checkpoint
of the build session in git, and its code graph showed what a change would touch before it was
made. **cfo.ai** turned the measured cost per migration into the plan: $499 per verified
migration, about $37 to deliver, break-even March 2027 even with growth halved.

What the numbers are: seven real false successes from real models, all caught by the checker;
three causes fixed test first; then all 20 failure scenarios passing on a real model three
times in a row, the last on the final code, where the model that made the mistakes also passes
18 of 18. One pass per commit, sandbox systems, Gemini
models on the free tier ($4.06 at list price in total). No Claude run exists.

Links
- Sponsor evidence: https://eartherai.github.io/zerodrop/evidence/
- Neatlogs incidents, identified to resolved: https://github.com/Eartherai/zerodrop/blob/main/EVIDENCE.md#1-neatlogs-incidents-identified-and-resolved
- cfo.ai model: https://cfo.ai/s/VyrSUZBAxHyXEJfC
- Entire: checkpoint `01M4KEGN3Q174N063453HK5XC6` (git ref `refs/entire/checkpoints/C6/01M4KEGN3Q174N063453HK5XC6`); entire-graph output: https://github.com/Eartherai/zerodrop/tree/main/evidence/entire
- Every evaluation, including the bad passes: https://github.com/Eartherai/zerodrop/blob/main/EVALUATION.md
- Build log: https://github.com/Eartherai/zerodrop/blob/main/hackathon.md

## 4. Before you post
- Open the Demo link once and press Start migration.
- Entire page: on entire.io go to Repositories, Add repository, and install the Entire GitHub
  App for `Eartherai/zerodrop`. Then `https://entire.io/gh/Eartherai/zerodrop` works and can be
  added to the links above.
- Post at least one build-in-public post from `posts/` first (09, 07 or 08), tagged #neatHack.
