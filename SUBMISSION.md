# Submission

Submit between **Mon Oct 12, 19:00 and 23:55 IST** by quoting the official neatlogs post. The
sponsors engage with the first 50 quote posts, so 19:00 sharp is worth it.

## 1. The quote post (278 of 280 characters)

Both steps are mandatory: this quote post **and** the submission form (links arrive at 19:00).
The post must tag **@neatlogs, @EntireHQ and @arithecfo**; all three are in the text below.
Attach `evidence/video/zerodrop-demo-x.mp4` (2:20; the full 2:39 cut is at the Demo link).
If you change the name, keep the total at 280 or less.

```
Our migration agent said SUCCESS on wrong data 7 times. A separate checker caught all 7. Now 20 of 20 on a real model.

ZeroDrop · Team Tokenmaxing · Khamir Desai

@neatlogs 3 incidents resolved · @EntireHQ · @arithecfo

https://eartherai.github.io/zerodrop/
https://github.com/Eartherai/zerodrop
#neatHack
```

## 2. Reply underneath (276 characters)

```
@neatlogs: every run is a trace. Its investigation agent raised 3 incidents on our traces; all resolved, 2 with code changes.
@EntireHQ: build checkpoint in git, entire-graph before changes.
@arithecfo: $499 per verified migration, break-even Mar 2027.
https://eartherai.github.io/zerodrop/evidence/
```

## 2a. Submission form: answers ready to paste

Short fields:

| Field | Answer |
|---|---|
| Project name | ZeroDrop |
| Team / name | Tokenmaxing (solo) / Khamir Desai |
| One line | The migration agent that proves nothing was lost: the model decides, code executes, an independent checker judges |
| Quote post link | the link to your quote post |
| Public repo | https://github.com/Eartherai/zerodrop |
| Demo (live) | https://eartherai.github.io/zerodrop/ |
| Demo video | https://eartherai.github.io/zerodrop/video/zerodrop-demo.mp4 |
| Entire checkpoint ID | `01M4KEGN3Q174N063453HK5XC6` |
| Entire link | https://entire.io/et/hackathone/hackathon (public, no sign-in: commits, and the session with its checkpoint under Sessions) |
| cfo.ai plan | https://cfo.ai/s/VyrSUZBAxHyXEJfC |
| Where you live, founder or not, open to a call | yours to fill |

**Problem / how it works**
```
Data migrations lose records quietly, and the tool doing the work is the one that reports success. In ZeroDrop an LLM writes the field mapping in a restricted language; deterministic code moves the records and recovers from rate limits, timeouts, crashes and a mid-run API change; an independent verifier re-reads both systems (first batch, then everything) and gives the final status. Real models claimed SUCCESS on wrong data 7 times during the build; the verifier caught all 7.
```

**neatlogs: what did you trace, debug or improve?**
```
Traced: every migration run is one neatlogs trace: model calls with tokens and cost, each batch write, each retry, each state change, and the independent checker's verdict. Debugged: neatlogs' Investigate agent read our traces and raised 3 incidents; the Critical one was "agent SUCCESS, evaluator FAILED". Improved: its recommended step 4 became commit 286c728 (the checker re-reads the first batch). The same wrong plan now stops after 28 records and reports FAILED itself, instead of writing all 182 and claiming SUCCESS. A second incident led to commit d92588d. All 3 are Resolved. Timeline, before/after traces and what neatlogs got wrong: https://eartherai.github.io/zerodrop/evidence/
```

**Entire: how did you use it? Evidence links**
```
Checkpoints: checkpoint 01M4KEGN3Q174N063453HK5XC6 holds the start of the build session in git, secrets redacted; 41 later commits carry its Entire-Checkpoint trailer. Check: git ls-remote https://github.com/Eartherai/zerodrop 'refs/entire/*'. entire-graph, to assess risky changes before making them: entire graph impact on MigrationEngine._set_status showed 17 callers and 6 co-change files; we also ran it on the incident fix 286c728. Output: https://github.com/Eartherai/zerodrop/tree/main/evidence/entire . Public Entire page (commits, and the session with its checkpoint): https://entire.io/et/hackathone/hackathon . Limit: one checkpoint, covering the first part of the build.
```

**cfo.ai: how did it shape the business plan?**
```
cfo.ai holds the model: $499 per verified migration (failed runs are not billed), $36.77 to deliver, break-even March 2027. What it changed: 20% monthly growth for 21 months is a 46x increase, so we plan on the 10% case, which still breaks even in March 2027 and never drops below $35,213 from a $60,000 start. Public model: https://cfo.ai/s/VyrSUZBAxHyXEJfC
```

## 2b. Discord post (showcase channel)

```
**ZeroDrop** (team Tokenmaxing): our migration agent said SUCCESS and the data was wrong. That happened 7 times with real models this weekend. An independent checker that shares no code with the agent caught all 7.

How it works: the model writes the field mapping in a restricted language, deterministic code moves the records (rate limits, timeouts after a write landed, crashes, an API that changes version mid-run), and the checker re-reads both systems and gives the verdict. Since this morning it also re-reads the first batch, so a wrong mapping stops after 28 records instead of 182. That change came from an incident @neatlogs raised on our traces.

Numbers, all in the repo with the bad passes included: 20 of 20 scenarios on a real model in each of three full passes (a fourth was cut short by the free-tier quota after 8 of 8); 18 of 18 on the model that made the mistakes; 3 neatlogs incidents raised, investigated, resolved.

🔗 Try the replay of real runs: https://eartherai.github.io/zerodrop/
📋 Evidence, one page: https://eartherai.github.io/zerodrop/evidence/
💻 https://github.com/Eartherai/zerodrop

Open "A real model's false success" in the scenario list and tell me if the verdict page is clear enough to trust at a glance.
```

## 3. Long form (Discord, a form, or a thread)

**ZeroDrop: the migration agent that proves nothing was lost**
An LLM writes the field mapping, deterministic code moves the records through rate limits,
timeouts, crashes and a mid-run API change, and an independent checker re-reads both systems
and gives the verdict the agent cannot give itself.

Try it: https://eartherai.github.io/zerodrop/
Repo: https://github.com/Eartherai/zerodrop
Demo video (2:39): https://eartherai.github.io/zerodrop/video/zerodrop-demo.mp4

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
verdict); its investigation agent raised three incidents on our traces, two of them led
to code changes the same morning, and all three are resolved. **Entire** keeps one checkpoint
from the start of the build session in git (later commits carry its id), and its code graph showed what a change would touch before it was
made. **cfo.ai** turned the measured cost per migration into the plan: $499 per verified
migration, about $37 to deliver, break-even March 2027 even with growth halved.

What the numbers are: seven real false successes from real models, all caught by the checker;
three causes fixed test first; then all 20 failure scenarios passing on a real model in three
full passes, the last on the final code (one more pass was cut short by the free-tier quota
after 8 of 8), where the model that made the mistakes also passes 18 of 18. One pass per commit, sandbox systems, Gemini
models on the free tier ($4.06 at list price in total). No Claude run exists.

Links
- Sponsor evidence: https://eartherai.github.io/zerodrop/evidence/
- Neatlogs incidents, identified to resolved: https://github.com/Eartherai/zerodrop/blob/main/EVIDENCE.md#1-neatlogs-incidents-identified-and-resolved
- cfo.ai model: https://cfo.ai/s/VyrSUZBAxHyXEJfC
- Entire page (public): https://entire.io/et/hackathone/hackathon
- Entire: checkpoint `01M4KEGN3Q174N063453HK5XC6` (git ref `refs/entire/checkpoints/C6/01M4KEGN3Q174N063453HK5XC6`); entire-graph output: https://github.com/Eartherai/zerodrop/tree/main/evidence/entire
- Every evaluation, including the bad passes: https://github.com/Eartherai/zerodrop/blob/main/EVALUATION.md
- Build log: https://github.com/Eartherai/zerodrop/blob/main/hackathon.md

## 4. Before you post
- Open the Demo link once and press Start migration.
- Entire page: done. https://entire.io/et/hackathone/hackathon opens without signing in (checked Oct 12, 19:36 IST). After any
  later commit, run `git push entire main` so the page stays current.
- Post at least one build-in-public post from `posts/` first (09, 07 or 08), tagged #neatHack.
