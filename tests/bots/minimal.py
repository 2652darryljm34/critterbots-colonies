import random
def act(view):
    return {"units": {u["id"]: {"do": "move", "dir": random.choice("NESW")} for u in view["units"]}}
