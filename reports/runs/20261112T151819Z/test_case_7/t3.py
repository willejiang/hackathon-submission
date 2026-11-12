from build123d import *
def derive(facts):
    d = {}
    d["a"] = facts["bounding_box_mm"]["x"]
    d["r"] = 11.0 / 2
    return d
def build(p):
    return Pos(0, 0, p["a"] / 2) * Rot(0, p["r"], 0) * Cylinder(p["r"], p["a"])
