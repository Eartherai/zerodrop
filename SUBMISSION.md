# Submission

Submit between **Mon Oct 12, 19:00 and 23:55 IST** by quoting the official neatlogs post. The
sponsors engage with the first 50 quote posts, so 19:00 sharp is worth it.

## 1. The quote post (275 of 280 characters)

Both steps are mandatory: this quote post **and** the submission form (links arrive at 19:00).
The post must tag **@neatlogs, @EntireHQ and @arithecfo**; all three are in the text below.
Attach `evidence/video/zerodrop-demo-x.mp4` (2:19; the full 2:37 cut is at the Demo link).
If you change the name, keep the total at 280 or less.

```
ZeroDrop · Team Tokenmaxing · Khamir Desai

Our migration agent said SUCCESS. The data was wrong. An independent checker caught it, 7 times.

@neatlogs incidents · @EntireHQ build record · @arithecfo plan

Demo: https://eartherai.github.io/zerodrop/
Repo: https://github.com/Eartherai/zerodrop
#neatHack
```

## 2. Reply underneath (290 characters)

```
How each was used:
@neatlogs: every run is a trace. Its Incidents board raised 3 incidents on our runs; all resolved, 1 with a code change.
@EntireHQ: build checkpoint in git, entire-graph before changes.
@arithecfo: $499 per verified migration, break-even Mar 2027.
https://eartherai.github.io/zerodrop/evidence/
```

## 2a. Submission form: answers ready to paste

| Field (whatever they call it) | Answer |
|---|---|
| Team | Tokenmaxing (solo) |
| Name | Khamir Desai |
| Project | ZeroDrop |
| One line | The migration agent that proves nothing was lost: the model decides, code executes, an independent checker judges |
| Problem | Data migrations lose records quietly, and the tool doing the work is the one that reports success |
| How it works | An LLM writes the field mapping in a restricted language; a deterministic engine moves the records and recovers from rate limits, timeouts, crashes and a mid-run API change; an independent verifier re-reads both systems (first batch, then everything) and gives the final status |
| Public repo | https://github.com/Eartherai/zerodrop |
| Demo (live) | https://eartherai.github.io/zerodrop/ |
| Demo video | https://eartherai.github.io/zerodrop/video/zerodrop-demo.mp4 |
| neatlogs | Every run is one trace. Three incidents raised on our traces, investigated and resolved; two code changes came from them. Evidence: https://eartherai.github.io/zerodrop/evidence/ |
| Entire checkpoint ID | `01M4KEGN3Q174N063453HK5XC6` |
| Entire link | `https://entire.io/gh/Eartherai/zerodrop` once the Entire GitHub App is installed (section 4); until then the ref is in the repo: `git ls-remote https://github.com/Eartherai/zerodrop 'refs/entire/*'`. entire-graph output: https://github.com/Eartherai/zerodrop/tree/main/evidence/entire |
| cfo.ai plan | https://cfo.ai/s/VyrSUZBAxHyXEJfC |
| X post | the link to your quote post |

## 2b. Discord post (showcase channel)

```
**ZeroDrop** (team Tokenmaxing): our migration agent said SUCCESS and the data was wrong. That happened 7 times with real models this weekend. An independent checker that shares no code with the agent caught all 7.

How it works: the model writes the field mapping in a restricted language, deterministic code moves the records (rate limits, timeouts after a write landed, crashes, an API that changes version mid-run), and the checker re-reads both systems and gives the verdict. Since this morning it also re-reads the first batch, so a wrong mapping stops after 28 records instead of 182. That change came from an incident @neatlogs raised on our traces.

Numbers, all in the repo with the bad passes included: 20 of 20 failure scenarios on a real model, three passes in a row; 18 of 18 on the model that made the mistakes; 3 neatlogs incidents raised, investigated, resolved.

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
