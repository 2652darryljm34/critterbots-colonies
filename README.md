# Critterbots: Colonies

A programming game. Write a Python function `act(view)` that runs a whole critter colony for 400 ticks on a 24x24 map:
gather seeds, plant crops, hatch workers, scouts and brutes, raid your rivals, and finish with the most banked seeds.
Rivals are hidden by fog of war. The same pure-Python engine runs on the command line and in the browser (Pyodide),
and a given seed and set of bots always replay byte for byte the same.

**Play:** `https://2652darryljm34.github.io/critterbots-colonies/` (after you enable Pages, below). Nothing to install: write a bot in the page, pick opponents, watch the replay.

## Run locally
Python 3.8+ and nothing else (standard library only).

```
python run_match.py bots/forager.py bots/sleepwalker.py            # writes replay.json, opens the viewer
python run_match.py a.py b.py c.py d.py --seed 7 --ticks 400 --no-open
python ladder.py bots/*.py --seeds 1-10                              # round robin, both seats, isolated subprocesses
python tests/run_checks.py                                           # the automated checklist
```

To serve the website locally: `python tools/build_site.py`, then `cd site && python -m http.server` and open
http://localhost:8000/ (the page must be served over http; `file://` cannot load the engine).
`tests/web_e2e.js` needs `cd tests && npm install` and a Chromium (see the file header); it is a dev dependency only.

## Write a bot
Start with [BOT_GUIDE.md](BOT_GUIDE.md) (also on the site as the Guide page). `bots/` holds five examples, from `sleepwalker` to `warlord`.
Copy `bots/forager.py` as a template. Never let the order of a `set` decide anything: it breaks determinism between runtimes.

## Submit a bot to the public ladder
Open a pull request adding `ladder/bots/<github-username>.py`. See [CONTRIBUTING.md](CONTRIBUTING.md). Submitted bots are public.

## Publish on GitHub Pages
One manual step: in your repository go to **Settings > Pages > Build and deployment > Source** and choose **GitHub Actions**.
The `pages` workflow then builds `site/`, runs the ladder and deploys on every push to `main` and nightly. Nothing is deployed from this repo until you do that.

## Layout
`engine/` rules and simulation, `bots/` examples, `tests/` checks, `tools/` site build and ladder scripts, `site/` the static website
(generated copies of `engine/` and `bots/` live there; edit the sources and run `python tools/build_site.py`),
`ladder/bots/` submissions, `.github/workflows/` CI. Design choices and known issues: [DECISIONS.md](DECISIONS.md). Extending the game: [EXTENDING.md](EXTENDING.md).

## Credits and license
MIT, see [LICENSE](LICENSE). Python in the browser by [Pyodide](https://pyodide.org) (MPL-2.0), loaded from the jsDelivr CDN.
The editor is [CodeMirror 6](https://codemirror.net) (MIT), loaded from a CDN when reachable; otherwise a plain text box is used.
