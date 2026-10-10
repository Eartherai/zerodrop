# Post 2: first verified migration, and the verifier catching a lie (thread)

Source for the facts: `hackathon.md` (Oct 10, 17:50 to 18:05 IST) and
`tests/test_runner_api.py::test_naive_planner_is_caught_by_the_verifier`.

1/ First end-to-end run: customers, subscriptions and invoices moved between two billing systems, then re-read and checked by the independent verifier. SUCCESS.

2/ Then we gave the engine a plausible but wrong mapping: two decimals for every currency.
The engine finished and believed it had succeeded.
The verifier said FAILED: yen invoice totals were 100x too large.

3/ That is the whole point of the project in one test. A migration that looks finished is not the same as a migration that is correct. #neatHack
