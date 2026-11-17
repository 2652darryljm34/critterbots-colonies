# Build: Critterbots: Colonies

You are building a new programming game, **Critterbots: Colonies**, in `games/critterbots-colonies/`. It is the bigger sequel to
`games/critterbots/` (if that folder exists, read its `SPEC.md`, `DECISIONS.md`, `EXTENDING.md`, `engine/` and `index.html`
first and reuse what still fits: the `random` reseed per call, the error-with-line-number logging, the viewer's controls,
art style and `window.__game` hooks. Its thread-based sandbox and `replay.js`/file:// loading do **not** carry over,
because the sequel must also run in the browser). Do **not** modify the original game.

The original is a good game with one weakness: a player controls one critter, so the whole game is pathfinding plus
an occasional snatch. In a sample 200-tick match the clever bot beat the greedy one 30 to 28 with **zero** snatches.
The sequel must make strategy matter: a player runs a whole colony with an economy, unit roles, hidden information and
real conflict, and the choices (expand vs hoard, farm vs raid, defend vs attack) must visibly decide matches.

**It will be hosted on GitHub Pages so anyone can play it in a browser with nothing installed.** The same Python engine
runs locally (CPython, command line) and on the website (Pyodide in a Web Worker). Visitors write their bot in an
in-page editor, pick opponents, run the match and watch the replay. Both targets must produce byte-identical replays for
the same bots and seed.

Keep a `DECISIONS.md` (one line per decision with its reason) and log every place where you had to change a number or
rule below to make the game balanced or finishable. The numbers below are starting points; balance results win over them.

---

## Layout (all under games/critterbots-colonies/)
- `engine/` : deterministic, standard-library-only Python 3.8+ (`__init__.py`, `rules.py` constants, `world.py` map +
  terrain + spawning, `game.py` tick resolution, `fog.py` vision, `budget.py` step-budget guard, `match.py` match loop that
  takes bot source code as strings and returns the replay dict). All randomness from one `random.Random(seed)` consumed in
  a documented fixed order. No pip packages. **The engine must not import `threading`, `ctypes`, `signal`, `subprocess`
  or `os`-level process features**: it has to run unchanged in Pyodide.
- `engine/local_runner.py` : CPython-only extras for the command line (wall-clock watchdog per match, process isolation
  for the ladder). The website never imports it.
- `bots/` : five example bots (see "Example bots"). Also listed in `bots/manifest.json` (name, file, one-line blurb,
  difficulty) so the website can offer them as opponents.
- `tests/bots/` : test-only bots (crasher, slowpoke, bad-actions, no-act, turtle, spammer, guide's minimal bot).
- `run_match.py` : `python run_match.py a.py b.py [c.py d.py] [--seed N] [--ticks N] [--out FILE] [--no-open]`.
  Writes `replay.json`, prints the scoreboard, opens the local viewer unless `--no-open`. 2 or 4 bots (3 is allowed but the
  4th corner stays empty). Defaults: seed 1, ticks 400.
- `ladder.py` : `python ladder.py bots/*.py --seeds 1-10 [--json out.json]` round-robin of 2-bot matches (both seat
  orders), prints a win matrix and per-bot averages (score, snatches, bonks, hatches, plants harvested, starvations).
  Each match runs in its own subprocess with a wall-clock and memory limit, so it is safe to run on submitted bots.
- `site/` : the GitHub Pages site (see "Website"). Static files only, relative paths only, no build step required to
  serve it; `tools/build_site.py` copies `engine/`, `bots/` and the docs into `site/` and writes `site/engine_files.json`
  (file list + content hash) so the page knows what to load.
- `site/samples/` : a few committed sample replays (match recipes, see "Sharing") shown on the landing page.
- `BOT_GUIDE.md`, `DECISIONS.md`, `EXTENDING.md`, `SPEC.md` (copy of this file), `README.md` (what it is, play link,
  how to run locally, how to submit a bot), `LICENSE` (MIT unless told otherwise) with credits for Pyodide and the editor.
- `tests/run_checks.py` : runs the whole Done checklist that can be automated and prints PASS/FAIL per item.
- `tests/viewer_smoke.js` : `node tests/viewer_smoke.js [replay.json]` runs the viewer against a stubbed DOM.
- `tests/web_e2e.js` : headless-browser test (Playwright, dev dependency only, never shipped) that loads the built site
  from a local static server, runs forager vs sleepwalker through Pyodide, and compares the replay hash with the CPython one.
- `.github/workflows/` : `checks.yml` (tests on push and PR), `pages.yml` (build and deploy `site/` on push to main),
  `ladder.yml` (see "Public ladder").

## World
- Grid **24x24**, 400 ticks. Coordinates `[x, y]`, x east, y south, `[0,0]` top-left.
- Each colony owns a **den**: the 2x2 block in its corner (colony 0 top-left, 1 bottom-right, 2 top-right, 3 bottom-left).
  Own critters may share den cells (no collisions among own units there). Rival critters can never enter a den.
  A critter in its own den cannot be snatched or bonked.
- **Terrain** (static, fully known to all bots from tick 0):
  - `wall`: impassable.
  - `mud`: entering a mud cell costs the critter its next action (it is "stuck" for 1 tick, shown in the view).
  - `grass`: a critter standing in grass is invisible to rivals unless a rival unit is orthogonally adjacent.
  - `soil`: fertile ground; the only cells where seeds can be planted. Soil patches appear both near dens and in the middle.
- Map generation: everything mirrored on both axes (4-fold), every open cell reachable (flood fill), every den has the
  same BFS distance to the center and the same count of soil cells within 6 steps. Retry with the seeded RNG until valid.
  Store terrain as a list of strings in the replay and view (one char per cell), not per-cell dicts.
- **Wild seeds** spawn every 3 ticks on empty non-den, non-wall cells, never within 6 steps of a den, cap 24 on the map.
  2-bot matches spawn 180-degree-rotated pairs; 4-bot matches spawn 4-fold mirrored groups (the original learned that
  4-fold mirrors in 2-bot games keep the critters apart). Values: 1 (brown, common), 3 (golden, 25%, only within 5 steps of
  the center). The game starts with the map half full.

## Colony economy
- **Stores**: banked seeds, the colony's money. **Final score = stores at the end of the last tick.** Load still carried,
  unripe plants and living critters are worth nothing at the end, so every investment must pay back in time.
- Every colony starts with **2 workers** in its den and **4 stores**.
- **Hatching** (colony action, at most one in progress): costs stores up front, takes 6 ticks, the newborn appears on a free
  den cell (waits if all are full). Costs: worker 5, scout 3, brute 7. Max 6 living critters per colony.
- **Upkeep**: every 30 ticks each critter beyond the first two costs 1 store. If stores cannot cover it, the most recently
  hatched critter starves (removed; its load drops on the ground as seeds). This stops unit spam from being free.
- **Banking**: any own critter on any own den cell with `bank` moves its load into stores.

## Unit types
| type | capacity | vision | special |
|---|---|---|---|
| worker | 5 | 4 | `pickup`, `bank`, `snatch`, `plant`, `harvest`, `build` |
| scout | 2 | 7 | `pickup`, `bank`, `dash` (2 straight cells, cooldown 4), ignores mud |
| brute | 0 | 3 | `bonk`, `shove`, `break` (fences); cannot carry |

- **Snatch** (worker, cooldown 3, spent on a miss): from an orthogonally adjacent rival carrying load, outside its den,
  take `ceil(load/2)` capped by free capacity; victim stunned 1 tick. Resolves after movement, like the original.
- **Bonk** (brute, cooldown 4): adjacent rival outside its den drops its **entire** load onto its own cell and up to the
  3 nearest free cells as loose seeds (split into 3s and 1s, deterministic), and is stunned 2 ticks. Anyone can pick them up,
  so a bonk only pays off if your workers are near. A bonked brute is just stunned.
- **Shove** (brute, cooldown 2): pushes an adjacent rival one cell directly away. If that cell is blocked (wall, edge,
  critter, den, fence) the victim is stunned 1 tick instead. Shoving a rival into mud gets it stuck.
- Stunned critters' actions are replaced by `wait`; stun duration ends at a fixed point in the tick (document which).

## Farming
- **Plant** (worker on an empty soil cell, carrying at least 1): spends 1 load, creates a sprout owned by the colony.
- Sprouts grow through 3 visible stages and **ripen after 40 ticks** into a crop of value 4. Wild seeds never spawn on
  planted cells.
- **Harvest**: any worker (any colony) standing on a ripe crop takes it (capacity rules apply). Rivals can steal your
  crops, so farming far from home is a gamble and farming at home costs travel and soil space.
- **Trample**: a rival brute standing on an unripe sprout at the end of a tick destroys it.
- Plants owned by a colony are always visible to that colony; rival plants only when inside vision.

## Fences
- **Build** (worker, 2 stores, takes 3 consecutive build actions on the same adjacent cell): cell must be empty, open,
  non-soil, within 5 steps of the own den, and must not disconnect any open cell (flood-fill check) or block a rival den's
  only path. Max 6 fences per colony.
- Fences block rival critters only; own critters pass. Brutes `break` an adjacent rival fence in 3 consecutive actions.
- Fences must never make the map unfair to the point that a colony can wall itself in: if the turtle test bot wins
  more than 2 of 10 against the top example bot, fix the rules.

## Fog of war
- A colony sees cells within Manhattan `vision` of any of its critters plus radius 3 around its den.
- The view lists only visible rival critters (respecting grass), visible wild seeds, visible rival plants, visible rival
  fences. Terrain and walls are always fully known. Rival stores and scores are **not** visible; the view gives only a
  coarse rival status per colony: number of living critters last seen, and `rival_banked_recently` (bool, did they bank in
  the last 10 ticks). Bots keep their own memory in module globals.

## Movement and conflict resolution (order inside one tick)
1. Every bot is called once with its colony view; returns actions for its units plus an optional colony action.
2. Stunned/stuck units' actions become `wait` (and counters tick).
3. Movement (`move`, `dash`, `shove` pushes resolve in a documented sub-step). Unlike the original, a unit **may** enter a
   cell vacated during this tick (so own units can walk in a line). Resolve with a deterministic fixpoint: repeat
   "a move succeeds if its target is free or is being vacated by a successful move" until stable; two units swapping cells
   or several units entering one cell all bump. Edge, wall, rival den, rival fence, mud-stuck = bump.
4. Pickup, harvest, bank, plant, build, break, snatch, bonk resolve one unit at a time in a seeded random order over all
   units of all colonies (positions after movement).
5. Cooldowns tick down, plants grow, hatching progresses, upkeep is charged, wild seeds spawn.
Write the exact order in `BOT_GUIDE.md` and test it: each rule above gets at least one hand-built micro-scenario test in
`tests/` that sets up a tiny board and asserts the outcome (no bots needed).

## Bot API
```python
def act(view):
    return {
        "units": {unit_id: {"do": "move", "dir": "N"}, ...},   # missing units wait
        "colony": {"hatch": "scout"},                          # optional
    }
```
- `view`: `tick`, `max_ticks`, `size`, `terrain` (list of strings), `me` {`id`, `stores`, `den` (4 cells), `hatching`
  {type, ticks_left} or null, `next_upkeep_tick`, `upkeep_due`, `fences`}, `units` (own: `id`, `type`, `pos`, `load`,
  `capacity`, `vision`, `stunned`, `stuck`, cooldowns, `build_progress`), `plants` (own + visible rival: pos, owner,
  stage, ticks_to_ripe or ripe), `seeds` (visible wild + loose), `rivals` (visible units: colony, id, type, pos, load,
  stunned), `rival_fences` (visible), `rival_status`, `events_seen` (last tick's events you could see: snatches, bonks on
  your units, starvation, hatch done).
- Unit ids are stable for the life of a unit and never reused.
- Invalid action for one unit = that unit waits and one error is logged; the other units still act.
- Guards (must work identically in CPython and Pyodide, so no threads):
  - **Step budget instead of a wall-clock limit**: each `act()` call runs under `sys.settrace` counting executed lines
    (Python-level, including callees in the bot module and stdlib Python code). Default budget 200,000 lines per tick per
    colony. Exceeding it raises inside the bot, the colony's actions that tick become `wait`, and an `over budget` error is
    logged; after 3 overruns the bot is disabled. This is deterministic on every machine, which a time limit is not.
    Measure the slowdown tracing adds (CPython and Pyodide), record it in `DECISIONS.md`, and tune the budget so every
    example bot fits with at least 3x headroom.
  - Code that escapes the line counter (a huge C-level call like `sorted(range(10**9))`, `time.sleep`) is caught by an
    outer watchdog: in the browser the page terminates the Web Worker if no frame arrives for 10 s and reports which bot
    was running; locally `local_runner.py` kills the subprocess. Either way the match is reported as aborted with a clear
    message, never as a hang.
  - Exceptions caught with the bot file's line number, `print()` captured per tick (200 chars) by temporarily swapping
    `sys.stdout` around each call, `random` reseeded per call from (seed, tick, colony id), fresh deep copy of the view
    every call. Bots must not see the engine's RNG or other bots' modules (load each bot as its own module object).
- Ties: higher stores, then fewer errors, then more critters alive, then shared win.

## Example bots (a visible skill ladder)
- `sleepwalker.py` : random walk with all units, never hatches.
- `forager.py` : the original greedy, per unit with BFS; reserves targets so its two workers do not chase the same seed;
  never hatches, plants or fights. Under 80 lines, heavily commented: it is the template players copy.
- `farmer.py` : hatches workers early, plants at home soil, harvests on time, banks safely, stops investing when the
  remaining ticks cannot pay back the cost.
- `raider.py` : scouts find loaded rivals and rival farms, brutes bonk while workers sweep up the spilled seeds,
  harvests rival crops, minimal economy.
- `warlord.py` : the strong bot. Tracks rivals under fog with memory (last seen position, estimated load), mixes farming
  and raiding depending on what it sees, guards its farm when raiders appear, fences only chokepoints, times its last
  hatch by payback, retreats loaded units from threats, uses shove to block chokepoints.
- Every example bot must stay within a third of the step budget per tick with 6 units, and a full 4-bot 400-tick match of
  example bots must simulate in under 20 s in Pyodide on a mid-range laptop (measure in `tests/web_e2e.js`, report it).

## Website (site/, served by GitHub Pages)
- **Pages**: landing (`index.html`: one-paragraph pitch, an autoplaying sample replay, "Write a bot" and "Watch matches"
  buttons), `play.html` (editor + match setup + viewer), `guide.html` (BOT_GUIDE rendered to HTML at build time by
  `tools/build_site.py` with a tiny stdlib markdown converter, no JS markdown library), `ladder.html` (public ladder).
  Shared header and styles; the viewer is one shared script file used by every page.
- **Python in the browser**: Pyodide pinned to one exact version from the jsDelivr CDN, loaded once inside a Web Worker.
  The worker fetches the files in `engine_files.json`, writes them into Pyodide's virtual filesystem, and runs matches.
  Show a loading screen with progress on first load (it is several MB) and let the browser cache it. If Pyodide fails to
  load, show a plain message with the "run it locally" instructions.
- **Streaming**: the worker posts frames in batches as it simulates; the viewer can start playing while the match is still
  running, with a progress bar on the scrub track showing how far simulation has got.
- **Editor**: CodeMirror 6 from a pinned CDN build (Python mode, line numbers, error line highlighted from the log),
  starting from the guide's minimal bot. Buttons: Run, Reset to template, Load example bot (opens a read-only copy to learn
  from, "Fork" makes it editable), Import `.py`, Export `.py`. Drafts autosave to `localStorage` (several named slots).
  Errors in the log panel link to the line in the editor.
- **Match setup**: choose 1 to 3 opponents from the manifest (or your own saved slots), seed (or random), ticks, then Run.
  "Rematch" re-runs with the same settings after an edit.
- **Challenges**: a short ladder on `play.html`: beat sleepwalker, forager, farmer, raider, warlord, each over 3 fixed
  seeds. Progress stored in `localStorage` and shown as badges. This is the first thing a new visitor is pointed at.
- **Layout**: desktop gets editor and viewer side by side. On phones (narrow viewport) the replay viewer and ladder must be
  usable (watch, scrub, play/pause, perspective); the editor may show a "best on a computer" note but still works.
- Accessibility basics: all controls reachable by keyboard, visible focus, colony colours also distinguished by shape or
  label, `prefers-reduced-motion` disables shake and particle bursts.

## Sharing (no server)
- **Match recipes**: a replay is shared as a recipe, not as frames: `{engine_version, bots: [{name, source or example
  id}], seed, ticks}`. Because the engine is deterministic, opening the link re-simulates the exact match. Encode the
  recipe with `CompressionStream("deflate-raw")` + base64url into the URL fragment (`play.html#m=...`). If the URL would
  exceed ~8,000 characters, offer a "Download match file" (`.critter.json`) instead, and support opening such files.
- **Bot links**: `play.html#bot=...` loads a bot into a new editor slot.
- **Safety**: code that came from a link or file is shown in the editor, read-only, with a banner ("This bot came from a
  link. It will run in your browser.") and only runs after the visitor clicks Run. Bots run only inside the worker, which
  never receives DOM access, cookies or `localStorage` contents. Block the `js` and `pyodide` modules from bot code
  (remove them from `sys.modules` for bot imports and make importing them raise), and document this as a mitigation, not a
  guarantee.
- `engine_version` is part of every recipe; if the site's engine version differs, warn that the match may play out
  differently. Bump it whenever rules change.

## Public ladder (GitHub Actions, no server)
- Players submit a bot by pull request adding `ladder/bots/<github-username>.py` (one bot per user, max 50 KB, checked).
- `ladder.yml` on `pull_request` (never `pull_request_target`), no secrets, read-only token: validates the file loads, has
  `act`, and beats sleepwalker; posts the result as a job summary.
- On push to main (after a maintainer merges) and nightly: run `ladder.py` over all ladder bots plus the example bots,
  each match in an isolated subprocess with wall-clock, memory and no-network limits, and write `site/ladder/results.json`
  (ratings, win matrix, last-updated time, engine version) plus match recipes for each bot's best and worst match. Deploy
  with the Pages workflow. Rating: Elo or simple win rate, decided and documented in `DECISIONS.md`.
- `ladder.html` shows the table, per-bot pages with recipes you can click to watch, and links to each bot's source.
- `CONTRIBUTING.md` explains the submission rules and that submitted bots are public.

## Viewer
Everything from the original (play/pause, speeds 0.5x-4x, scrub, step, restart, mute, keyboard shortcuts, log panel with
tabs, scoreboard, winner banner in a DOM strip, board scales to fit the viewport, `#autoplay=N`, `window.__game` with
`state`/`tick`/`score`/`scores`), plus:
- **Perspective selector**: God view, or "as colony N" which shades everything that colony could not see that tick. The
  replay records per-colony visible cells per frame (compact: bitmask string or run-length per row).
- Terrain art (mud, grass tufts, soil furrows), fences, sprouts with 3 growth stages and a ripe crop look, unit types that
  read at a glance (worker, scout with ears up, brute bigger and stocky), unit id on hover.
- Click a unit: inspector card with type, load, cooldowns, its last action and result.
- Scoreboard columns: stores, carried, units alive (by type), plants growing, errors; a small stores-over-time line chart
  per colony up to the current tick.
- Scrub bar with event markers (bank, bonk, snatch, starvation, hatch) coloured by colony; clicking a marker seeks there.
- Effects: snatch line flash, bonk shake + scattering seeds, shove slide, hatch pop at the den, starvation fade,
  "+n" on bank, plant growth sparkle on ripening. WebAudio blips only after first input; mute (M).
- Must stay smooth (no visible stutter at 4x) with 4 colonies x 6 units x 400 ticks. Keep `replay.json` under 3 MB for
  that match (store per-frame state compactly; document the format in `BOT_GUIDE.md`). The viewer loads data with
  `fetch` (site) or from the worker's messages (live matches); the local command line opens the same viewer through a
  tiny `python -m http.server` started by `run_match.py`, since `fetch` does not work from file://.

## BOT_GUIDE.md
Quick start for both ways to play (website first, then local), a **minimal bot under 20 lines that works when
copy-pasted** and beats sleepwalker, the step budget and what costs steps, every view field, every
action and its preconditions, the tick order, costs/cooldowns table, fog rules, scoring, guards, tips (payback math for
hatching and planting, how to remember rivals under fog, why bonk needs a worker nearby, convoy movement), the replay
format, and how to read `ladder.py` output.

## Done checklist (tests/run_checks.py automates 1, 2, 4, 6-12; tests/web_e2e.js automates 2, 3, 4, 4b)
1. `python run_match.py bots/forager.py bots/sleepwalker.py --no-open` runs with only the standard library, exits 0, writes a valid `replay.json`.
2. Same seed and bots give a byte-identical `replay.json`, in 2-bot and 4-bot matches, **and the Pyodide build produces the same bytes as CPython** (`tests/web_e2e.js`).
3. The built site served by a plain static server (`python -m http.server` in `site/`, under a sub-path like `/critterbots-colonies/` to mimic GitHub Pages) loads with no console errors; landing replay autoplays; editor, Run, Rematch, import/export, autosave, challenges, perspective selector and every viewer control work; scrub shows the correct state at any tick; no absolute paths anywhere.
4. A crashing bot, an infinite pure-Python loop (stopped by the step budget), a stall in C code or `time.sleep` (stopped by the watchdog), and a bot returning garbage for some units only lose those actions or abort the match with a clear message; the page never freezes; errors show in the log and link to the editor line.
4b. Share links: a match recipe link and a bot link round-trip (open in a fresh browser profile, same replay hash / same code); code from a link does not run until Run is clicked; bot code cannot import `js` or `pyodide`.
4c. GitHub Actions: `checks.yml` and `pages.yml` pass on a fresh fork; `ladder.yml` rejects a bot without `act` and a bot that loses to sleepwalker, and accepts a valid one; ladder matches run in isolated subprocesses with limits.
5. Text is readable (>= 14px, high contrast); winner banner shows at the end; sound only after first input; mute works.
6. Skill ladder over seeds 1-10, both seat orders (20 matches per pair): warlord beats farmer and raider at least 14/20 each; farmer and raider each beat forager at least 14/20; forager beats sleepwalker at least 18/20.
7. **No dominant cheap strategy**: warlord beats `tests/bots/turtle.py` (fences and only forages near home) and `tests/bots/spammer.py` (hatches brutes nonstop) at least 16/20 each. Farmer vs raider must not be lopsided beyond 15/5 either way (two different strategies should both be viable).
8. **Interaction actually happens**: in warlord vs farmer over seeds 1-10, average at least 4 successful snatches + bonks per match, at least 1 rival crop harvested per match on average, and average final-score margin of the winner at least 10% of the loser's score. Print these numbers.
9. **Economy matters**: in farmer and warlord matches, average hatches >= 2 per colony and average plants harvested >= 3 per colony; at least one starvation happens across the spammer matches.
10. Map generation: 4-fold mirrored terrain, all open cells reachable, equal den-to-center BFS distance, equal soil within 6 steps of each den, for seeds 1-200.
11. Every rule in "Movement and conflict resolution" has a passing micro-scenario test (swap bump, convoy follow, three-way bump, shove into wall, shove into mud, snatch on den refused, bonk spill placement, fence flood-fill refusal, upkeep starvation order, fog with grass).
12. 2, 3 and 4-bot matches work; a missing bot file, an import error, or a missing `act` prints `error: ...` and exits 2.
13. `BOT_GUIDE.md` documents every view field, action, cost, cooldown, rule order, scoring rule and guard; its minimal bot works when pasted into `mybot.py`.

## Process
- Build in this order and keep each step runnable: rules + micro-tests, map generation, step-budget guard, single-unit
  play with the old API semantics, **a Pyodide smoke run of that minimal engine (prove CPython/Pyodide byte-identical
  output before building more on top)**, multi-unit API, economy, farming, combat units, fences, fog, example bots,
  viewer, website (worker, editor, setup, sharing, challenges), ladder + Actions, docs.
- Balance with `ladder.py`, not intuition. When a checklist balance item fails, change rules or numbers (and log the change
  in `DECISIONS.md` with the before/after ladder numbers) rather than handicapping the weaker example bot.
- Regenerate the sample recipes as the last step, including a 4-bot match (warlord, farmer, raider, forager) on a seed
  where bonks, snatches, a fence, ripe harvests and a hatch all happen; note the seed in `DECISIONS.md`.
- Do not deploy anything or push to a remote. Leave the repo ready so that enabling Pages ("GitHub Actions" as the source)
  on the user's repo is the only manual step, and write that step in `README.md`.

## Cut list
No live multiplayer or accounts, no backend server or database (everything is static files plus GitHub Actions), no
in-browser tournaments beyond the challenge ladder, no teams/alliances or bot-to-bot messaging, no tech trees or upgrades
beyond the three unit types, no procedural events or weather, no bot languages other than Python, no pip packages in the
engine or bots, no frontend framework or bundler (plain ES modules are fine; CDN libraries pinned to exact versions:
Pyodide and CodeMirror only), no analytics or tracking.
