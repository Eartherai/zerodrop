# Submission

**Check this first.** The organisers extended the window by seven hours on Discord (Oct 12,
23:35 IST), to about **06:55 IST on Tue Oct 13**. At 00:09 IST the public form at
https://neatlogs.com/submission still rendered as closed (its page had the old 23:55 closing time
built in). Open the form in your own browser. If it is closed, post the quote post anyway (the
quote plus the three tags is what neatlogs says its systems detect) and ask in Discord how the
form takes entries during the extension. Both steps are mandatory.

## 1. The quote post (256 characters; 280 if X adds the quoted link to the text)

Quote the launch post natively: open https://x.com/bettersayAJ/status/2109639214723932495 (it is on the founder's account; @neatlogs
confirmed it is the post to quote, and the form's "View launch post" link points to it), choose
Repost, then Quote, paste the text and attach the video. The form's own button can put the launch
link into the text, which costs 24 characters; this text fits either way. Attach the full cut
`evidence/video/zerodrop-demo.mp4` (2:41) first; if X refuses the length, attach
`evidence/video/zerodrop-demo-x.mp4` (2:20).

```
Our #neatHack submission: ZeroDrop

Our migration agent said SUCCESS on wrong data 7 times. One run wrote yen 100x too large. A separate checker caught all 7. Now 20 of 20 on a real model.

Built with @arithecfo @EntireHQ @neatlogs

https://eartherai.github.io/zerodrop/
```

## 2. Replies underneath, in this order

Reply 1 (226 characters; For judges, post this first (no image)):
```
For judges: every number maps to a trace, a commit or a saved run file, bad passes included.
https://eartherai.github.io/zerodrop/evidence/
Repo: https://github.com/Eartherai/zerodrop
Build log, dated: https://github.com/Eartherai/zerodrop/blob/main/hackathon.md
Team Tokenmaxing (solo): Khamir Desai
```

Reply 2 (277 characters; neatlogs; attach `evidence/screenshots/22-neatlogs-incidents-board-three-resolved.png` and `19-neatlogs-after-early-check-stops-the-run.png`):
```
With @neatlogs: every run is one trace. Its Investigate agent raised 3 incidents. The Critical one: agent SUCCESS, evaluator FAILED. Fix 286c728: the checker re-reads the first batch. Same wrong plan: 182 records and a false success, then stopped at 28.
https://eartherai.github.io/zerodrop/evidence/
```

Reply 3 (229 characters; Entire; no image needed, the link shows the commit page):
```
With @EntireHQ: before changing how runs change state, entire graph impact listed the 17 callers of _set_status. The incident fix as Entire shows it:
https://entire.io/et/hackathone/hackathon/commit/286c7286038c6558f82f89853b120a573ffd87e7
Limit: one checkpoint, covering the start of the build.
```

Reply 4 (208 characters; cfo.ai; attach `evidence/screenshots/08-cfo-ai-monthly-forecast.png`):
```
With @arithecfo: $499 per verified migration, $36.77 to deliver, failed runs not billed. Its hard verdict: halve growth to 10% a month and break-even is still March 2027, by only $215.
https://cfo.ai/s/VyrSUZBAxHyXEJfC
```

Reply 5 (225 characters; what broke; attach `evidence/screenshots/12-real-model-false-success-caught.png`):
```
What broke: real models claimed SUCCESS on wrong data 7 times (one id for every record; yen written 100 times too large). The checker caught all 7. Every bad pass is in the repo, next to the good ones:
https://github.com/Eartherai/zerodrop/blob/main/EVALUATION.md
```

If someone replies, answer with a fact:

To @neatlogs (246 characters):
```
Thanks. Your Investigate agent raised the Critical incident (agent SUCCESS, evaluator FAILED). Its 4th recommended step became commit 286c728: the same wrong plan wrote 182 records before and stops at 28 now. What it got wrong is in the repo too.
```

To Entire or its devrel (198 characters):
```
Thanks. entire graph impact listed 17 callers of _set_status before we changed it (commit 1838455). Honest limit: one checkpoint, covering the start of the build. Graph output is in evidence/entire.
```

To cfo.ai (176 characters):
```
Thanks. The model's pushback changed the plan: with growth halved to 10% a month, break-even is still March 2027, by only $215, and cash never drops below $35,213 from $60,000.
```

To someone asking how the checker is independent (216 characters):
```
The checker imports nothing from the engine or the planner and re-reads both systems itself. On one run the agent said SUCCESS while the target held one record per entity instead of hundreds; the checker said FAILED.
```

## 2c. Build-in-public posts (15% of the score), ready to paste

Separate posts, spaced out. They will be dated Oct 13; the dated proof of building during the
event is `hackathon.md` and the commit log. Post now rather than at dawn: Entire's staff replied
within minutes during US working hours, which run until about 06:30 IST. Longer threads with the
same facts are in `posts/07`, `08` and `09`. Do not paste the link under other teams' posts.

Post B, the neatlogs incident (278 characters; attach `evidence/screenshots/18-neatlogs-before-false-success-flagged.png` and `19-neatlogs-after-early-check-stops-the-run.png`):
```
The @neatlogs Investigate agent raised 3 incidents on our traces. The Critical one: agent SUCCESS, evaluator FAILED.

Fix 286c728: the checker re-reads the first batch.
Same wrong plan, before: 182 records, false success. After: stopped at 28.

https://eartherai.github.io/zerodrop/evidence/ #neatHack
```

Post E, what neatlogs got right and wrong (258 characters; attach `evidence/screenshots/21-neatlogs-incident-false-success-resolved-full-report.png`):
```
What the @neatlogs Investigate agent got right and wrong on our traces.

Right: its 5 evidence traces were exactly our real false successes.
Wrong: a follow-up cited 3 healthy runs.

We took its 4th step, not its 1st. Notes: https://eartherai.github.io/zerodrop/evidence/ #neatHack
```

Post A, cfo.ai (257 characters; attach `evidence/screenshots/08-cfo-ai-monthly-forecast.png`):
```
cfo.ai pushed back on our plan, and it was right.

$499 per verified migration, $36.77 to deliver, failed runs not billed. @arithecfo's verdict: halve growth to 10% a month and break-even is still March 2027, by only $215.

https://cfo.ai/s/VyrSUZBAxHyXEJfC #neatHack
```

Post C, the real false success (275 characters; attach `evidence/screenshots/12-real-model-false-success-caught.png`):
```
Our migration agent finished and said SUCCESS. The target had one record per entity instead of hundreds.

A real model had mapped every id to the same constant. An independent checker caught it; the agent could not have.

Replay of that run: https://eartherai.github.io/zerodrop/ #neatHack
```

Post D, Entire (222 characters; no image needed):
```
How we used @EntireHQ: before changing how runs change state, entire graph impact listed 17 callers. The session and its checkpoint are public, and so is the incident fix as a commit page:
https://entire.io/et/hackathone/hackathon/commit/286c7286038c6558f82f89853b120a573ffd87e7 #neatHack
```

After posting, send the links: they go into the README, the evidence page and a thread reply.

## 2a. Submission form: answers ready to paste

Step 2 of the form (read from the page): verify the check-in email with a code, then:

| Field | Answer |
|---|---|
| Project name | ZeroDrop |
| Your quote-post link | the link to your quote post |
| GitHub repository | https://github.com/Eartherai/zerodrop |
| Where do you live, founder or not, where you work and your role, open to a call | yours to fill; tick the call |

Step 3, a few lines each, in the form's order. The form has no field for the demo, the video or
the evidence page, so the last answer ends with those links.

**How cfo.ai shaped the business plan**
```
cfo.ai holds the model, built from the cost we measured per migration: $499 per verified migration (failed runs are not billed), $36.77 to deliver, break-even March 2027. What it changed: 20% monthly growth for 21 months is a 46x increase, so we plan on the 10% case, which still breaks even in March 2027, by only $215, and never drops below $35,213 from a $60,000 start. Public model: https://cfo.ai/s/VyrSUZBAxHyXEJfC
```

**How you used Entire (evidence links)**
```
Checkpoints: checkpoint 01M4KEGN3Q174N063453HK5XC6 holds the start of the build session in git, secrets redacted; more than 40 later commits carry its Entire-Checkpoint trailer. Public, no sign-in: the session https://entire.io/et/hackathone/hackathon/session/3ca2e4c1-0518-40bc-86bb-a3d3f8786516 and the incident fix as a commit page https://entire.io/et/hackathone/hackathon/commit/286c7286038c6558f82f89853b120a573ffd87e7 .
entire-graph, to assess risky changes before making them: entire graph impact on MigrationEngine._set_status listed 17 callers before we changed it; we also ran it on the incident fix 286c728 and on the dry-run function where four fixes live. Saved output: https://github.com/Eartherai/zerodrop/tree/main/evidence/entire
Limit, stated plainly: one checkpoint, covering the first part of the build.
```
Update the checkpoint count and the limit sentence here if the in-repo sessions add checkpoints.

**What you traced, debugged or improved with neatlogs**
```
Traced: every migration run is one neatlogs trace: model calls with tokens and cost, each batch write, each retry, each state change, and the independent checker's verdict. Debugged: neatlogs' Investigate agent read our traces and raised 3 incidents; the Critical one was "agent SUCCESS, evaluator FAILED", and its 5 evidence traces were exactly our real false successes. Improved: its recommended step 4 became commit 286c728 (the checker re-reads the first batch). The same wrong plan now stops after 28 records and reports FAILED itself, instead of writing all 182 and claiming SUCCESS. A second incident led to commit d92588d. All 3 are Resolved, and the false-success detector neatlogs AI suggested is on.
Demo: https://eartherai.github.io/zerodrop/ · Video: https://eartherai.github.io/zerodrop/video/zerodrop-demo.mp4 · Evidence, including what neatlogs got wrong: https://eartherai.github.io/zerodrop/evidence/
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
Demo video (2:41): https://eartherai.github.io/zerodrop/video/zerodrop-demo.mp4

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
- After any later commit, run `git push entire main` so the Entire page stays current.
- Post at least two of the build-in-public posts in section 2c.
