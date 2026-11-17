def act(view):
    units = {}
    for i, u in enumerate(view["units"]):
        units[u["id"]] = [{"do": "fly"}, "banana", {"do": "move"}, {"do": "bonk", "dir": "N"}][i % 4]
    units[99999] = {"do": "wait"}
    return {"units": units, "colony": {"hatch": "dragon"}}
