"""Regenerates bots/raider.py and bots/warlord.py from bots/farmer.py: identical code, different docstring and constants.
Edit farmer.py, then run: python tools/make_bots.py"""
import os, re
B = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bots")
src = open(os.path.join(B, "farmer.py"), encoding="utf-8").read()
head = src[:src.index('"""', 3) + 3]
VARIANTS = {
    "raider": ("Raider: small farm (4 plants) for income. A brute camps beside the rival den and bonks whoever leaves it carrying seeds;\n"
               "workers sweep up the spilled seeds and snatch.\n"
               "Generated from farmer.py (same code, different constants).",
               {"PLAN": '["brute"]', "MAX_PLANTS": "4", "SNATCH": "True", "RAID": "True"}),
    "warlord": ("Warlord: farms like farmer.py, keeps a scout on the rival den and a brute that guards the farm first and raids\n"
                "second, snatches, and stops hatching when the ticks left cannot repay a critter.\n"
                "Generated from farmer.py (same code, different constants).",
                {"PLAN": '["worker", "worker", "scout", "brute"]', "SNATCH": "True", "RAID": "True", "GUARD": "True", "THIEF": "True"}),
}
for name, (doc, consts) in VARIANTS.items():
    out = src.replace(head, '"""' + doc + '"""', 1)
    for k, v in consts.items():
        out, n = re.subn(r"^%s = [^#\n]*?(\s*#.*)?$" % k, lambda m: "%s = %s%s" % (k, v, m.group(1) or ""), out, flags=re.M)
        assert n == 1, k
    open(os.path.join(B, name + ".py"), "w", encoding="utf-8").write(out)
