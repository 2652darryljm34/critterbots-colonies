"""python tools/run_ladder.py [--seeds 1-6]   Runs the public ladder: every example bot plus ladder/bots/*.py, round robin, both
seats, each match in an isolated subprocess. Rating = overall win rate (ties count half), see DECISIONS.md.
Writes site/ladder/results.json and copies submitted sources to site/ladder/bots/."""
import argparse, datetime, glob, json, os, shutil, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from engine import rules                                          # noqa: E402
from ladder import load_bot, parse_seeds, play_all, summarize     # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--seeds", default="1-6")
a = ap.parse_args()
manifest = json.load(open(os.path.join(ROOT, "bots", "manifest.json")))
examples = [os.path.join(ROOT, "bots", b["file"]) for b in manifest]
mine = sorted(glob.glob(os.path.join(ROOT, "ladder", "bots", "*.py")))
bots = [load_bot(p) for p in examples + mine]
seeds = parse_seeds(a.seeds)
recs = play_all(bots, seeds)
agg = summarize(bots, recs)
ex_files = {os.path.splitext(b["file"])[0]: b["file"] for b in manifest}
out_dir = os.path.join(ROOT, "site", "ladder")
shutil.rmtree(out_dir, ignore_errors=True)
os.makedirs(os.path.join(out_dir, "bots"))
rows = []
for b in bots:
    n = b["name"]
    submitted = b["path"] in mine
    if submitted:
        shutil.copy2(b["path"], os.path.join(out_dir, "bots", n + ".py"))
    # recipes: matches where this bot sat in seat 0 against an example bot (play.html can replay those)
    mt = [(r["scores"][0] - r["scores"][1], r) for r in recs if r["a"] == n and r["b"] in ex_files and "scores" in r and r["b"] != n]
    pick = lambda m: {"opp": ex_files[m[1]["b"]], "seed": m[1]["seed"], "margin": m[0]} if mt else None
    d = agg[n]
    rows.append({"name": n, "submitted": submitted, "rating": round(100 * d["overall"], 1), "avg_score": round(d["avg_score"], 1),
                 "h2h": {k: round(100 * v) for k, v in d["h2h"].items()}, "avg_stats": {k: round(v, 2) for k, v in d["avg_stats"].items()},
                 "source": ("ladder/bots/%s.py" % n) if submitted else ("bots/%s.py" % n),
                 "best": pick(max(mt, key=lambda m: m[0])) if mt else None, "worst": pick(min(mt, key=lambda m: m[0])) if mt else None,
                 "aborted": d["aborted"]})
rows.sort(key=lambda r: -r["rating"])
json.dump({"engine_version": rules.ENGINE_VERSION, "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
           "seeds": seeds, "bots": rows}, open(os.path.join(out_dir, "results.json"), "w"), indent=1)
print("ladder: %d bots, %d matches -> site/ladder/results.json" % (len(bots), len(recs)))
for r in rows:
    print("%5.1f%%  %s%s" % (r["rating"], r["name"], "  (submitted)" if r["submitted"] else ""))
