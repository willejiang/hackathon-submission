from build123d import *
def derive(facts):
    d = {}
    bb = facts["bounding_box_mm"]
    d["z"] = bb["z"]
    d["t"] = 16.25
    d["bot"] = d["z"] - d["t"]
    d["cx"] = (9.45 + 152.25) / 2
    d["cy"] = 46.5
    d["w"] = (152.25 - 32.05)
    d["h"] = 2*38.95
    d["r"] = 6
    return d
def build(p):
    m = Pos(p["cx"], p["cy"], p["bot"]) * extrude(RectangleRounded(p["w"], p["h"], p["r"]), p["t"])
    return m
