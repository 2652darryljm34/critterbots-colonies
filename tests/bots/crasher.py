def act(view):
    x = view["tick"] - view["tick"]
    return {"units": {u["id"]: {"do": "move", "dir": "N"} for u in view["units"]}, "boom": 1 / x}
