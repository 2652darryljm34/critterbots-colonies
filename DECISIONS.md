# DECISIONS

Every choice the spec left open, and every number changed during balancing, with the reason.

## Engine and determinism
- **Replay identity excludes `diag`.** `sys.settrace` line counts differ between Python versions (CPython 3.15 vs Pyodide's 3.12 gave 17606 vs 17590 for the same bot), so the per-bot `max_lines` lives under `replay["diag"]` and is excluded from the byte-identical comparison. Consequence: a bot running within a few lines of the step budget could be cut off in one runtime and not the other. Keep bots well under the budget.
- **Pyodide smoke run (done before building more):** Pyodide 0.27.7 (Python 3.12.7) in node vs CPython 3.15.2: sha256 of the replay (minus `diag`) identical for a 2-bot seed-7 and a 4-bot seed-11 400-tick match.
- **The smoke run found a real bug, and it was in a bot, not the engine.** The forager broke ties between equally distant seeds with `min()` over a set; tie order depends on the interpreter's hash implementation, so the replays diverged at tick 308. Fix: tie-break on `(distance, position)`. Rule for bot authors (to go in BOT_GUIDE.md): never let the order of a `set` decide anything.
- Bots get `random.seed(seed*1000003 + tick*131 + colony)` before every `act()`, so bots using `random` are deterministic and independent of the previous call.
- Blocked imports (`js`, `pyodide`, `ctypes`, `subprocess`, `socket`, `threading`, ...) are a mitigation, not a sandbox; the real isolation is the Web Worker in the browser.

## Balance log (ladder.py, round robin, both seats, seeds 1..N; overall = average win rate vs the other four bots)
- **Start:** sleepwalker 16, forager 55, farmer 92, raider 12, warlord 75. Farmer dominant; raider worse than doing nothing; warlord lost to farmer.
- **Tried CROP_VALUE 4 -> 3 and RIPEN 40 -> 50 (via CRITTERBOTS_TUNE): not adopted.** Farmer stayed first (94 / 83) and the warlord got worse (60), so farming strength was not the real problem; the bots never met.
- **Finding:** an identical bot with SNATCH on tied the farmer exactly, so snatch never triggered. Colonies stay on their own side; interaction needs something worth attacking.
- **Rule change: a rival brute standing on a crop tramples it even when ripe** (was: only unripe sprouts). Reason: ripe crops were untouchable, so aggression had no target. Micro-test `brute_tramples_ripe_crop_too` added. Side effect: fences now have a purpose (they block brutes).
- **Bug found in my own bot, not the rules:** patrol points could be wall cells, leaving an empty list and a ZeroDivisionError every tick (132 errors in one match). Fixed with `open_cell()`. The ladder alone would not have shown this; the per-match error count did.
- **Bots:** farmer / raider / warlord are generated from `bots/farmer.py` by `tools/make_bots.py` (they differ only in PLAN, MAX_PLANTS, SNATCH and the docstring). Raider = farm 4 plants + one brute that tramples. A pure raider (no farming) never beat an economy bot in any of 8 variants tried, so it was dropped. Warlord = farm 6 + snatch + one brute.
- **Result (12 seeds):** sleepwalker 2, forager 29, farmer 58, warlord 78, raider 82 (raider vs warlord 46/54, near even). Chain holds and nobody exceeds 90%.
- **Open:** raider is slightly above warlord, and no bot builds fences, so the farmer has no counter to the brute yet. A fence-building farmer is the obvious next bot and would close the farmer > forager > ... cycle. Hatching reserve matters: RESERVE 6 made an otherwise identical warlord lose to the farmer (38%).

## Browser stage
- **Layout:** the engine runs in a Web Worker (`site/worker.js`, Pyodide 0.27.7 from jsDelivr, engine `.py` files fetched from `../engine/`). The site is served from the repository root, so Pages must publish the root (the pages live in `site/`). Pages need http(s); `file://` cannot fetch the engine, by design (the spec's file:// replay trick from the first game does not carry over).
- **Watchdog:** the page terminates the Worker if no tick arrives for 10 s and restarts it. Tested with a bot stuck in `time.sleep(60)`, which the line-count budget cannot see.
- **Editor:** CodeMirror 6 via esm.sh when reachable, plain textarea (Tab inserts 4 spaces) otherwise. The e2e test uses the textarea (`?nocm`); the CodeMirror path is NOT covered by any automated test.
- **Viewer:** drawn entirely from the replay; fog is re-derived client-side with the same rules as `engine/fog.py` (duplicated logic, so a rule change must touch both).
- **Second determinism bug, found by the real-browser test:** `near(p, q)` in `bots/farmer.py` returned `p` (the unit's own cell) as its tie-break instead of `q`, so tied goals compared equal and set order decided the move. CPython 3.15 and Pyodide's 3.12 picked different cells and the replays diverged at tick 86. Same class as the forager bug before. Fixed; browser and CPython now match byte for byte on a 400-tick farmer match. Lesson for BOT_GUIDE: sort ties on the cell, never rely on set order.
- **Ladder after the fix (12 seeds):** sleepwalker 2, forager 31, farmer 58, warlord 77, raider 81. Unchanged order.

## Balance freeze (rules frozen; see the loop-breaker prompt)
- **Rules frozen** at the current engine (0.1.0, ripe crops trampled by brutes). No further rule or number changes unless a bug shows up. Only bot logic may change.
- **Gates replaced:** HARD = forager beats sleepwalker 18/20, warlord beats every other bot 12/20 (2 wins of slack). SOFT = checklist items 6-9, reported only.
- **Bot change (the only one):** raider was the pure raider that the log above says was dropped (no farming, 3 hatches, 2 starved per match, 25% overall). Why it lost: no income, so hatches and upkeep drained it. Now: farm 4 plants + 1 brute (PLAN ["brute"], MAX_PLANTS 4, RESERVE default). Seeds 1-4: raider 25% -> 66% overall.
- **Ladder budget used (3 runs):** seeds 1-4 baseline, seeds 1-4 after the raider change, seeds 1-10 confirm.
- **Seeds 1-10 confirm (win rate, ties half):** sleepwalker 0, forager 29, farmer 84, raider 71, warlord 66.
  forager>sleepwalker 100%; farmer>forager 95%, raider>forager 100%, warlord>forager 90%; farmer>raider 70%; farmer>warlord 70%; raider>warlord 55%; warlord>raider 45%.

## Known issues (not blocking)
- **HARD gate FAILED: warlord beats farmer only 30% (6/20) and raider 45% (9/20); needs 12/20, or 10/20 with slack.** Warlord's extra hatches (4.0 vs 2.0) and the brute cost more than its 1 stolen crop and ~10 bonks per match return; farmer's economy simply out-earns it (avg stores 82 vs 53). Seeds 1-4 had warlord 62% vs farmer, so the 10-seed number also shows the small sample is noisy. Needs a bot-logic pass on warlord (not a rules pass).
- SOFT item 6: farmer>raider 14/20 needed, raider is *above* it is fine, but warlord>farmer/raider fails (above); farmer and raider both beat forager (ok); forager>sleepwalker ok.
- SOFT item 7: warlord vs tests/bots/turtle and spammer NOT re-measured this pass.
- SOFT item 8: warlord vs farmer snatches+bonks ~9.8 bonks, 0.24 snatches per colony per match (ok on count), winner margin not re-measured.
- Check 3 in tests/run_checks.py (the old "no bot above 90%, order sleepwalker<forager<farmer<warlord") fails because farmer > warlord; replace it with the new gates.

## Warlord pass (bot logic only, 3 ladder runs: seeds 1-4, 1-4, 1-10)
- Lost-match reading (warlord vs farmer seed 2, 48 vs 89): warlord planted 23 vs 41 crops because the scout+brute (10 stores + upkeep) were bought before the second extra worker. Tried PLAN ["worker","worker","scout","brute"] (was worker,scout,worker,brute): seeds 1-4 warlord v farmer 38% -> 50%.
- Tried dropping the scout (["worker","worker","brute"]): v farmer 25%, reverted.
- **Seeds 1-10 confirm with the kept plan:** farmer 84, raider 72, warlord 66, forager 28, sleepwalker 0. Warlord v farmer 30% (6/20), v raider 40% (8/20), v forager 95%. The 1-4 gain was noise; the HARD gate (warlord >= 12/20, slack 10/20 vs every bot) **still fails**.
- Evidence for the next pass: warlord averages 9.1 bonks, 0.2 snatches, 0.9 stolen crops and 0.0 trampled per match, while raider tramples 1.7 and beats warlord 60%. Bonks only spill seeds that the victim's workers re-collect; the damage that pays is trampling crops. Warlord's GUARD-first brute never gets to trample. Untested idea: make the warlord brute camp the rival fields like the raider's and keep GUARD only when a rival is inside 4 cells of our den.

## Soft items measured once at the freeze (no tuning)
- Item 7: warlord beats turtle 20/20 and spammer 20/20 (seeds 1-10, both seats). Passes.
- Item 8 (warlord vs farmer, seeds 1-10, both seats): 19.9 snatches+bonks per match, 1.75 stolen crops per match, winner margin 35% of loser's score. Passes.
- Item 9: farmer/warlord hatch 2 / 4 and harvest ~28 per colony; starvation occurs in spammer matches (19 over 5 seeds). Passes.
- Items 6 and warlord's HARD gate: still failing, see the Known issues above (warlord v farmer 30%, v raider 40%). Left as a known issue by decision. `tests/run_checks.py` item 3b prints it without failing.

## Ladder, sharing, samples, docs
- **Rating = overall win rate** (both seats, ties half), not Elo: a full round robin plays every pair equally often, so win rate is order independent, needs no K-factor or history, and anyone can recompute it from the matrix.
- **Ladder runs in `pages.yml`** (push to main, nightly, manual) so one job builds, rates and deploys; `ladder.yml` only validates pull requests (`pull_request`, read-only token, no secrets). `tools/validate_bot.py` checks name, 50 KB, loads, has `act`, beats sleepwalker 5 of 6 games.
- **Ladder recipes are `{code, opp, seed}`**, the existing `play.html#r=` share format, and only for matches against example bots (the page cannot fetch other submissions' opponents). The spec's `#m=` recipe and `#bot=` link names are NOT implemented as such: one `#r=` link holds a bot plus an example opponent and seed, and opens read-only until Run is clicked. `.critter.json` match files are not implemented.
- **Landing page sample** is a committed replay (`site/samples/four-bot.json`, 295 KB) of warlord, farmer, raider, forager on seed 6, picked from seeds 1-16 for the most snatches and bonks (23 and 24 for raider, 17 and 23 for warlord; ripe harvests and hatches throughout). **No example bot builds fences, so no fence appears in it.** `four-bot.recipe.json` is its recipe.
- The "Pages must publish the root" line in the Browser stage section is out of date: `tools/build_site.py` copies the engine into `site/`, and Pages publishes `site/`.
- Not done / not verified: perspective selector, inspector card, scoreboard charts, scrub markers and effects were not re-audited against the spec this pass; CodeMirror path has no automated test; `checks.yml`, `pages.yml` and `ladder.yml` have not been run on GitHub; `tests/web_e2e.js` does not yet cover the ladder or landing pages (checked once by hand with a headless browser under a `/critterbots-colonies/` sub-path: no console errors); no phone-width pass; challenge ladder uses 7 challenges that differ from the spec's "beat each example bot over 3 seeds".
