# Extending the game

- **Rules and numbers** live in `engine/rules.py` (costs, cooldowns, capacities, growth time). Rules are currently **frozen** (see DECISIONS.md);
  bump `ENGINE_VERSION` in `engine/rules.py` whenever a change alters play, because it is part of every shared match.
- **Tick order** is in `engine/game.py` (`Game.step`) and documented in BOT_GUIDE.md. Add a micro-scenario to `tests/test_micro.py` for any rule you touch.
- **Map generation**: `engine/world.py`. Check 10 in `tests/run_checks.py` verifies mirroring, reachability and fairness for seeds 1-200.
- **Fog**: `engine/fog.py`. The viewer re-derives fog in `site/viewer.js` with the same rules, so a fog change must touch both.
- **Bots**: `farmer.py`, `raider.py` and `warlord.py` are generated from `bots/farmer.py` by `tools/make_bots.py` (edit the constants there).
  New example bot: add the file and an entry in `bots/manifest.json` (name, file, blurb, tier), then `python tools/build_site.py`.
- **Determinism**: all randomness comes from one seeded `random.Random`; bots get `random` reseeded per call. Never iterate a `set` where order matters.
  After any change run `python tests/run_checks.py` (CPython vs Pyodide byte-identical replays).
- **Site**: static files in `site/`; `python tools/build_site.py` copies engine, bots and docs into it. No bundler.
- **Ladder**: `tools/run_ladder.py` writes `site/ladder/results.json`; `tools/validate_bot.py` gates pull requests.
