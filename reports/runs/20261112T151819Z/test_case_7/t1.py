from build123d import *
def derive(facts):
    d = {}
    d["a"] = facts["bounding_box_mm"]["x"]
    return d
def build(p):
    return Box(p["a"], p["a"], p["a"])
